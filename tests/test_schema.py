"""Schema sanity tests — catch accidental model drift."""

from __future__ import annotations

import json

from repository_object_mapper import SCHEMA_VERSION
from repository_object_mapper.schema import (
    FieldPresenceFlags,
    NormalizedRecord,
    ObjectType,
)


def test_schema_version_constant_on_every_record(simple_article: NormalizedRecord) -> None:
    assert simple_article.schema_version == "0.2"
    assert SCHEMA_VERSION == "0.2"


def test_presence_defaults_all_false() -> None:
    flags = FieldPresenceFlags()
    for attr in (
        "has_relation_field",
        "has_creator_orcid_field",
        "has_affiliation_ror_field",
        "has_funder_field",
        "has_license_field",
        "has_subject_field",
        "has_fulltext_indicator_field",
    ):
        assert getattr(flags, attr) is False


def test_record_roundtrips_json(simple_article: NormalizedRecord) -> None:
    payload = simple_article.model_dump_json()
    rebuilt = NormalizedRecord.model_validate_json(payload)
    assert rebuilt == simple_article


def test_object_type_enum_values() -> None:
    # The closed vocabulary must not drift — analysis code depends on it.
    expected = {
        "article", "dataset", "thesis", "software", "book", "book_chapter",
        "preprint", "conference_paper", "report", "supplementary_material", "other",
    }
    assert {o.value for o in ObjectType} == expected


def test_extras_is_a_dict(bare_article: NormalizedRecord) -> None:
    # Should be safe to assign arbitrary debug context
    bare_article.extras["debug"] = {"note": "anything"}
    reparsed = NormalizedRecord.model_validate(json.loads(bare_article.model_dump_json()))
    assert reparsed.extras["debug"] == {"note": "anything"}
