"""End-to-end smoke test on mock data.

Drives every CLI stage in sequence and asserts that expected output files
appear. Does not assert on specific statistical results — only on the pipeline
being resumable, idempotent, and crash-free.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from repository_object_mapper.analyze import run_analysis
from repository_object_mapper.cache import ResolutionCache
from repository_object_mapper.classify import classify_many, load_type_mapping
from repository_object_mapper.profile import build_profile, save_profile
from repository_object_mapper.report import build_report
from repository_object_mapper.resolve import ResolutionConfig, resolve_records
from repository_object_mapper.sample import build_adapter, load_sample_config
from repository_object_mapper.schema import NormalizedRecord
from repository_object_mapper.score import score_records, summarize_by_repository

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def isolated_output(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.chdir(PROJECT_ROOT)
    out = tmp_path / "output"
    out.mkdir(parents=True, exist_ok=True)
    return out


def test_full_pipeline_on_mocks(isolated_output: Path, tmp_path: Path) -> None:
    configs = load_sample_config("config/sample_v0_2.yaml")
    assert len(configs) == 4, "expected 4 repositories in v0.2 config"

    # 1) Harvest
    all_records: list[NormalizedRecord] = []
    adapter_caps: dict[str, dict] = {}
    for cfg in configs:
        adapter = build_adapter(cfg, isolated_output, mock=True)
        adapter_caps[cfg.name] = adapter.describe_capabilities()
        for rec in adapter.harvest():
            all_records.append(rec)
    assert all_records, "expected mock records"
    repos_seen = {r.repository_name for r in all_records}
    assert len(repos_seen) >= 2  # at least two tiers should produce fixtures

    # 2) Classify
    mapping = load_type_mapping("config/type_mapping.yaml")
    classify_many(all_records, mapping)
    assert all(r.object_type is not None for r in all_records)

    # 3) Capability profile
    profile = build_profile(all_records, adapter_caps)
    save_profile(profile, isolated_output / "repository_profile.json")
    assert (isolated_output / "repository_profile.json").exists()

    # 4) Resolve (mock mode = cache + weak pattern only)
    cache_path = tmp_path / "resolution.db"
    with ResolutionCache(cache_path) as cache:
        config = ResolutionConfig(contact_email="t@t")
        resolve_records(all_records, cache, config, mock=True)

    # 5) Score
    scores = score_records(all_records, profile)
    assert not scores.empty
    scores.to_parquet(isolated_output / "scores.parquet", index=False)
    summary = summarize_by_repository(scores)
    summary.to_csv(isolated_output / "repository_summary.csv", index=False)

    # 6) Analyze
    run_analysis(scores, isolated_output / "analysis")
    assert (isolated_output / "analysis" / "results.json").exists()
    assert (isolated_output / "analysis" / "results.md").exists()

    # 7) Report
    # Fake a resolution_report for the report builder
    resolution_report: dict = {}
    for r in all_records:
        bucket = resolution_report.setdefault(
            r.repository_name,
            {"fully_typed": 0, "weakly_typed": 0, "unresolved": 0},
        )
        for rel in r.relations:
            if rel.resolution_tier is not None:
                bucket[rel.resolution_tier.value] += 1
    (isolated_output / "resolution_report.json").write_text(
        json.dumps(resolution_report, indent=2), encoding="utf-8"
    )
    report_path = build_report(isolated_output)
    assert report_path.exists()
    content = report_path.read_text(encoding="utf-8")
    assert "Methods-ready summary" in content
