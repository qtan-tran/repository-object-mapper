"""Scoring tests with hand-calculated expected values.

Each dimension's formula is spelled out in ``docs/scoring.md`` — these tests
are the executable counterpart. Any change here must also update the doc.
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from repository_object_mapper.profile import build_profile
from repository_object_mapper.schema import NormalizedRecord
from repository_object_mapper.score import (
    _agent_raw,
    _object_link_stats,
    _relation_count_and_distinct,
    _relational_adjusted,
    score_records,
)


def test_relation_count_and_distinct(simple_article: NormalizedRecord) -> None:
    n, distinct = _relation_count_and_distinct(simple_article.relations)
    assert n == 2
    assert distinct == 2  # IsSupplementTo, IsVersionOf


def test_relational_raw_hand_calculation(simple_article: NormalizedRecord) -> None:
    # Expected: log(1 + 2) + 2/10 = log(3) + 0.2
    n, d = _relation_count_and_distinct(simple_article.relations)
    expected = math.log1p(n) + d / 10.0
    assert math.isclose(expected, math.log1p(2) + 0.2)


def test_agent_raw_all_components(simple_article: NormalizedRecord) -> None:
    # simple_article: 1/1 creators have ORCID, 1 ROR, 1 funder_id, 1 project_id
    # Expected mean = (1 + 1 + 1 + 1) / 4 = 1.0
    assert _agent_raw(simple_article) == pytest.approx(1.0)


def test_agent_raw_bare(bare_article: NormalizedRecord) -> None:
    # No ORCID, no ROR, no funder, no project → mean of zeros
    assert _agent_raw(bare_article) == pytest.approx(0.0)


def test_object_stats_fully_only_vs_inclusive(simple_article: NormalizedRecord) -> None:
    n_f, d_f = _object_link_stats(simple_article.relations, "fully_only")
    n_fw, d_fw = _object_link_stats(simple_article.relations, "fully_and_weakly")
    # Only the IsSupplementTo relation is FULLY_TYPED
    assert n_f == 1 and d_f == 1
    # Both are counted under fully+weakly
    assert n_fw == 2 and d_fw == 2


def test_relational_adjusted_ratio(simple_article: NormalizedRecord) -> None:
    # 2 distinct observed / 4 available ⇒ 0.5
    assert _relational_adjusted(simple_article, 4) == 0.5
    # Division-by-zero safety
    assert _relational_adjusted(simple_article, 0) == 0.0


def test_score_records_end_to_end_with_profile(
    simple_article: NormalizedRecord, bare_article: NormalizedRecord
) -> None:
    records = [simple_article, bare_article]
    profile = build_profile(
        records,
        adapter_capabilities={
            "repo_a": {
                "permits_relations": True,
                "permits_creator_orcid": True,
                "permits_affiliation_ror": True,
                "permits_funder": True,
                "permits_typed_relations": True,
            },
            "repo_b": {
                "permits_relations": True,
                "permits_creator_orcid": False,
                "permits_affiliation_ror": False,
                "permits_funder": False,
                "permits_typed_relations": False,
            },
        },
    )
    df = score_records(records, profile)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2
    # Min-max normalized columns in [0,1]
    for col in (
        "relational_raw_norm",
        "object_raw_fully_norm",
        "object_raw_fully_weakly_norm",
    ):
        assert df[col].between(0, 1).all()

    # simple_article should have a higher overall embeddedness than bare_article
    s = df.set_index("record_id")
    assert (
        s.loc["rec-1", "overall_embeddedness_score"]
        > s.loc["rec-2", "overall_embeddedness_score"]
    )

    # Legacy inverse
    for col in ("article_autonomy_score",):
        assert df[col].between(0, 1).all()


def test_minmax_all_identical_is_zero(simple_article: NormalizedRecord) -> None:
    # Only one record in the corpus ⇒ min == max ⇒ normalized = 0
    profile = build_profile(
        [simple_article],
        adapter_capabilities={"repo_a": {}},
    )
    df = score_records([simple_article], profile)
    assert df["relational_raw_norm"].iloc[0] == 0.0
