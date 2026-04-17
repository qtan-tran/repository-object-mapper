"""Per-repository capability profile.

Separates **available affordances** (what the schema *permits* and the
repository *exposes*) from **used affordances** (what harvested records
actually populate). This separation is central to the H2 analysis; see
``docs/scoring.md`` and the README for the theoretical motivation.

The profile is written to ``output/repository_profile.json`` and is a
first-class paper artifact — not a diagnostic appendix.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .schema import NormalizedRecord, ObjectType, ResolutionTier


def build_profile(
    records: list[NormalizedRecord],
    adapter_capabilities: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Produce the per-repository capability profile.

    Parameters
    ----------
    records:
        All harvested normalized records.
    adapter_capabilities:
        Mapping repository_name → adapter.describe_capabilities().
    """
    by_repo: dict[str, list[NormalizedRecord]] = defaultdict(list)
    for r in records:
        by_repo[r.repository_name].append(r)

    profile: dict[str, Any] = {}

    for repo, rs in by_repo.items():
        n_total = len(rs)
        articles = [
            r for r in rs if r.object_type == ObjectType.ARTICLE
        ]
        n_art = len(articles) or 1  # guard division

        # Available affordances: from adapter static declaration and from
        # empirical observation of which relation types appeared at all.
        static_caps = adapter_capabilities.get(repo, {})

        native_relation_types_seen: Counter[str] = Counter()
        for r in rs:
            for rel in r.relations:
                native_relation_types_seen[rel.native_relation_type] += 1

        # Used affordances among articles only (H2 is about articles)
        relation_populated_count = sum(1 for a in articles if a.relations)
        at_least_one_orcid = sum(
            1
            for a in articles
            if any(c.orcid for c in a.creators)
        )
        at_least_one_ror = sum(
            1
            for a in articles
            if any(
                aff.ror
                for c in a.creators
                for aff in c.affiliations
            )
        )
        funder_present = sum(
            1 for a in articles if any(f.funder_id for f in a.funders)
        )

        # Per-native-type population rate among articles
        per_type_rate: dict[str, float] = {}
        for ntype in native_relation_types_seen:
            k = sum(
                1
                for a in articles
                if any(rel.native_relation_type == ntype for rel in a.relations)
            )
            per_type_rate[ntype] = k / n_art

        # Resolved-object-type distribution across relations of articles
        resolved_counts: Counter[str] = Counter()
        tier_counts: Counter[str] = Counter()
        for a in articles:
            for rel in a.relations:
                if rel.resolved_object_type is not None:
                    resolved_counts[rel.resolved_object_type.value] += 1
                else:
                    resolved_counts["unresolved"] += 1
                if rel.resolution_tier is not None:
                    tier_counts[rel.resolution_tier.value] += 1

        profile[repo] = {
            "n_records_total": n_total,
            "n_article_records": len(articles),
            "a_priori_tier": rs[0].repository_a_priori_tier if rs else None,
            "available_affordances": {
                **static_caps,
                "native_relation_types_seen": list(native_relation_types_seen.keys()),
                "native_relation_types_count": len(native_relation_types_seen),
            },
            "used_affordances_articles": {
                "articles_with_any_relation": relation_populated_count / n_art,
                "articles_with_any_orcid": at_least_one_orcid / n_art,
                "articles_with_any_ror": at_least_one_ror / n_art,
                "articles_with_funder_id": funder_present / n_art,
                "per_native_relation_type_rate": per_type_rate,
            },
            "resolved_object_type_distribution": dict(resolved_counts),
            "resolution_tier_distribution": dict(tier_counts),
            "empirical_tier_indicator": _infer_empirical_tier(
                static_caps, len(native_relation_types_seen), per_type_rate
            ),
        }

    return profile


def _infer_empirical_tier(
    static_caps: dict[str, Any],
    n_native_relation_types: int,
    per_type_rate: dict[str, float],
) -> int:
    """Heuristic empirical tier based on what the adapter actually sees.

    - Tier 1: only dc:relation or no relations
    - Tier 2: some typed relations but sparse coverage
    - Tier 3: rich typed relations, common usage
    - Tier 4: tier 3 + funder/project identifiers populated
    """
    if not static_caps.get("permits_relations", False):
        return 1
    if not static_caps.get("permits_typed_relations", False):
        return 1
    if n_native_relation_types <= 1:
        return 1
    if n_native_relation_types <= 3:
        return 2
    mean_rate = sum(per_type_rate.values()) / max(len(per_type_rate), 1)
    if mean_rate >= 0.15 and static_caps.get("permits_funder", False):
        return 4
    return 3


def save_profile(profile: dict[str, Any], path: Path | str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2, sort_keys=True)


def compare_a_priori_and_empirical(profile: dict[str, Any]) -> list[dict[str, Any]]:
    """Return a list of ``{repo, a_priori, empirical, discrepancy}`` dicts.

    Any non-zero discrepancy is reported in methods; empirical tier is used as
    the primary tier indicator where they diverge.
    """
    out: list[dict[str, Any]] = []
    for repo, data in profile.items():
        a_priori = data.get("a_priori_tier")
        empirical = data.get("empirical_tier_indicator")
        out.append(
            {
                "repository": repo,
                "a_priori_tier": a_priori,
                "empirical_tier": empirical,
                "discrepancy": (a_priori or 0) - (empirical or 0),
            }
        )
    return out
