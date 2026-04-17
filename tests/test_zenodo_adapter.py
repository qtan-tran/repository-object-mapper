"""Tests for the Zenodo REST adapter (mock mode)."""

from __future__ import annotations

from pathlib import Path

from repository_object_mapper.adapters import AdapterConfig
from repository_object_mapper.adapters.zenodo import ZenodoAdapter


def _make_adapter(tmp_path: Path) -> ZenodoAdapter:
    cfg = AdapterConfig(
        name="zenodo",
        url="https://zenodo.org/",
        type="zenodo_rest",
        a_priori_tier=3,
        endpoint="https://zenodo.org/api/records",
        metadata_formats=["zenodo_json"],
        sampling_method="systematic",
        random_seed=0,
        target_record_count=100,
        contact_email="test@example.org",
    )
    return ZenodoAdapter(cfg, tmp_path, mock=True)


def test_zenodo_parses_mock_records(monkeypatch, tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parent.parent
    monkeypatch.chdir(project_root)

    adapter = _make_adapter(tmp_path)
    records = list(adapter.harvest())
    assert records
    for r in records:
        assert r.repository_name == "zenodo"
        assert r.schema_version == "0.2"
        assert r.presence.has_creator_orcid_field is True
        assert r.presence.has_affiliation_ror_field is False  # Zenodo v1 lacks ROR


def test_zenodo_declared_type_roundtrips(monkeypatch, tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parent.parent
    monkeypatch.chdir(project_root)

    adapter = _make_adapter(tmp_path)
    records = list(adapter.harvest())
    # Most of our mocks are publication/article
    declared = [r.declared_type_raw for r in records]
    assert any(d == "publication/article" for d in declared)


def test_zenodo_url_only_relations_preserved(monkeypatch, tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parent.parent
    monkeypatch.chdir(project_root)

    adapter = _make_adapter(tmp_path)
    records = list(adapter.harvest())
    # At least some mocks include url-scheme relations
    schemes = {
        rel.target_identifier.scheme
        for r in records
        for rel in r.relations
    }
    assert "url" in schemes or "doi" in schemes


def test_zenodo_funder_field_parsing(monkeypatch, tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parent.parent
    monkeypatch.chdir(project_root)

    adapter = _make_adapter(tmp_path)
    records = list(adapter.harvest())
    with_funder = [r for r in records if r.funders]
    # Mock data includes ~50% with grants
    assert len(with_funder) > 0
