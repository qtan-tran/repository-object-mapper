"""Assemble a methods-ready Markdown summary (``output/report.md``).

Pulls together the capability profile, classification validation, scoring
statistics, and analysis results into a single document that can be pasted
near-verbatim into the methods section of the JDoc submission.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def build_report(output_dir: Path | str) -> Path:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # Load artifacts if present
    profile = _safe_load_json(out / "repository_profile.json", default={})
    validation = _safe_load_json(out / "classification_validation.json", default={})
    resolution = _safe_load_json(out / "resolution_report.json", default={})
    analysis = _safe_load_json(out / "analysis" / "results.json", default={})

    lines: list[str] = [
        "# Methods-ready summary — v0.2",
        "",
        "This document is auto-assembled from pipeline outputs. It contains the",
        "minimum text and tables needed to describe the harvest, classification,",
        "resolution, scoring, and analysis stages for the JDoc paper.",
        "",
        "## 1. Sampling and harvest",
        "",
        f"Repositories harvested: **{len(profile)}** "
        f"(target ~1,500 article records per repository at v0.2).",
        "",
    ]

    # Capability profile summary
    lines.append("## 2. Capability profile (available vs used affordances)")
    lines.append("")
    lines.append(
        "| Repository | tier (a priori) | tier (empirical) | n records | n articles | "
        "relation types seen | % articles w/ relation | % articles w/ ORCID | "
        "% articles w/ ROR | % articles w/ funder ID |"
    )
    lines.append(
        "|---|---|---|---|---|---|---|---|---|---|"
    )
    for repo, data in profile.items():
        used = data.get("used_affordances_articles", {})
        avail = data.get("available_affordances", {})
        lines.append(
            f"| {repo} | {data.get('a_priori_tier')} | "
            f"{data.get('empirical_tier_indicator')} | "
            f"{data.get('n_records_total')} | {data.get('n_article_records')} | "
            f"{avail.get('native_relation_types_count', 0)} | "
            f"{used.get('articles_with_any_relation', 0):.2%} | "
            f"{used.get('articles_with_any_orcid', 0):.2%} | "
            f"{used.get('articles_with_any_ror', 0):.2%} | "
            f"{used.get('articles_with_funder_id', 0):.2%} |"
        )
    lines.append("")

    # Classification validation
    lines.append("## 3. Classification validation")
    lines.append("")
    if validation:
        lines.append(f"- Validation set size: {validation.get('n', 'n/a')}")
        lines.append(f"- Overall accuracy: {validation.get('accuracy', 0):.2%}")
        for repo, acc in (validation.get("per_repository_accuracy") or {}).items():
            lines.append(f"  - {repo}: {acc:.2%}")
    else:
        lines.append("_No manual validation artifact found._")
    lines.append("")

    # Resolution report
    lines.append("## 4. Resolution report")
    lines.append("")
    if resolution:
        for repo, d in resolution.items():
            if not isinstance(d, dict):
                continue
            lines.append(
                f"- **{repo}**: fully={d.get('fully_typed', 0)}, "
                f"weakly={d.get('weakly_typed', 0)}, "
                f"unresolved={d.get('unresolved', 0)}"
            )
    else:
        lines.append("_No resolution report found._")
    lines.append("")

    # Analysis
    lines.append("## 5. Analysis summary")
    lines.append("")
    cross = analysis.get("cross_tier", {})
    within = analysis.get("within_repository", {})
    if cross:
        lines.append("### Cross-tier (exploratory)")
        for col, res in cross.items():
            if res.get("skipped"):
                continue
            lines.append(
                f"- {col}: H={res['H']:.3f}, p={res['p_value']:.4g}, "
                f"ε²={res.get('epsilon_squared'):.3f}, n={res.get('n_total')}"
            )
    if within:
        lines.append("")
        lines.append("### Within-repository object-type comparisons (primary)")
        for col, per_repo in within.items():
            for repo, res in per_repo.items():
                if res.get("test") == "skipped":
                    continue
                pw = res.get("pairwise", {}).get("article_vs_dataset", {})
                if not pw or pw.get("test") == "skipped":
                    continue
                lines.append(
                    f"- {repo} [{col}]: articles vs datasets: "
                    f"U={pw['U']:.0f}, p={pw['p_value']:.4g}, "
                    f"rank-biserial={pw['rank_biserial']:.3f}, "
                    f"article-lower={pw['article_lower_than_other']}"
                )
    lines.append("")
    lines.append("## 6. Limitations")
    lines.append("")
    lines.append(
        "- v0.2 has n=4 repositories; cross-tier test is exploratory. "
        "Within-repository comparisons are the statistically defensible test."
    )
    lines.append(
        "- Measured differences may reflect schema capacity, repository "
        "curation policy, or depositor behavior; see ``docs/repository_context.md``."
    )
    lines.append(
        "- Findings concern repository metadata representation only — no "
        "longitudinal, citation, or reading-behavior claims."
    )
    report_path = out / "report.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


def _safe_load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default
