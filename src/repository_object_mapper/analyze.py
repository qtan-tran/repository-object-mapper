"""Statistical analysis for H2 exploratory test and within-repository comparison.

For v0.2 (n=4 repositories), cross-tier tests are descriptive and
exploratory. The **primary statistically defensible test** is the
within-repository object-type comparison: do articles exhibit lower
embeddedness than datasets or software *within the same repository*?
With hundreds to thousands of records per repository, this is
genuinely powered.

Both raw and available-adjusted scores are analyzed separately.
Results are emitted as machine-readable JSON and human-readable Markdown.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats


@dataclass
class AnalysisResult:
    cross_tier: dict[str, Any]
    within_repository: dict[str, Any]
    bootstrap_ci: dict[str, Any]


def bootstrap_ci(
    values: np.ndarray, n_boot: int = 2000, ci: float = 0.95, seed: int = 42
) -> tuple[float, float]:
    """Nonparametric bootstrap CI on the mean."""
    if len(values) == 0:
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    boots = np.empty(n_boot)
    n = len(values)
    for i in range(n_boot):
        sample = rng.choice(values, size=n, replace=True)
        boots[i] = float(np.mean(sample))
    lo = float(np.quantile(boots, (1 - ci) / 2))
    hi = float(np.quantile(boots, 1 - (1 - ci) / 2))
    return lo, hi


def per_repository_bootstrap(
    scores_articles: pd.DataFrame,
    score_columns: list[str],
) -> dict[str, Any]:
    """Per-repository mean and 95% bootstrap CI for each scoring column."""
    out: dict[str, Any] = {}
    for repo, group in scores_articles.groupby("repository"):
        out[repo] = {"n": int(len(group)), "tier": int(group["tier"].iloc[0])}
        for col in score_columns:
            vals = group[col].dropna().to_numpy(dtype=float)
            lo, hi = bootstrap_ci(vals)
            out[repo][col] = {
                "mean": float(np.mean(vals)) if len(vals) else float("nan"),
                "ci_low": lo,
                "ci_high": hi,
            }
    return out


def kruskal_across_tiers(
    scores_articles: pd.DataFrame,
    column: str,
) -> dict[str, Any]:
    """Kruskal-Wallis across a priori tiers on one scoring column.

    With n=4 repositories this test is exploratory and underpowered; the
    epsilon-squared effect size is reported alongside p-value.
    """
    groups = [
        group[column].dropna().to_numpy(dtype=float)
        for _, group in scores_articles.groupby("tier")
        if len(group) > 0
    ]
    if len(groups) < 2 or all(len(g) == 0 for g in groups):
        return {"test": "kruskal_wallis", "skipped": True}

    try:
        h, p = stats.kruskal(*groups)
    except ValueError:
        return {"test": "kruskal_wallis", "skipped": True, "reason": "degenerate groups"}

    n = sum(len(g) for g in groups)
    # Epsilon-squared for Kruskal-Wallis (Tomczak & Tomczak, 2014)
    eps_sq = (float(h) - len(groups) + 1) / (n - len(groups)) if n > len(groups) else float("nan")
    return {
        "test": "kruskal_wallis",
        "column": column,
        "H": float(h),
        "p_value": float(p),
        "n_groups": len(groups),
        "n_total": n,
        "epsilon_squared": eps_sq,
        "power_caveat": (
            "Cross-tier test is exploratory at v0.2 (n=4 repositories). "
            "Not statistically decisive."
        ),
    }


def within_repository_object_type_comparison(
    all_scores: pd.DataFrame,
    column: str,
) -> dict[str, Any]:
    """For each repository, compare articles vs datasets vs software.

    Kruskal-Wallis per repository, with epsilon-squared effect size and
    pairwise article-vs-other summaries. This is the primary test for v0.2.
    """
    out: dict[str, Any] = {}
    for repo, group in all_scores.groupby("repository"):
        target_types = ["article", "dataset", "software"]
        subsets = [
            group[group["object_type"] == t][column].dropna().to_numpy(dtype=float)
            for t in target_types
        ]
        non_empty = [(t, s) for t, s in zip(target_types, subsets) if len(s) > 0]

        repo_result: dict[str, Any] = {
            "n_articles": int((group["object_type"] == "article").sum()),
            "n_datasets": int((group["object_type"] == "dataset").sum()),
            "n_software": int((group["object_type"] == "software").sum()),
            "column": column,
        }

        if len(non_empty) < 2:
            repo_result["test"] = "skipped"
            repo_result["reason"] = "fewer than 2 object-type groups"
            out[repo] = repo_result
            continue

        try:
            h, p = stats.kruskal(*[s for _, s in non_empty])
        except ValueError:
            repo_result["test"] = "skipped"
            repo_result["reason"] = "degenerate"
            out[repo] = repo_result
            continue

        n = sum(len(s) for _, s in non_empty)
        k = len(non_empty)
        eps_sq = (float(h) - k + 1) / (n - k) if n > k else float("nan")

        # Pairwise: article vs each other type (Mann-Whitney U)
        pairwise: dict[str, Any] = {}
        art_vals = group[group["object_type"] == "article"][column].dropna().to_numpy(
            dtype=float
        )
        for t in ("dataset", "software"):
            other = group[group["object_type"] == t][column].dropna().to_numpy(
                dtype=float
            )
            if len(art_vals) == 0 or len(other) == 0:
                pairwise[f"article_vs_{t}"] = {"test": "skipped"}
                continue
            try:
                u, p_mw = stats.mannwhitneyu(art_vals, other, alternative="two-sided")
                # Rank-biserial effect size
                rbc = 1 - (2 * u) / (len(art_vals) * len(other))
                pairwise[f"article_vs_{t}"] = {
                    "U": float(u),
                    "p_value": float(p_mw),
                    "rank_biserial": float(rbc),
                    "article_mean": float(np.mean(art_vals)),
                    "other_mean": float(np.mean(other)),
                    "article_lower_than_other": bool(
                        np.mean(art_vals) < np.mean(other)
                    ),
                }
            except ValueError:
                pairwise[f"article_vs_{t}"] = {"test": "skipped"}

        repo_result.update(
            {
                "test": "kruskal_wallis",
                "H": float(h),
                "p_value": float(p),
                "n_total": n,
                "epsilon_squared": eps_sq,
                "pairwise": pairwise,
            }
        )
        out[repo] = repo_result

    return out


def run_analysis(
    scores: pd.DataFrame,
    output_dir: Path | str,
) -> AnalysisResult:
    """Run the full v0.2 analysis and write JSON + Markdown summaries.

    The JSON output is committed to ``output/analysis/results.json`` and the
    Markdown to ``output/analysis/results.md``.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Restrict to articles with medium+ confidence where possible
    articles = scores[scores["object_type"] == "article"].copy()

    score_columns = [
        "relational_raw_norm",
        "agent_raw",
        "object_raw_fully_norm",
        "object_raw_fully_weakly_norm",
        "relational_adjusted",
        "agent_adjusted",
        "object_adjusted_fully",
        "object_adjusted_fully_weakly",
        "overall_embeddedness_score",
    ]
    # Guard against missing columns
    score_columns = [c for c in score_columns if c in articles.columns]

    boots = per_repository_bootstrap(articles, score_columns)

    cross_tier: dict[str, Any] = {}
    for col in score_columns:
        cross_tier[col] = kruskal_across_tiers(articles, col)

    within: dict[str, Any] = {}
    for col in score_columns:
        within[col] = within_repository_object_type_comparison(scores, col)

    result = AnalysisResult(
        cross_tier=cross_tier,
        within_repository=within,
        bootstrap_ci=boots,
    )

    # Write machine-readable JSON
    json_path = output_path / "results.json"
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "cross_tier": cross_tier,
                "within_repository": within,
                "bootstrap_ci": boots,
            },
            f,
            indent=2,
            default=str,
        )

    # Write Markdown summary
    md_path = output_path / "results.md"
    md_path.write_text(_render_markdown(cross_tier, within, boots), encoding="utf-8")

    return result


def _render_markdown(
    cross_tier: dict[str, Any],
    within: dict[str, Any],
    boots: dict[str, Any],
) -> str:
    lines: list[str] = ["# v0.2 analysis results", ""]
    lines.append("## Per-repository bootstrap CIs (articles only)")
    lines.append("")
    lines.append("| Repository | tier | n | relational (raw) | agent (raw) | object fully (raw) | relational adj | agent adj | object adj fully |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for repo, d in boots.items():
        def fmt(col: str) -> str:
            if col not in d:
                return "—"
            cell = d[col]
            if not isinstance(cell, dict):
                return "—"
            return f"{cell['mean']:.3f} [{cell['ci_low']:.3f}, {cell['ci_high']:.3f}]"

        lines.append(
            f"| {repo} | {d.get('tier')} | {d.get('n')} | "
            f"{fmt('relational_raw_norm')} | {fmt('agent_raw')} | "
            f"{fmt('object_raw_fully_norm')} | "
            f"{fmt('relational_adjusted')} | {fmt('agent_adjusted')} | "
            f"{fmt('object_adjusted_fully')} |"
        )

    lines.append("")
    lines.append("## Cross-tier Kruskal–Wallis (exploratory, n=4 repositories)")
    lines.append("")
    for col, res in cross_tier.items():
        if res.get("skipped"):
            continue
        lines.append(
            f"- **{col}**: H={res['H']:.3f}, p={res['p_value']:.4f}, "
            f"ε²={res.get('epsilon_squared'):.3f}, n={res['n_total']}"
        )
    lines.append("")
    lines.append(
        "> Caveat: with n=4 repositories, cross-tier results are exploratory only. "
        "See within-repository comparisons for statistically defensible tests."
    )

    lines.append("")
    lines.append("## Within-repository object-type comparisons (primary test)")
    for col, repo_results in within.items():
        lines.append(f"\n### {col}\n")
        for repo, res in repo_results.items():
            if res.get("test") == "skipped":
                lines.append(f"- **{repo}**: skipped ({res.get('reason', 'n/a')})")
                continue
            lines.append(
                f"- **{repo}**: H={res['H']:.3f}, p={res['p_value']:.4g}, "
                f"ε²={res.get('epsilon_squared'):.3f}, n={res['n_total']}"
            )
            for pair, pr in res.get("pairwise", {}).items():
                if pr.get("test") == "skipped":
                    continue
                lines.append(
                    f"  - {pair}: U={pr['U']:.0f}, p={pr['p_value']:.4g}, "
                    f"rank-biserial={pr['rank_biserial']:.3f}, "
                    f"article-lower={pr['article_lower_than_other']}"
                )

    return "\n".join(lines) + "\n"
