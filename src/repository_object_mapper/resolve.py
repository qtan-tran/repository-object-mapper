"""Resolution micro-pipeline.

Responsible for taking the identifiers extracted into relations and producing
a ``(resolved_object_type, resolution_tier)`` pair for each. Owned independently
of upstream stages: reruns are cheap, retries are local, and the cache holds
state across v0.2 → v0.5.

Three tiers:

1. **Fully typed** — Crossref/DataCite API confirms a ``type`` field,
   or DataCite ``relatedIdentifier`` supplies ``resourceTypeGeneral`` directly.
2. **Weakly typed** — the identifier pattern alone maps to a type
   (e.g. arXiv → preprint, Software Heritage → software, PMC → article).
3. **Unresolved** — URL-only, failed DOI lookup, or unknown scheme.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Any

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .cache import ResolutionCache
from .schema import Identifier, NormalizedRecord, ObjectType, Relation, ResolutionTier

log = structlog.get_logger(__name__)


CROSSREF_URL = "https://api.crossref.org/works/{doi}"
DATACITE_URL = "https://api.datacite.org/dois/{doi}"


# Pattern-based weak typing (applied before any network call)
_WEAK_PATTERNS: list[tuple[str, ObjectType]] = [
    ("arxiv", ObjectType.PREPRINT),
    ("softwareheritage", ObjectType.SOFTWARE),
    ("swh:", ObjectType.SOFTWARE),
    ("pmc", ObjectType.ARTICLE),
    ("pubmed", ObjectType.ARTICLE),
    ("bioarxiv", ObjectType.PREPRINT),
    ("biorxiv", ObjectType.PREPRINT),
    ("medrxiv", ObjectType.PREPRINT),
]


# Crossref "type" → ObjectType (only entries we consume with HIGH confidence)
_CROSSREF_TYPE_MAP: dict[str, ObjectType] = {
    "journal-article": ObjectType.ARTICLE,
    "book": ObjectType.BOOK,
    "book-chapter": ObjectType.BOOK_CHAPTER,
    "proceedings-article": ObjectType.CONFERENCE_PAPER,
    "dataset": ObjectType.DATASET,
    "report": ObjectType.REPORT,
    "dissertation": ObjectType.THESIS,
    "posted-content": ObjectType.PREPRINT,
    "component": ObjectType.SUPPLEMENTARY_MATERIAL,
    "reference-book": ObjectType.BOOK,
}


# DataCite resourceTypeGeneral → ObjectType
_DATACITE_TYPE_MAP: dict[str, ObjectType] = {
    "JournalArticle": ObjectType.ARTICLE,
    "Text": ObjectType.OTHER,  # ambiguous; require secondary disambiguation
    "Dataset": ObjectType.DATASET,
    "Software": ObjectType.SOFTWARE,
    "Book": ObjectType.BOOK,
    "BookChapter": ObjectType.BOOK_CHAPTER,
    "Report": ObjectType.REPORT,
    "Thesis": ObjectType.THESIS,
    "Preprint": ObjectType.PREPRINT,
    "ConferencePaper": ObjectType.CONFERENCE_PAPER,
}


@dataclass
class ResolutionConfig:
    contact_email: str
    request_rate_per_second: float = 2.0
    timeout_seconds: float = 15.0


def resolve_identifier(
    identifier: Identifier,
    cache: ResolutionCache,
    config: ResolutionConfig,
    *,
    datacite_hint: str | None = None,
    client: httpx.Client | None = None,
) -> tuple[ObjectType | None, ResolutionTier]:
    """Resolve a single identifier with caching.

    Parameters
    ----------
    datacite_hint:
        If the source record included a DataCite ``resourceTypeGeneral`` on
        the related identifier, pass it here so we trust it as fully-typed
        without additional network calls.
    """
    cached = cache.get(identifier.scheme, identifier.value)
    if cached is not None:
        ot = ObjectType(cached["resolved_object_type"]) if cached["resolved_object_type"] else None
        return ot, ResolutionTier(cached["resolution_tier"])

    # 1) DataCite hint — fully typed without a network call
    if datacite_hint and datacite_hint in _DATACITE_TYPE_MAP:
        mapped = _DATACITE_TYPE_MAP[datacite_hint]
        if mapped is not ObjectType.OTHER:
            cache.put(
                identifier.scheme,
                identifier.value,
                resolver_used="datacite_hint",
                http_status=None,
                raw_response={"resourceTypeGeneral": datacite_hint},
                resolved_object_type=mapped,
                resolution_tier=ResolutionTier.FULLY_TYPED,
            )
            return mapped, ResolutionTier.FULLY_TYPED

    # 2) DOI → Crossref → DataCite fallback
    if identifier.scheme == "doi":
        owns_client = client is None
        c = client or httpx.Client(
            headers={"User-Agent": f"repository-object-mapper/0.2 (mailto:{config.contact_email})"},
            timeout=config.timeout_seconds,
        )
        try:
            ot, status, raw = _doi_lookup(identifier.value, c)
            if ot is not None:
                cache.put(
                    identifier.scheme,
                    identifier.value,
                    resolver_used=raw.get("_resolver") if raw else None,
                    http_status=status,
                    raw_response=raw,
                    resolved_object_type=ot,
                    resolution_tier=ResolutionTier.FULLY_TYPED,
                )
                return ot, ResolutionTier.FULLY_TYPED
            # Not resolvable: fall through
            cache.put(
                identifier.scheme,
                identifier.value,
                resolver_used="doi_failed",
                http_status=status,
                raw_response=None,
                resolved_object_type=None,
                resolution_tier=ResolutionTier.UNRESOLVED,
            )
            return None, ResolutionTier.UNRESOLVED
        finally:
            if owns_client:
                c.close()
                time.sleep(1.0 / max(config.request_rate_per_second, 0.01))

    # 3) Pattern-based weak typing
    weak = _weak_match(identifier)
    if weak is not None:
        cache.put(
            identifier.scheme,
            identifier.value,
            resolver_used="pattern",
            http_status=None,
            raw_response=None,
            resolved_object_type=weak,
            resolution_tier=ResolutionTier.WEAKLY_TYPED,
        )
        return weak, ResolutionTier.WEAKLY_TYPED

    # 4) Unresolvable
    cache.put(
        identifier.scheme,
        identifier.value,
        resolver_used=None,
        http_status=None,
        raw_response=None,
        resolved_object_type=None,
        resolution_tier=ResolutionTier.UNRESOLVED,
    )
    return None, ResolutionTier.UNRESOLVED


def resolve_records(
    records: list[NormalizedRecord],
    cache: ResolutionCache,
    config: ResolutionConfig,
    *,
    mock: bool = False,
) -> list[NormalizedRecord]:
    """Walk all relations on all records and populate resolution fields.

    In ``mock`` mode, network calls are skipped — only cache hits and weak
    pattern matches are used. The function mutates records in place.
    """
    client: httpx.Client | None = None
    if not mock:
        client = httpx.Client(
            headers={"User-Agent": f"repository-object-mapper/0.2 (mailto:{config.contact_email})"},
            timeout=config.timeout_seconds,
        )
    try:
        for record in records:
            for rel in record.relations:
                # DataCite may carry native type hints in extras (rare);
                # for v0.2 we pass None and let cache/pattern logic decide.
                ot, tier = _resolve_with_mock_guard(
                    rel, cache, config, client=client, mock=mock
                )
                rel.resolved_object_type = ot
                rel.resolution_tier = tier
    finally:
        if client is not None:
            client.close()

    return records


def _resolve_with_mock_guard(
    rel: Relation,
    cache: ResolutionCache,
    config: ResolutionConfig,
    client: httpx.Client | None,
    mock: bool,
) -> tuple[ObjectType | None, ResolutionTier]:
    """Wrapper preventing network access under mock mode."""
    if mock:
        # Cache only + pattern only
        cached = cache.get(rel.target_identifier.scheme, rel.target_identifier.value)
        if cached is not None:
            ot = (
                ObjectType(cached["resolved_object_type"])
                if cached["resolved_object_type"]
                else None
            )
            return ot, ResolutionTier(cached["resolution_tier"])
        weak = _weak_match(rel.target_identifier)
        if weak is not None:
            cache.put(
                rel.target_identifier.scheme,
                rel.target_identifier.value,
                resolver_used="pattern",
                http_status=None,
                raw_response=None,
                resolved_object_type=weak,
                resolution_tier=ResolutionTier.WEAKLY_TYPED,
            )
            return weak, ResolutionTier.WEAKLY_TYPED
        cache.put(
            rel.target_identifier.scheme,
            rel.target_identifier.value,
            resolver_used=None,
            http_status=None,
            raw_response=None,
            resolved_object_type=None,
            resolution_tier=ResolutionTier.UNRESOLVED,
        )
        return None, ResolutionTier.UNRESOLVED

    return resolve_identifier(
        rel.target_identifier, cache, config, client=client,
    )


# ----------------------------------------------------------------------
# Pattern and DOI internals
# ----------------------------------------------------------------------


def _weak_match(identifier: Identifier) -> ObjectType | None:
    scheme = identifier.scheme.lower()
    value = identifier.value.lower()
    combined = f"{scheme} {value}"
    for pat, ot in _WEAK_PATTERNS:
        if pat in combined:
            return ot
    return None


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(httpx.HTTPError),
    reraise=True,
)
def _http_get(client: httpx.Client, url: str) -> httpx.Response:
    r = client.get(url)
    return r


def _doi_lookup(
    doi: str, client: httpx.Client
) -> tuple[ObjectType | None, int | None, dict[str, Any] | None]:
    # Try Crossref first
    try:
        r = _http_get(client, CROSSREF_URL.format(doi=doi))
        if r.status_code == 200:
            data = r.json().get("message", {})
            ctype = data.get("type")
            if ctype in _CROSSREF_TYPE_MAP:
                return (
                    _CROSSREF_TYPE_MAP[ctype],
                    200,
                    {"_resolver": "crossref", "type": ctype},
                )
    except httpx.HTTPError as exc:
        log.debug("crossref_http_error", doi=doi, error=str(exc))

    # Fall back to DataCite
    try:
        r = _http_get(client, DATACITE_URL.format(doi=doi))
        if r.status_code == 200:
            data = r.json().get("data", {}).get("attributes", {})
            rtg = (data.get("types") or {}).get("resourceTypeGeneral")
            if rtg in _DATACITE_TYPE_MAP and _DATACITE_TYPE_MAP[rtg] is not ObjectType.OTHER:
                return (
                    _DATACITE_TYPE_MAP[rtg],
                    200,
                    {"_resolver": "datacite", "resourceTypeGeneral": rtg},
                )
    except httpx.HTTPError as exc:
        log.debug("datacite_http_error", doi=doi, error=str(exc))

    return None, None, None


# ----------------------------------------------------------------------
# Pilot report
# ----------------------------------------------------------------------


def run_resolution_pilot(
    records: list[NormalizedRecord],
    cache: ResolutionCache,
    config: ResolutionConfig,
    n: int = 500,
    seed: int = 42,
    mock: bool = False,
) -> dict[str, Any]:
    """Run the mandatory 500-identifier pilot described in the spec.

    Returns a summary dict that is also written to
    ``docs/resolution_pilot.md`` by the CLI.
    """
    rng = random.Random(seed)
    # Pool all identifiers from Zenodo (or first tier-3 repo found)
    pool: list[Identifier] = []
    for r in records:
        if r.repository_a_priori_tier == 3:
            for rel in r.relations:
                pool.append(rel.target_identifier)

    if not pool:
        # Fallback: use any relations at all
        for r in records:
            for rel in r.relations:
                pool.append(rel.target_identifier)

    sample = pool if len(pool) <= n else rng.sample(pool, n)
    log.info("pilot_start", sample_size=len(sample), mock=mock)

    # Stub relations for the resolve logic
    stub_records = [
        NormalizedRecord(
            repository_name="pilot",
            repository_a_priori_tier=3,
            local_identifier=f"pilot-{i}",
            raw_path="",
            provenance=_DUMMY_PROVENANCE,
            relations=[Relation(native_relation_type="sample", target_identifier=ident)],
        )
        for i, ident in enumerate(sample)
    ]
    resolve_records(stub_records, cache, config, mock=mock)

    tiers = {
        ResolutionTier.FULLY_TYPED: 0,
        ResolutionTier.WEAKLY_TYPED: 0,
        ResolutionTier.UNRESOLVED: 0,
    }
    url_only = 0
    for r in stub_records:
        rel = r.relations[0]
        if rel.resolution_tier is not None:
            tiers[rel.resolution_tier] += 1
        if (
            rel.resolution_tier == ResolutionTier.UNRESOLVED
            and rel.target_identifier.scheme in {"url", "other"}
        ):
            url_only += 1

    total = len(sample)
    return {
        "sample_size": total,
        "fully_typed": tiers[ResolutionTier.FULLY_TYPED],
        "weakly_typed": tiers[ResolutionTier.WEAKLY_TYPED],
        "unresolved": tiers[ResolutionTier.UNRESOLVED],
        "fully_typed_rate": tiers[ResolutionTier.FULLY_TYPED] / total if total else 0.0,
        "weakly_typed_rate": tiers[ResolutionTier.WEAKLY_TYPED] / total if total else 0.0,
        "unresolved_rate": tiers[ResolutionTier.UNRESOLVED] / total if total else 0.0,
        "url_only_unresolved_rate": url_only / total if total else 0.0,
    }


# Provenance placeholder used for pilot-only stub records
from datetime import datetime, timezone  # noqa: E402

from .schema import HarvestProvenance  # noqa: E402

_DUMMY_PROVENANCE = HarvestProvenance(
    timestamp=datetime.now(timezone.utc),
    endpoint="pilot",
    format_negotiated="pilot",
    adapter_name="pilot",
    adapter_version="0.2.0",
)
