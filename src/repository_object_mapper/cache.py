"""Persistent SQLite cache for identifier resolution.

The cache is the single source of truth for resolution state. It is idempotent
across runs, survives v0.2 → v0.5, and can be shared across machines.

Schema
------
Columns:
- identifier (TEXT PRIMARY KEY)        — normalized "scheme:value" string
- scheme (TEXT)
- value (TEXT)
- attempt_ts (TEXT, ISO-8601)
- resolver_used (TEXT)
- http_status (INTEGER)
- raw_response (TEXT, JSON-encoded or raw body)
- resolved_object_type (TEXT, ObjectType enum value or NULL)
- resolution_tier (TEXT, ResolutionTier enum value)
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import structlog

from .schema import ObjectType, ResolutionTier

log = structlog.get_logger(__name__)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS resolution (
    identifier TEXT PRIMARY KEY,
    scheme TEXT NOT NULL,
    value TEXT NOT NULL,
    attempt_ts TEXT NOT NULL,
    resolver_used TEXT,
    http_status INTEGER,
    raw_response TEXT,
    resolved_object_type TEXT,
    resolution_tier TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_resolution_scheme ON resolution(scheme);
CREATE INDEX IF NOT EXISTS idx_resolution_tier ON resolution(resolution_tier);
"""


class ResolutionCache:
    """Thin wrapper around a SQLite table with staleness logic."""

    def __init__(self, path: Path | str, staleness_days: int = 90) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.staleness = timedelta(days=staleness_days)
        self._conn = sqlite3.connect(str(self.path))
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, scheme: str, value: str) -> dict[str, Any] | None:
        key = _key(scheme, value)
        row = self._conn.execute(
            "SELECT identifier, scheme, value, attempt_ts, resolver_used, http_status, "
            "raw_response, resolved_object_type, resolution_tier "
            "FROM resolution WHERE identifier = ?",
            (key,),
        ).fetchone()
        if row is None:
            return None
        attempt_ts = datetime.fromisoformat(row[3])
        if datetime.now(timezone.utc) - attempt_ts > self.staleness:
            log.debug("cache_stale", identifier=key)
            return None
        return _row_to_dict(row)

    def put(
        self,
        scheme: str,
        value: str,
        *,
        resolver_used: str | None,
        http_status: int | None,
        raw_response: dict[str, Any] | str | None,
        resolved_object_type: ObjectType | None,
        resolution_tier: ResolutionTier,
    ) -> None:
        key = _key(scheme, value)
        payload: str | None = json.dumps(raw_response) if isinstance(raw_response, dict) else raw_response

        self._conn.execute(
            "INSERT OR REPLACE INTO resolution "
            "(identifier, scheme, value, attempt_ts, resolver_used, http_status, "
            "raw_response, resolved_object_type, resolution_tier) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                key,
                scheme,
                value,
                datetime.now(timezone.utc).isoformat(),
                resolver_used,
                http_status,
                payload,
                resolved_object_type.value if resolved_object_type else None,
                resolution_tier.value,
            ),
        )
        self._conn.commit()

    def count_by_tier(self) -> dict[str, int]:
        cur = self._conn.execute(
            "SELECT resolution_tier, COUNT(*) FROM resolution GROUP BY resolution_tier"
        )
        return {tier: cnt for tier, cnt in cur.fetchall()}

    def total(self) -> int:
        cur = self._conn.execute("SELECT COUNT(*) FROM resolution")
        return int(cur.fetchone()[0])

    def close(self) -> None:
        self._conn.close()

    # Allow use as context manager
    def __enter__(self) -> ResolutionCache:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _key(scheme: str, value: str) -> str:
    return f"{scheme.lower()}:{value.strip()}"


def _row_to_dict(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "identifier": row[0],
        "scheme": row[1],
        "value": row[2],
        "attempt_ts": row[3],
        "resolver_used": row[4],
        "http_status": row[5],
        "raw_response": row[6],
        "resolved_object_type": row[7],
        "resolution_tier": row[8],
    }
