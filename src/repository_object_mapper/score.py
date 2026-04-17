"""Embeddedness scoring.

Three theoretically distinct dimensions are computed per record, each in two
forms:

- **Raw**: the quantity as observed in the record, normalized across the
  pooled v0.2 corpus via min-max scaling.
- **Available-adjusted**: the same quantity normalized by the repository's
  available affordances from the capability profile. Isolates depositor /
  curation behavior from schema capacity.

Both forms are reported. Their divergence is the core H2-relevant signal.

Dimension definitions
---------------------

1. **Relational embeddedness** (``relational``)
   Raw = ``log1p(relation_count)`` + ``distinct_relation_type_count / c``
   Adjusted = ``used_relation_types / available_relation_types``
   (a ratio in [0, 1]).

2. **Agent embeddedness** (``agent``)
   Raw components:
     - ORCID coverage ratio among creators
     - 1 if any affiliation ROR present else 0
     - 1 if any funder identifier present else 0
     - 1 if any project ID present else 0
   Raw = mean of components.
   Adjusted = observed_identifier_types / schema_exposed_identifier_slots.

3. **Object embeddedness** (``object``)
   Raw = ``log1p(resolved_link_count)`` + ``distinct_resolved_type_count / c``
   Computed under each resolution-inclusion policy (fully-only, fully+weakly).
   Adjusted = same quantity normalized by expected-given-infrastructure
   proxy from the capability profile.

A secondary composite ``overall_embeddedness_score`` is the equal-weight mean of
the three scaled dimensions; ``article_autonomy_score = 1 - overall`` is a
legacy inverse.

See ``docs/scoring.md`` for the exact formulas and worked examples.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from .schema import NormalizedRecord, ObjectType, Relation, ResolutionTier

# A scaling constant for the distinct-type bonus. Keeps dimension components
# on roughly comparable scales before the pooled min-max normalization step.
_DISTINCT_TYPE_SCALE = 10.0


ResolutionPolicy = Literal["fully_only", "fully_and_weakly"]


@dataclass
class RecordScores:
    """Per-record raw and adjusted scores, pre-normalization."""

    record_id: str
    repository: str
    tier: int
    object_type: str | None

    # Raw
    relational_raw: float
    agent_raw: float
    object_raw_fully: float
    object_raw_fully_weakly: float

    # Adjusted (in [0, 1])
    relational_adjusted: float
    agent_adjusted: float
    object_adjusted_fully: float
    object_adjusted_fully_weakly: float


# ----------------------------------------------------------------------
# Per-record computations
# ----------------------------------------------------------------------


def _relation_count_and_distinct(
    relations: list[Relation],
) -> tuple[int, int]:
    n = len(relations)
    distinct = len({r.native_relation_type for r in relations})
    return n, distinct


def _object_link_stats(
    relations: list[Relation],
    policy: ResolutionPolicy,
) -> tuple[int, int]:
    """Count resolved links and distinct resolved types under a policy."""
    if policy == "fully_only":
        allowed = {ResolutionTier.FULLY_TYPED}
    else:
        allowed = {ResolutionTier.FULLY_TYPED, ResolutionTier.WEAKLY_TYPED}

    resolved = [
        r
        for r in relations
        if r.resolution_tier in allowed and r.resolved_object_type is not None
    ]
    n = len(resolved)
    distinct = len({r.resolved_object_type for r in resolved if r.resolved_object_type})
    return n, distinct


def _agent_raw(record: NormalizedRecord) -> float:
    """Mean of four identifier-presence components."""
    orcid_ratio = 0.0
    if record.creators:
        with_orcid = sum(1 for c in record.creators if c.orcid)
        orcid_ratio = with_orcid / len(record.creators)

    any_ror = 1.0 if any(
        aff.ror for c in record.creators for aff in c.affiliations
    ) else 0.0
    any_funder_id = 1.0 if any(f.funder_id for f in record.funders) else 0.0
    any_project = 1.0 if any(f.project_id for f in record.funders) else 0.0

    return float(np.mean([orcid_ratio, any_ror, any_funder_id, any_project]))


def _relational_adjusted(
    record: NormalizedRecord,
    available_relation_types_count: int,
) -> float:
    if available_relation_types_count <= 0:
        return 0.0
    distinct = len({r.native_relation_type for r in record.relations})
    return min(1.0, distinct / available_relation_types_count)


def _agent_adjusted(
    record: NormalizedRecord,
    exposed_slots: int,
) -> float:
    """Observed identifier types / schema-exposed identifier slots.

    Slots considered: ORCID, ROR, funder_id, project_id. Exposed by the
    schema = count of those slots the source format permits. Observed =
    count populated in this record.
    """
    if exposed_slots <= 0:
        return 0.0

    observed = 0
    if any(c.orcid for c in record.creators):
        observed += 1
    if any(aff.ror for c in record.creators for aff in c.affiliations):
        observed += 1
    if any(f.funder_id for f in record.funders):
        observed += 1
    if any(f.project_id for f in record.funders):
        observed += 1
    return min(1.0, observed / exposed_slots)


def _object_adjusted(
    n_resolved: int,
    n_distinct_resolved: int,
    infrastructure_proxy: int,
) -> float:
    """Object embeddedness adjusted for infrastructure capacity.

    infrastructure_proxy = number of distinct native relation types seen in
    the repository corpus. A tier-1 repo with only ``dc:relation`` has a
    proxy of 1; a tier-3 DataCite repo may expose a dozen.
    """
    if infrastructure_proxy <= 0:
        return 0.0
    # Use distinct resolved types as the numerator — the *variety* of object
    # classes is what matters for decentering, not raw count.
    return min(1.0, n_distinct_resolved / infrastructure_proxy)


# ----------------------------------------------------------------------
# Corpus-level driver
# ----------------------------------------------------------------------


def score_records(
    records: list[NormalizedRecord],
    profile: dict[str, dict],
) -> pd.DataFrame:
    """Compute all dimensions for all records and return a DataFrame.

    Min-max normalization is applied at the end, pooled across the full
    corpus so cross-repository comparison is well-defined.
    """
    rows: list[RecordScores] = []

    for r in records:
        repo_profile = profile.get(r.repository_name, {})
        avail = repo_profile.get("available_affordances", {})

        available_relation_types = int(
            avail.get("native_relation_types_count", 0)
        )
        # Schema-exposed slots for agent adjustment
        exposed_slots = sum(
            [
                bool(avail.get("permits_creator_orcid", False)),
                bool(avail.get("permits_affiliation_ror", False)),
                bool(avail.get("permits_funder", False)),
                bool(avail.get("permits_funder", False)),  # project slot tied to funder
            ]
        )

        infra_proxy = int(avail.get("native_relation_types_count", 0))

        n, distinct = _relation_count_and_distinct(r.relations)
        relational_raw = math.log1p(n) + distinct / _DISTINCT_TYPE_SCALE

        n_f, d_f = _object_link_stats(r.relations, "fully_only")
        n_fw, d_fw = _object_link_stats(r.relations, "fully_and_weakly")
        object_raw_f = math.log1p(n_f) + d_f / _DISTINCT_TYPE_SCALE
        object_raw_fw = math.log1p(n_fw) + d_fw / _DISTINCT_TYPE_SCALE

        rows.append(
            RecordScores(
                record_id=r.local_identifier,
                repository=r.repository_name,
                tier=r.repository_a_priori_tier,
                object_type=r.object_type.value if r.object_type else None,
                relational_raw=relational_raw,
                agent_raw=_agent_raw(r),
                object_raw_fully=object_raw_f,
                object_raw_fully_weakly=object_raw_fw,
                relational_adjusted=_relational_adjusted(r, available_relation_types),
                agent_adjusted=_agent_adjusted(r, exposed_slots),
                object_adjusted_fully=_object_adjusted(n_f, d_f, infra_proxy),
                object_adjusted_fully_weakly=_object_adjusted(n_fw, d_fw, infra_proxy),
            )
        )

    df = pd.DataFrame([row.__dict__ for row in rows])

    # Pooled min-max normalization of raw scores to [0, 1]
    for col in (
        "relational_raw",
        "agent_raw",
        "object_raw_fully",
        "object_raw_fully_weakly",
    ):
        df[f"{col}_norm"] = _minmax(df[col])

    # Composite: equal-weight mean of normalized raw (primary policy = fully_only)
    df["overall_embeddedness_score"] = df[
        ["relational_raw_norm", "agent_raw", "object_raw_fully_norm"]
    ].mean(axis=1)
    df["article_autonomy_score"] = 1.0 - df["overall_embeddedness_score"]

    return df


def _minmax(s: pd.Series) -> pd.Series:
    if s.empty:
        return s
    lo, hi = s.min(), s.max()
    if hi == lo:
        return pd.Series(np.zeros(len(s)), index=s.index)
    return (s - lo) / (hi - lo)


def summarize_by_repository(scores: pd.DataFrame) -> pd.DataFrame:
    """Produce the per-repository summary CSV (descriptive statistics)."""
    if scores.empty:
        return pd.DataFrame()

    grouped = scores.groupby("repository").agg(
        n=("record_id", "count"),
        tier=("tier", "first"),
        relational_raw_mean=("relational_raw_norm", "mean"),
        agent_raw_mean=("agent_raw", "mean"),
        object_raw_fully_mean=("object_raw_fully_norm", "mean"),
        relational_adj_mean=("relational_adjusted", "mean"),
        agent_adj_mean=("agent_adjusted", "mean"),
        object_adj_fully_mean=("object_adjusted_fully", "mean"),
        overall_mean=("overall_embeddedness_score", "mean"),
    )
    return grouped.reset_index()


def articles_only(scores: pd.DataFrame, min_confidence: str = "medium") -> pd.DataFrame:
    """Filter to article records at or above the confidence threshold.

    The confidence column is not present on scores; callers should pre-join
    confidence from the normalized records if needed. This helper filters by
    ``object_type == 'article'`` only.
    """
    return scores[scores["object_type"] == ObjectType.ARTICLE.value].copy()
