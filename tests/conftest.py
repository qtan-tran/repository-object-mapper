"""Shared pytest fixtures."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from repository_object_mapper.schema import (
    Affiliation,
    Creator,
    FieldPresenceFlags,
    Funder,
    HarvestProvenance,
    Identifier,
    NormalizedRecord,
    Relation,
    ResolutionTier,
    ObjectType,
)


@pytest.fixture
def provenance() -> HarvestProvenance:
    return HarvestProvenance(
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        endpoint="mock://",
        format_negotiated="mock",
        adapter_name="mock",
        adapter_version="0.0.0",
    )


@pytest.fixture
def simple_article(provenance: HarvestProvenance) -> NormalizedRecord:
    return NormalizedRecord(
        repository_name="repo_a",
        repository_a_priori_tier=3,
        local_identifier="rec-1",
        raw_path="data/mock/rec-1.xml",
        provenance=provenance,
        identifiers=[Identifier(scheme="doi", value="10.1234/a.1")],
        title="An article",
        declared_type_raw="JournalArticle",
        creators=[
            Creator(
                name="Author, A",
                orcid="0000-0001-0000-0001",
                affiliations=[Affiliation(name="U", ror="https://ror.org/0abcd1234")],
            )
        ],
        funders=[Funder(name="NSF", funder_id="10.13039/100000001", project_id="P123")],
        relations=[
            Relation(
                native_relation_type="IsSupplementTo",
                target_identifier=Identifier(scheme="doi", value="10.1234/dataset.1"),
                resolved_object_type=ObjectType.DATASET,
                resolution_tier=ResolutionTier.FULLY_TYPED,
            ),
            Relation(
                native_relation_type="IsVersionOf",
                target_identifier=Identifier(scheme="arxiv", value="2307.00001"),
                resolved_object_type=ObjectType.PREPRINT,
                resolution_tier=ResolutionTier.WEAKLY_TYPED,
            ),
        ],
        presence=FieldPresenceFlags(
            has_relation_field=True,
            has_creator_orcid_field=True,
            has_affiliation_ror_field=True,
            has_funder_field=True,
        ),
    )


@pytest.fixture
def bare_article(provenance: HarvestProvenance) -> NormalizedRecord:
    return NormalizedRecord(
        repository_name="repo_b",
        repository_a_priori_tier=1,
        local_identifier="rec-2",
        raw_path="data/mock/rec-2.xml",
        provenance=provenance,
        identifiers=[Identifier(scheme="handle", value="hdl:1/2")],
        title="A bare article",
        declared_type_raw="Text",
        creators=[Creator(name="Someone")],
        funders=[],
        relations=[],
        presence=FieldPresenceFlags(has_relation_field=True),
    )


@pytest.fixture
def mock_root() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "mock"
