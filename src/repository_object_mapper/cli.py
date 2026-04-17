"""Typer-based CLI for the pipeline.

Each subcommand is idempotent and independently runnable. State lives in
``output/`` and ``data/cache/``; rerunning a stage never corrupts prior
results.

Example (full pipeline on mocks)::

    rom harvest --config config/sample_v0_2.yaml --mock
    rom classify
    rom resolve-pilot --mock
    rom resolve --mock
    rom score
    rom analyze
    rom visualize
    rom report
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import structlog
import typer

from .analyze import run_analysis
from .cache import ResolutionCache
from .classify import classify_many, disagreement_rate, load_type_mapping
from .logging_config import configure as configure_logging
from .profile import build_profile, compare_a_priori_and_empirical, save_profile
from .report import build_report
from .resolve import ResolutionConfig, resolve_records, run_resolution_pilot
from .sample import build_adapter, load_sample_config, summarize_sampling_frame
from .schema import NormalizedRecord
from .score import score_records, summarize_by_repository
from .visualize import run_visualizations

app = typer.Typer(no_args_is_help=True, add_completion=False)
log = structlog.get_logger(__name__)


OUTPUT_DIR = Path("output")
DATA_DIR = Path("data")
CONFIG_DEFAULT = Path("config/sample_v0_2.yaml")
TYPE_MAPPING_DEFAULT = Path("config/type_mapping.yaml")
CACHE_DEFAULT = Path("data/cache/resolution.db")


# -- Helpers -----------------------------------------------------------------


def _records_path() -> Path:
    return OUTPUT_DIR / "records_normalized.parquet"


def _relations_path() -> Path:
    return OUTPUT_DIR / "relations.parquet"


def _scores_path() -> Path:
    return OUTPUT_DIR / "scores.parquet"


def _profile_path() -> Path:
    return OUTPUT_DIR / "repository_profile.json"


def _records_to_df(records: list[NormalizedRecord]) -> pd.DataFrame:
    rows = []
    for r in records:
        rows.append(
            {
                "schema_version": r.schema_version,
                "repository": r.repository_name,
                "tier": r.repository_a_priori_tier,
                "local_id": r.local_identifier,
                "raw_path": r.raw_path,
                "title": r.title,
                "declared_type_raw": r.declared_type_raw,
                "object_type": r.object_type.value if r.object_type else None,
                "object_type_confidence": (
                    r.object_type_confidence.value if r.object_type_confidence else None
                ),
                "type_disagreement": r.type_disagreement,
                "n_creators": len(r.creators),
                "n_creators_with_orcid": sum(1 for c in r.creators if c.orcid),
                "n_funders_with_id": sum(1 for f in r.funders if f.funder_id),
                "n_relations": len(r.relations),
                "record_json": r.model_dump_json(),
            }
        )
    return pd.DataFrame(rows)


def _records_from_df(df: pd.DataFrame) -> list[NormalizedRecord]:
    return [NormalizedRecord.model_validate_json(j) for j in df["record_json"]]


def _relations_to_df(records: list[NormalizedRecord]) -> pd.DataFrame:
    rows = []
    for r in records:
        for rel in r.relations:
            rows.append(
                {
                    "repository": r.repository_name,
                    "local_id": r.local_identifier,
                    "native_relation_type": rel.native_relation_type,
                    "target_scheme": rel.target_identifier.scheme,
                    "target_value": rel.target_identifier.value,
                    "resolved_object_type": (
                        rel.resolved_object_type.value if rel.resolved_object_type else None
                    ),
                    "resolution_tier": (
                        rel.resolution_tier.value if rel.resolution_tier else None
                    ),
                }
            )
    return pd.DataFrame(rows)


# -- Subcommands -------------------------------------------------------------


@app.command("sample")
def sample_cmd(
    config: Path = typer.Option(CONFIG_DEFAULT, "--config", "-c", exists=True),
    log_level: str = typer.Option("INFO"),
) -> None:
    """Validate and summarize the sampling frame."""
    configure_logging(log_level)
    configs = load_sample_config(config)
    summary = summarize_sampling_frame(configs)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "sampling_frame.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    typer.echo(json.dumps(summary, indent=2, default=str))


@app.command("harvest")
def harvest_cmd(
    config: Path = typer.Option(CONFIG_DEFAULT, "--config", "-c", exists=True),
    mock: bool = typer.Option(False, "--mock/--live"),
    log_level: str = typer.Option("INFO"),
) -> None:
    """Run adapters, normalize records, and emit the capability profile."""
    configure_logging(log_level)
    configs = load_sample_config(config)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    all_records: list[NormalizedRecord] = []
    adapter_caps: dict[str, dict] = {}
    for cfg in configs:
        adapter = build_adapter(cfg, OUTPUT_DIR, mock=mock)
        adapter_caps[cfg.name] = adapter.describe_capabilities()
        count = 0
        for rec in adapter.harvest():
            all_records.append(rec)
            count += 1
        log.info("adapter_complete", repository=cfg.name, records=count)

    # Persist normalized records
    df = _records_to_df(all_records)
    df.to_parquet(_records_path(), index=False)

    # Preliminary profile (types not classified yet — will be refined by classify step)
    profile = build_profile(all_records, adapter_caps)
    save_profile(profile, _profile_path())
    typer.echo(f"Harvest complete: {len(all_records)} records across {len(configs)} repositories.")


@app.command("classify")
def classify_cmd(
    mapping: Path = typer.Option(TYPE_MAPPING_DEFAULT, "--mapping", "-m", exists=True),
    log_level: str = typer.Option("INFO"),
) -> None:
    """Apply hierarchical object-type classification."""
    configure_logging(log_level)
    df = pd.read_parquet(_records_path())
    records = _records_from_df(df)

    mapping_data = load_type_mapping(mapping)
    classify_many(records, mapping_data)

    # Persist re-serialized records
    df2 = _records_to_df(records)
    df2.to_parquet(_records_path(), index=False)

    # Emit relations parquet (pre-resolution; resolved fields will be filled later)
    rel_df = _relations_to_df(records)
    rel_df.to_parquet(_relations_path(), index=False)

    # Update capability profile now that we know which records are articles
    with open(_profile_path(), encoding="utf-8") as f:
        existing = json.load(f)
    caps = {
        repo: d.get("available_affordances", {})
        for repo, d in existing.items()
    }
    # build_profile expects the adapter-describe shape; the stored "available_affordances"
    # contains the same keys plus `native_relation_types_seen` — pass through.
    profile = build_profile(records, {k: {**v} for k, v in caps.items()})
    save_profile(profile, _profile_path())

    disagreement = disagreement_rate(records)
    (OUTPUT_DIR / "classification_disagreement.json").write_text(
        json.dumps(disagreement, indent=2), encoding="utf-8"
    )
    typer.echo(f"Classified {len(records)} records. Disagreement rates: {disagreement}")


@app.command("resolve-pilot")
def resolve_pilot_cmd(
    n: int = typer.Option(500, "-n"),
    mock: bool = typer.Option(False, "--mock/--live"),
    contact_email: str = typer.Option("user@example.org"),
    log_level: str = typer.Option("INFO"),
) -> None:
    """Run the 500-identifier resolution pilot described in the spec."""
    configure_logging(log_level)
    df = pd.read_parquet(_records_path())
    records = _records_from_df(df)
    cache = ResolutionCache(CACHE_DEFAULT)
    config = ResolutionConfig(contact_email=contact_email)
    summary = run_resolution_pilot(records, cache, config, n=n, mock=mock)
    cache.close()

    pilot_doc = Path("docs/resolution_pilot.md")
    pilot_doc.parent.mkdir(parents=True, exist_ok=True)
    pilot_doc.write_text(
        _render_pilot_md(summary, mock=mock), encoding="utf-8"
    )
    typer.echo(json.dumps(summary, indent=2))


def _render_pilot_md(summary: dict, *, mock: bool) -> str:
    mode = "mock" if mock else "live"
    return (
        "# Resolution pilot\n\n"
        f"Mode: **{mode}**  \n"
        f"Sample size: {summary['sample_size']}\n\n"
        "| tier | count | rate |\n"
        "|---|---|---|\n"
        f"| fully_typed | {summary['fully_typed']} | {summary['fully_typed_rate']:.2%} |\n"
        f"| weakly_typed | {summary['weakly_typed']} | {summary['weakly_typed_rate']:.2%} |\n"
        f"| unresolved | {summary['unresolved']} | {summary['unresolved_rate']:.2%} |\n"
        f"\nURL-only share of unresolved: {summary['url_only_unresolved_rate']:.2%}\n\n"
        "## Interpretation\n\n"
        "If the fully-typed rate is materially below expectation (e.g., <50%), "
        "object embeddedness claims must be conditioned on resolution tier. "
        "Sensitivity analyses under the ``fully_only`` and ``fully_and_weakly`` "
        "inclusion policies are reported in ``output/analysis/``.\n"
    )


@app.command("resolve")
def resolve_cmd(
    mock: bool = typer.Option(False, "--mock/--live"),
    contact_email: str = typer.Option("user@example.org"),
    log_level: str = typer.Option("INFO"),
) -> None:
    """Run full identifier resolution against the cache."""
    configure_logging(log_level)
    df = pd.read_parquet(_records_path())
    records = _records_from_df(df)
    cache = ResolutionCache(CACHE_DEFAULT)
    config = ResolutionConfig(contact_email=contact_email)
    resolve_records(records, cache, config, mock=mock)

    # Persist re-serialized records and relations
    df2 = _records_to_df(records)
    df2.to_parquet(_records_path(), index=False)
    rel_df = _relations_to_df(records)
    rel_df.to_parquet(_relations_path(), index=False)

    # Emit resolution report keyed by repository
    resolution_report = {}
    for r in records:
        bucket = resolution_report.setdefault(
            r.repository_name,
            {"fully_typed": 0, "weakly_typed": 0, "unresolved": 0},
        )
        for rel in r.relations:
            if rel.resolution_tier is None:
                continue
            bucket[rel.resolution_tier.value] += 1
    (OUTPUT_DIR / "resolution_report.json").write_text(
        json.dumps(resolution_report, indent=2), encoding="utf-8"
    )
    typer.echo(json.dumps(cache.count_by_tier(), indent=2))
    cache.close()


@app.command("score")
def score_cmd(log_level: str = typer.Option("INFO")) -> None:
    """Compute embeddedness dimensions (raw and available-adjusted)."""
    configure_logging(log_level)
    df = pd.read_parquet(_records_path())
    records = _records_from_df(df)
    with open(_profile_path(), encoding="utf-8") as f:
        profile = json.load(f)
    scores = score_records(records, profile)
    scores.to_parquet(_scores_path(), index=False)

    summary = summarize_by_repository(scores)
    summary.to_csv(OUTPUT_DIR / "repository_summary.csv", index=False)

    # Capability discrepancy report
    discrepancies = compare_a_priori_and_empirical(profile)
    (OUTPUT_DIR / "tier_discrepancies.json").write_text(
        json.dumps(discrepancies, indent=2), encoding="utf-8"
    )
    typer.echo(f"Scored {len(scores)} records.")


@app.command("analyze")
def analyze_cmd(log_level: str = typer.Option("INFO")) -> None:
    """Run exploratory H2 tests and within-repository object-type comparison."""
    configure_logging(log_level)
    scores = pd.read_parquet(_scores_path())
    run_analysis(scores, OUTPUT_DIR / "analysis")
    typer.echo("Analysis complete: output/analysis/results.{json,md}")


@app.command("visualize")
def visualize_cmd(log_level: str = typer.Option("INFO")) -> None:
    """Generate all paper figures."""
    configure_logging(log_level)
    scores = pd.read_parquet(_scores_path())
    df = pd.read_parquet(_records_path())
    records = _records_from_df(df)
    with open(_profile_path(), encoding="utf-8") as f:
        profile = json.load(f)
    paths = run_visualizations(scores, records, profile, OUTPUT_DIR / "figures")
    typer.echo(f"Produced {len(paths)} figures in output/figures/")


@app.command("report")
def report_cmd(log_level: str = typer.Option("INFO")) -> None:
    """Assemble methods-ready summary."""
    configure_logging(log_level)
    path = build_report(OUTPUT_DIR)
    typer.echo(f"Report written to {path}")


if __name__ == "__main__":
    app()
