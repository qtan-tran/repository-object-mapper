"""Abstract adapter base and shared helpers.

Every repository integration implements :class:`AdapterBase`. The v0.2
release ships two concrete subclasses — :class:`OAIPMHAdapter` and
:class:`ZenodoAdapter` — plus an :class:`AdapterStub` demonstrating the
extension pattern for v0.5.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

from ..schema import NormalizedRecord

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class AdapterConfig:
    """Per-repository adapter configuration loaded from sample_v0_2.yaml."""

    name: str
    url: str
    type: str
    a_priori_tier: int
    endpoint: str
    metadata_formats: list[str]
    sampling_method: str
    random_seed: int
    target_record_count: int
    contact_email: str
    request_rate_per_second: float = 2.0
    extra: dict[str, Any] | None = None


@dataclass
class HarvestCheckpoint:
    """Persistent per-repository checkpoint to allow resumable harvests.

    Written atomically after each successful page/batch so a crash or
    resumption-token failure does not require a full restart.
    """

    repository_name: str
    last_cursor: str | None = None  # adapter-defined (token, offset, page...)
    records_harvested: int = 0
    updated_at: datetime = datetime.now(timezone.utc)

    def to_dict(self) -> dict[str, Any]:
        return {
            "repository_name": self.repository_name,
            "last_cursor": self.last_cursor,
            "records_harvested": self.records_harvested,
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> HarvestCheckpoint:
        return cls(
            repository_name=d["repository_name"],
            last_cursor=d.get("last_cursor"),
            records_harvested=int(d.get("records_harvested", 0)),
            updated_at=datetime.fromisoformat(d["updated_at"]),
        )


class AdapterBase(ABC):
    """Abstract adapter. v0.5 adapters subclass this without modifying callers."""

    name: str = "base"
    version: str = "0.2.0"

    def __init__(self, config: AdapterConfig, output_dir: Path, mock: bool = False) -> None:
        self.config = config
        self.output_dir = output_dir
        self.mock = mock
        self.raw_dir = output_dir / "records_raw" / config.name
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoint_path = output_dir / "records_raw" / f"{config.name}.checkpoint.json"

    # ------------------------------------------------------------------
    # Subclass contract
    # ------------------------------------------------------------------

    @abstractmethod
    def harvest(self, limit: int | None = None) -> Iterator[NormalizedRecord]:
        """Yield normalized records. Must be resumable and idempotent.

        Implementations should:
        - Persist raw payloads under :pyattr:`raw_dir`.
        - Call :meth:`save_checkpoint` periodically.
        - Never raise on per-record parse failures; log and continue.
        """

    @abstractmethod
    def describe_capabilities(self) -> dict[str, Any]:
        """Return static information about which fields the schema exposes.

        This is the "available affordances" side of the capability profile
        — what the schema *permits*, independent of what is populated.
        """

    # ------------------------------------------------------------------
    # Shared utilities
    # ------------------------------------------------------------------

    def save_raw(self, record_id: str, payload: str, extension: str = "xml") -> Path:
        """Write raw native payload to disk and return its path.

        Filenames are deterministic — re-running the harvest overwrites the
        same file for the same record identifier.
        """
        safe = record_id.replace("/", "_").replace(":", "_")
        path = self.raw_dir / f"{safe}.{extension}"
        path.write_text(payload, encoding="utf-8")
        return path

    def load_checkpoint(self) -> HarvestCheckpoint:
        if self.checkpoint_path.exists():
            try:
                data = json.loads(self.checkpoint_path.read_text())
                return HarvestCheckpoint.from_dict(data)
            except Exception as exc:
                log.warning(
                    "checkpoint_unreadable",
                    path=str(self.checkpoint_path),
                    error=str(exc),
                )
        return HarvestCheckpoint(repository_name=self.config.name)

    def save_checkpoint(self, cp: HarvestCheckpoint) -> None:
        cp.updated_at = datetime.now(timezone.utc)
        tmp = self.checkpoint_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(cp.to_dict(), indent=2))
        tmp.replace(self.checkpoint_path)

    def user_agent(self) -> str:
        return (
            f"repository-object-mapper/{self.version} "
            f"(+mailto:{self.config.contact_email})"
        )
