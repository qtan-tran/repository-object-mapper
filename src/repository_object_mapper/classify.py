"""Hierarchical object-type classifier with confidence levels.

Two passes:

1. Repository's own declared type → canonical type via ``config/type_mapping.yaml``.
   Ambiguous source types (e.g. DSpace's "Text" covering articles, reports,
   theses) are downgraded in confidence by the mapping table.
2. Rule-based classifier using identifier patterns, file extensions, and
   title/description keywords. Used when the mapping returns ``None`` or
   yields low confidence.

When the two passes disagree, the record's ``type_disagreement`` flag is set
and logged. The disagreement rate per repository is reported as a data-quality
signal in the final analysis.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import structlog
import yaml

from .schema import ConfidenceLevel, NormalizedRecord, ObjectType

log = structlog.get_logger(__name__)


# Rule-based signals -----------------------------------------------------

_KEYWORDS_STRONG: dict[ObjectType, list[str]] = {
    ObjectType.THESIS: ["thesis", "dissertation", "phd thesis", "doctoral", "master's thesis"],
    ObjectType.SOFTWARE: ["software", "codebase", "source code", "library", "package"],
    ObjectType.DATASET: ["dataset", "data set", "database"],
    ObjectType.CONFERENCE_PAPER: ["conference proceedings", "conference paper", "proceedings of"],
    ObjectType.PREPRINT: ["preprint", "working paper"],
    ObjectType.BOOK: ["monograph", "edited volume"],
    ObjectType.SUPPLEMENTARY_MATERIAL: ["supplementary", "supporting information"],
    ObjectType.REPORT: ["technical report", "white paper", "policy brief"],
}

_DOI_REGISTRANT_HINT: dict[str, tuple[ObjectType, ConfidenceLevel]] = {
    "10.5281/zenodo": (ObjectType.ARTICLE, ConfidenceLevel.MEDIUM),  # defer to declared
    "10.48550/arxiv": (ObjectType.PREPRINT, ConfidenceLevel.HIGH),
    "10.1101/": (ObjectType.PREPRINT, ConfidenceLevel.HIGH),  # bioRxiv/medRxiv
}

_FILENAME_HINTS: dict[str, ObjectType] = {
    ".csv": ObjectType.DATASET,
    ".tsv": ObjectType.DATASET,
    ".nc": ObjectType.DATASET,
    ".hdf5": ObjectType.DATASET,
    ".h5": ObjectType.DATASET,
    ".zip": ObjectType.DATASET,  # weak; defer to other signals
    ".py": ObjectType.SOFTWARE,
    ".r": ObjectType.SOFTWARE,
    ".ipynb": ObjectType.SOFTWARE,
    ".tar.gz": ObjectType.SOFTWARE,
    ".pdf": ObjectType.ARTICLE,
}


def load_type_mapping(path: Path | str) -> dict[str, Any]:
    """Load the YAML mapping. Returns an empty map if the file is missing."""
    p = Path(path)
    if not p.exists():
        log.warning("type_mapping_missing", path=str(p))
        return {}
    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data


def classify_record(
    record: NormalizedRecord,
    mapping: dict[str, Any],
) -> NormalizedRecord:
    """Apply the hierarchical classifier in place and return the record.

    Parameters
    ----------
    record:
        A NormalizedRecord whose ``object_type`` may be ``None``.
    mapping:
        Loaded ``type_mapping.yaml`` content. Structure:

        .. code-block:: yaml

            repositories:
              <repo_name>:
                declared_to_type:
                  Text: {type: article, confidence: low}
                  JournalArticle: {type: article, confidence: high}
                  Dataset: {type: dataset, confidence: high}
    """
    decl_type, decl_conf = _classify_from_declared(record, mapping)
    rule_type, rule_conf = _classify_from_rules(record)

    # Decision logic
    if (decl_type is not None and decl_conf == ConfidenceLevel.HIGH) or (decl_type is not None and rule_type is None):
        chosen, confidence = decl_type, decl_conf
    elif rule_type is not None and decl_type is None:
        chosen, confidence = rule_type, rule_conf
    elif decl_type == rule_type and decl_type is not None:
        chosen, confidence = decl_type, _max_confidence(decl_conf, rule_conf)
    else:
        # Disagreement: prefer rule-based when declared is low; otherwise declared
        if decl_type is not None and rule_type is not None and decl_type != rule_type:
            record.type_disagreement = True
            log.info(
                "type_disagreement",
                repository=record.repository_name,
                local_id=record.local_identifier,
                declared=decl_type.value,
                rule=rule_type.value,
            )
            if decl_conf == ConfidenceLevel.LOW:
                chosen, confidence = rule_type, ConfidenceLevel.MEDIUM
            else:
                chosen, confidence = decl_type, ConfidenceLevel.MEDIUM
        else:
            chosen, confidence = ObjectType.OTHER, ConfidenceLevel.LOW

    record.object_type = chosen
    record.object_type_confidence = confidence
    return record


def classify_many(
    records: list[NormalizedRecord],
    mapping: dict[str, Any],
) -> list[NormalizedRecord]:
    return [classify_record(r, mapping) for r in records]


# ----------------------------------------------------------------------
# Internals
# ----------------------------------------------------------------------


def _classify_from_declared(
    record: NormalizedRecord,
    mapping: dict[str, Any],
) -> tuple[ObjectType | None, ConfidenceLevel]:
    if not record.declared_type_raw:
        return None, ConfidenceLevel.LOW

    repos = mapping.get("repositories", {})
    repo_map = repos.get(record.repository_name) or repos.get("default") or {}
    declared_map = repo_map.get("declared_to_type", {})

    # Try exact match first, then case-insensitive
    entry = declared_map.get(record.declared_type_raw)
    if entry is None:
        for k, v in declared_map.items():
            if k.lower() == record.declared_type_raw.lower():
                entry = v
                break

    if entry is None:
        return None, ConfidenceLevel.LOW

    try:
        t = ObjectType(entry["type"])
    except (ValueError, KeyError):
        return None, ConfidenceLevel.LOW

    conf_raw = (entry.get("confidence") or "medium").lower()
    try:
        conf = ConfidenceLevel(conf_raw)
    except ValueError:
        conf = ConfidenceLevel.MEDIUM
    return t, conf


def _classify_from_rules(
    record: NormalizedRecord,
) -> tuple[ObjectType | None, ConfidenceLevel]:
    text_bits = " ".join(
        filter(None, [record.title, record.description, record.declared_type_raw])
    ).lower()

    # 1. Title/description keyword match (highest-specificity wins)
    for ot, kws in _KEYWORDS_STRONG.items():
        for kw in kws:
            if kw in text_bits:
                return ot, ConfidenceLevel.HIGH

    # 2. DOI registrant hint
    for ident in record.identifiers:
        if ident.scheme == "doi":
            for prefix, (ot, conf) in _DOI_REGISTRANT_HINT.items():
                if ident.value.lower().startswith(prefix):
                    return ot, conf

    # 3. Filename extension (guarded against ambiguous extensions)
    for ident in record.identifiers:
        url = ident.value.lower()
        for ext, ot in _FILENAME_HINTS.items():
            if url.endswith(ext):
                return ot, ConfidenceLevel.MEDIUM

    # 4. ISBN/ISSN heuristic
    for ident in record.identifiers:
        if ident.scheme == "isbn":
            return ObjectType.BOOK, ConfidenceLevel.HIGH
        if ident.scheme == "issn":
            return ObjectType.ARTICLE, ConfidenceLevel.MEDIUM

    return None, ConfidenceLevel.LOW


_CONF_ORDER = {
    ConfidenceLevel.LOW: 0,
    ConfidenceLevel.MEDIUM: 1,
    ConfidenceLevel.HIGH: 2,
}


def _max_confidence(a: ConfidenceLevel, b: ConfidenceLevel) -> ConfidenceLevel:
    return a if _CONF_ORDER[a] >= _CONF_ORDER[b] else b


def disagreement_rate(records: list[NormalizedRecord]) -> dict[str, float]:
    """Return per-repository disagreement rate (declared vs rule-based)."""
    by_repo: dict[str, list[NormalizedRecord]] = {}
    for r in records:
        by_repo.setdefault(r.repository_name, []).append(r)

    out: dict[str, float] = {}
    for repo, rs in by_repo.items():
        if not rs:
            continue
        out[repo] = sum(1 for r in rs if r.type_disagreement) / len(rs)
    return out


# Safe regex compile (not used in hot path, but retained for future hooks)
_ARXIV_RE = re.compile(r"arxiv:\s?(\d{4}\.\d{4,5})", re.IGNORECASE)
