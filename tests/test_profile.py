"""Tests for the capability profile generator."""

from __future__ import annotations

from repository_object_mapper.profile import (
    build_profile,
    compare_a_priori_and_empirical,
)
from repository_object_mapper.schema import NormalizedRecord, ObjectType


def test_profile_separates_available_from_used(
    simple_article: NormalizedRecord, bare_article: NormalizedRecord
) -> None:
    # Both are "articles" for profiling purposes
    simple_article.object_type = ObjectType.ARTICLE
    bare_article.object_type = ObjectType.ARTICLE

    profile = build_profile(
        [simple_article, bare_article],
        adapter_capabilities={
            "repo_a": {
                "permits_relations": True,
                "permits_typed_relations": True,
                "permits_creator_orcid": True,
                "permits_funder": True,
            },
            "repo_b": {
                "permits_relations": True,
                "permits_typed_relations": False,
            },
        },
    )
    assert "repo_a" in profile
    assert "repo_b" in profile

    # Used: repo_a article populates relations; repo_b article does not
    assert profile["repo_a"]["used_affordances_articles"][
        "articles_with_any_relation"
    ] == 1.0
    assert profile["repo_b"]["used_affordances_articles"][
        "articles_with_any_relation"
    ] == 0.0

    # Available: repo_a exposes relation types; repo_b is poorer
    a_types = profile["repo_a"]["available_affordances"]["native_relation_types_count"]
    b_types = profile["repo_b"]["available_affordances"]["native_relation_types_count"]
    assert a_types > b_types


def test_empirical_tier_inference(
    simple_article: NormalizedRecord, bare_article: NormalizedRecord
) -> None:
    simple_article.object_type = ObjectType.ARTICLE
    bare_article.object_type = ObjectType.ARTICLE

    profile = build_profile(
        [simple_article, bare_article],
        adapter_capabilities={
            "repo_a": {
                "permits_relations": True,
                "permits_typed_relations": True,
                "permits_funder": True,
            },
            "repo_b": {
                "permits_relations": True,
                "permits_typed_relations": False,
            },
        },
    )
    # repo_b has no typed relations → tier 1
    assert profile["repo_b"]["empirical_tier_indicator"] == 1


def test_compare_discrepancy_detection(
    simple_article: NormalizedRecord, bare_article: NormalizedRecord
) -> None:
    simple_article.object_type = ObjectType.ARTICLE
    bare_article.object_type = ObjectType.ARTICLE

    profile = build_profile(
        [simple_article, bare_article],
        adapter_capabilities={
            "repo_a": {"permits_relations": True, "permits_typed_relations": True},
            "repo_b": {"permits_relations": True, "permits_typed_relations": False},
        },
    )
    comp = compare_a_priori_and_empirical(profile)
    # bare_article is tier 1 (a_priori) and is classified as tier 1 empirically
    repo_b = next(e for e in comp if e["repository"] == "repo_b")
    assert repo_b["discrepancy"] == 0
