"""Sampling-frame loading and validation.

Reads ``config/sample_v0_2.yaml`` and turns each entry into an
:class:`~repository_object_mapper.adapters.AdapterConfig`. Also handles
the summary emitted by ``rom sample``.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml

from .adapters import AdapterConfig
from .adapters.oai_pmh import OAIPMHAdapter
from .adapters.zenodo import ZenodoAdapter


def load_sample_config(path: Path | str) -> list[AdapterConfig]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Sample config not found: {p}")
    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    repos = data.get("repositories", [])
    return [
        AdapterConfig(
            name=r["name"],
            url=r["url"],
            type=r.get("type", "unknown"),
            a_priori_tier=int(r["a_priori_tier"]),
            endpoint=r["endpoint"],
            metadata_formats=list(r.get("metadata_formats", ["oai_dc"])),
            sampling_method=r.get("sampling_method", "systematic"),
            random_seed=int(r.get("random_seed", 42)),
            target_record_count=int(r.get("target_record_count", 1500)),
            contact_email=r.get(
                "contact_email", data.get("default_contact_email", "user@example.org")
            ),
            request_rate_per_second=float(r.get("request_rate_per_second", 2.0)),
            extra=r.get("extra"),
        )
        for r in repos
    ]


def build_adapter(
    config: AdapterConfig, output_dir: Path, mock: bool = False
):
    """Dispatch to the right adapter based on declared type."""
    if config.type.lower() == "zenodo_rest" or "zenodo" in config.url.lower():
        return ZenodoAdapter(config, output_dir, mock=mock)
    return OAIPMHAdapter(config, output_dir, mock=mock)


def summarize_sampling_frame(configs: list[AdapterConfig]) -> dict[str, Any]:
    return {
        "n_repositories": len(configs),
        "tiers_represented": sorted({c.a_priori_tier for c in configs}),
        "target_total_records": sum(c.target_record_count for c in configs),
        "repositories": [asdict(c) for c in configs],
    }
