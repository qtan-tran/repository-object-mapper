"""Figure generation for the paper.

Produces:

- Per-dimension distributions (violin/kde per repository)
- Per-object-type boxplots within each repository
- Tier-vs-embeddedness scatter plots (raw and available-adjusted)
- Capability profile heatmap (repositories × relation types)
- Network graph visualizing a Zenodo article and its relational context
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")  # noqa: E402
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd
import seaborn as sns


def _ensure_dir(p: Path | str) -> Path:
    path = Path(p)
    path.mkdir(parents=True, exist_ok=True)
    return path


def dimension_distributions(scores: pd.DataFrame, out_dir: Path | str) -> list[Path]:
    """KDE distributions of each dimension, one panel per repository."""
    out = _ensure_dir(out_dir)
    paths: list[Path] = []

    articles = scores[scores["object_type"] == "article"].copy()
    if articles.empty:
        return paths

    for col in (
        "relational_raw_norm",
        "agent_raw",
        "object_raw_fully_norm",
        "relational_adjusted",
        "agent_adjusted",
        "object_adjusted_fully",
    ):
        if col not in articles.columns:
            continue
        fig, ax = plt.subplots(figsize=(8, 5))
        for repo, group in articles.groupby("repository"):
            vals = group[col].dropna().to_numpy()
            if len(vals) < 2:
                continue
            sns.kdeplot(vals, ax=ax, label=repo, fill=True, alpha=0.25)
        ax.set_xlabel(col)
        ax.set_ylabel("density")
        ax.set_title(f"Article embeddedness distribution — {col}")
        ax.legend()
        p = out / f"dist_{col}.png"
        fig.savefig(p, dpi=150, bbox_inches="tight")
        plt.close(fig)
        paths.append(p)
    return paths


def object_type_boxplots(scores: pd.DataFrame, out_dir: Path | str) -> list[Path]:
    """Per-repository boxplots of dimensions by object type."""
    out = _ensure_dir(out_dir)
    paths: list[Path] = []
    target_types = ["article", "dataset", "software", "preprint", "thesis"]
    for col in (
        "relational_raw_norm",
        "agent_raw",
        "object_raw_fully_norm",
        "relational_adjusted",
        "object_adjusted_fully",
    ):
        if col not in scores.columns:
            continue
        sub = scores[scores["object_type"].isin(target_types)].copy()
        if sub.empty:
            continue
        fig, ax = plt.subplots(figsize=(10, 6))
        sns.boxplot(
            data=sub, x="repository", y=col, hue="object_type", ax=ax,
        )
        ax.set_title(f"Object-type comparison — {col}")
        plt.setp(ax.get_xticklabels(), rotation=15, ha="right")
        p = out / f"box_{col}.png"
        fig.savefig(p, dpi=150, bbox_inches="tight")
        plt.close(fig)
        paths.append(p)
    return paths


def tier_scatter(scores: pd.DataFrame, out_dir: Path | str) -> list[Path]:
    """Tier (x) vs dimension (y) with per-repository points, raw and adjusted."""
    out = _ensure_dir(out_dir)
    paths: list[Path] = []
    articles = scores[scores["object_type"] == "article"].copy()
    if articles.empty:
        return paths

    agg = articles.groupby(["repository", "tier"]).agg(
        relational_raw=("relational_raw_norm", "mean"),
        agent_raw=("agent_raw", "mean"),
        object_raw=("object_raw_fully_norm", "mean"),
        relational_adj=("relational_adjusted", "mean"),
        agent_adj=("agent_adjusted", "mean"),
        object_adj=("object_adjusted_fully", "mean"),
    ).reset_index()

    for raw_col, adj_col in (
        ("relational_raw", "relational_adj"),
        ("agent_raw", "agent_adj"),
        ("object_raw", "object_adj"),
    ):
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5), sharey=True)
        for _, row in agg.iterrows():
            ax1.scatter(row["tier"], row[raw_col], s=100)
            ax1.annotate(row["repository"], (row["tier"], row[raw_col]))
            ax2.scatter(row["tier"], row[adj_col], s=100)
            ax2.annotate(row["repository"], (row["tier"], row[adj_col]))
        ax1.set_title(f"Raw — {raw_col}")
        ax1.set_xlabel("a priori schema tier")
        ax1.set_ylabel("mean score (articles)")
        ax2.set_title(f"Available-adjusted — {adj_col}")
        ax2.set_xlabel("a priori schema tier")
        p = out / f"tier_scatter_{raw_col}.png"
        fig.savefig(p, dpi=150, bbox_inches="tight")
        plt.close(fig)
        paths.append(p)
    return paths


def capability_heatmap(
    profile: dict[str, dict], out_dir: Path | str
) -> Path | None:
    """Heatmap: repositories × native relation types, cells = population rate."""
    out = _ensure_dir(out_dir)
    # Collect the union of all native relation types across repositories
    all_types: set[str] = set()
    for repo_data in profile.values():
        per = (
            repo_data.get("used_affordances_articles", {}).get(
                "per_native_relation_type_rate", {}
            )
            or {}
        )
        all_types.update(per.keys())
    if not all_types or not profile:
        return None

    types_sorted = sorted(all_types)
    repos = list(profile.keys())
    matrix = np.zeros((len(repos), len(types_sorted)))
    for i, repo in enumerate(repos):
        per = (
            profile[repo].get("used_affordances_articles", {}).get(
                "per_native_relation_type_rate", {}
            )
            or {}
        )
        for j, t in enumerate(types_sorted):
            matrix[i, j] = per.get(t, 0.0)

    fig, ax = plt.subplots(figsize=(max(8, len(types_sorted) * 0.4), max(4, len(repos) * 0.6)))
    sns.heatmap(
        matrix,
        xticklabels=types_sorted,
        yticklabels=repos,
        annot=False,
        cmap="viridis",
        ax=ax,
        cbar_kws={"label": "article population rate"},
    )
    ax.set_title("Capability profile: article population rate per native relation type")
    plt.setp(ax.get_xticklabels(), rotation=75, ha="right")
    p = out / "capability_heatmap.png"
    fig.savefig(p, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return p


def article_network_graph(
    records: list, out_dir: Path | str, repository: str = "zenodo"
) -> Path | None:
    """Pick an article record with many relations and graph its context."""
    out = _ensure_dir(out_dir)
    candidates = [
        r for r in records
        if r.repository_name == repository
        and r.object_type
        and r.object_type.value == "article"
        and len(r.relations) >= 2
    ]
    if not candidates:
        return None

    record = max(candidates, key=lambda r: len(r.relations))

    g = nx.DiGraph()
    center = f"Article: {record.title[:40] if record.title else record.local_identifier}"
    g.add_node(center, kind="article")
    for rel in record.relations:
        label = (
            f"{rel.resolved_object_type.value if rel.resolved_object_type else 'unresolved'}\n"
            f"({rel.native_relation_type})"
        )
        target = rel.target_identifier.value[:32]
        g.add_node(
            target,
            kind=rel.resolved_object_type.value if rel.resolved_object_type else "unresolved",
        )
        g.add_edge(center, target, label=rel.native_relation_type)

    fig, ax = plt.subplots(figsize=(10, 7))
    pos = nx.spring_layout(g, seed=42)
    color_by_kind = {
        "article": "#1f77b4",
        "dataset": "#2ca02c",
        "software": "#d62728",
        "preprint": "#9467bd",
        "thesis": "#8c564b",
        "unresolved": "#7f7f7f",
    }
    colors = [color_by_kind.get(g.nodes[n].get("kind", "unresolved"), "#7f7f7f") for n in g.nodes]
    nx.draw_networkx_nodes(g, pos, node_color=colors, node_size=1400, ax=ax, alpha=0.9)
    nx.draw_networkx_labels(g, pos, font_size=7, ax=ax)
    nx.draw_networkx_edges(g, pos, ax=ax, arrows=True, alpha=0.6)
    edge_labels = nx.get_edge_attributes(g, "label")
    nx.draw_networkx_edge_labels(g, pos, edge_labels=edge_labels, font_size=6, ax=ax)
    ax.set_title(f"Relational context of article {record.local_identifier}")
    ax.axis("off")
    p = out / "article_network.png"
    fig.savefig(p, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return p


def run_visualizations(
    scores: pd.DataFrame,
    records: list,
    profile: dict[str, Any],
    out_dir: Path | str,
) -> list[Path]:
    out = _ensure_dir(out_dir)
    paths: list[Path] = []
    paths.extend(dimension_distributions(scores, out))
    paths.extend(object_type_boxplots(scores, out))
    paths.extend(tier_scatter(scores, out))
    h = capability_heatmap(profile, out)
    if h:
        paths.append(h)
    n = article_network_graph(records, out)
    if n:
        paths.append(n)

    # Manifest
    (out / "figures.json").write_text(
        json.dumps([str(p) for p in paths], indent=2), encoding="utf-8"
    )
    return paths
