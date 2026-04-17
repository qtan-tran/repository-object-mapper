"""Tests for the OAI-PMH adapter.

Covers: oai_dc fallback, DataCite parsing, missing relations, malformed
records, deleted headers, and untyped relatedIdentifier handling.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from repository_object_mapper.adapters import AdapterConfig
from repository_object_mapper.adapters.oai_pmh import (
    OAIPMHAdapter,
    _guess_identifier_from_string,
    _strip_doi,
)


@pytest.fixture
def tmp_output(tmp_path: Path) -> Path:
    return tmp_path


def _make_adapter(
    name: str, formats: list[str], tier: int, tmp_output: Path
) -> OAIPMHAdapter:
    cfg = AdapterConfig(
        name=name,
        url="https://example.org/",
        type="oai_pmh",
        a_priori_tier=tier,
        endpoint="https://example.org/oai",
        metadata_formats=formats,
        sampling_method="systematic",
        random_seed=0,
        target_record_count=100,
        contact_email="test@example.org",
    )
    return OAIPMHAdapter(cfg, tmp_output, mock=True)


def test_strip_doi_variants() -> None:
    assert _strip_doi("https://doi.org/10.1/x") == "10.1/x"
    assert _strip_doi("doi:10.1/y") == "10.1/y"
    assert _strip_doi("10.1/z") == "10.1/z"


def test_guess_identifier_discriminates_schemes() -> None:
    assert _guess_identifier_from_string("https://doi.org/10.1/a").scheme == "doi"
    assert _guess_identifier_from_string("https://arxiv.org/abs/2307.00001").scheme == "arxiv"
    assert _guess_identifier_from_string("https://github.com/foo/bar").scheme == "url"
    assert _guess_identifier_from_string("some/local/id").scheme == "other"


def test_oai_dc_parses_mock_records(monkeypatch, tmp_output: Path) -> None:
    # Run against our generated tier1 mocks
    project_root = Path(__file__).resolve().parent.parent
    monkeypatch.chdir(project_root)

    adapter = _make_adapter(
        "tier1_dspace_example", ["oai_dc"], tier=1, tmp_output=tmp_output
    )
    records = list(adapter.harvest())
    assert len(records) > 0
    for r in records:
        assert r.repository_name == "tier1_dspace_example"
        assert r.schema_version == "0.2"
        # oai_dc has no ORCID
        assert r.presence.has_creator_orcid_field is False
        assert r.presence.has_relation_field is True


def test_datacite_parses_rich_records(monkeypatch, tmp_output: Path) -> None:
    project_root = Path(__file__).resolve().parent.parent
    monkeypatch.chdir(project_root)

    adapter = _make_adapter(
        "tier4_inveniordm_example",
        ["datacite4", "oai_datacite", "oai_dc"],
        tier=4,
        tmp_output=tmp_output,
    )
    records = list(adapter.harvest())
    assert records, "expected at least one record"

    # Tier 4 should expose richer presence flags
    rich = [r for r in records if r.presence.has_funder_field]
    assert rich, "at least one record should have funder field"

    # At least one record should have typed relations
    typed = [r for r in records if any(r.relations)]
    assert typed
    # Native relation labels preserved verbatim
    labels = {rel.native_relation_type for r in records for rel in r.relations}
    assert "IsSupplementTo" in labels


def test_malformed_datacite_handled_gracefully(
    monkeypatch, tmp_output: Path
) -> None:
    project_root = Path(__file__).resolve().parent.parent
    monkeypatch.chdir(project_root)

    adapter = _make_adapter(
        "tier2_datacite_partial",
        ["oai_datacite", "oai_dc"],
        tier=2,
        tmp_output=tmp_output,
    )
    # This should not raise despite the malformed fixture
    records = list(adapter.harvest())
    # At least the well-formed records return
    assert len(records) >= 10


def test_describe_capabilities_reflects_format(tmp_output: Path) -> None:
    poor = _make_adapter("tier1", ["oai_dc"], 1, tmp_output)
    rich = _make_adapter("tier4", ["datacite4", "oai_dc"], 4, tmp_output)
    poor_caps = poor.describe_capabilities()
    rich_caps = rich.describe_capabilities()
    assert poor_caps["permits_typed_relations"] is False
    assert rich_caps["permits_typed_relations"] is True
    assert rich_caps["permits_creator_orcid"] is True


def test_resumption_checkpoint_roundtrip(tmp_output: Path) -> None:
    adapter = _make_adapter("tier1", ["oai_dc"], 1, tmp_output)
    cp = adapter.load_checkpoint()
    cp.records_harvested = 42
    cp.last_cursor = "token123"
    adapter.save_checkpoint(cp)

    adapter2 = _make_adapter("tier1", ["oai_dc"], 1, tmp_output)
    cp2 = adapter2.load_checkpoint()
    assert cp2.records_harvested == 42
    assert cp2.last_cursor == "token123"


def test_deleted_records_are_dropped(monkeypatch, tmp_output: Path) -> None:
    project_root = Path(__file__).resolve().parent.parent
    monkeypatch.chdir(project_root)

    adapter = _make_adapter(
        "tier1_dspace_example", ["oai_dc"], tier=1, tmp_output=tmp_output
    )
    records = list(adapter.harvest())
    # The "deleted" mock should not appear in the parsed records
    ids = [r.local_identifier for r in records]
    assert "oai:tier1:deleted" not in ids
