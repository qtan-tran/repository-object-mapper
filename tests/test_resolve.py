"""Resolution cache and tier-assignment logic tests."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock

import httpx

from repository_object_mapper.cache import ResolutionCache
from repository_object_mapper.resolve import (
    ResolutionConfig,
    _weak_match,
    resolve_identifier,
)
from repository_object_mapper.schema import Identifier, ObjectType, ResolutionTier


def test_cache_roundtrip(tmp_path: Path) -> None:
    cache_path = tmp_path / "res.db"
    with ResolutionCache(cache_path) as cache:
        cache.put(
            "doi", "10.1/a",
            resolver_used="crossref",
            http_status=200,
            raw_response={"type": "journal-article"},
            resolved_object_type=ObjectType.ARTICLE,
            resolution_tier=ResolutionTier.FULLY_TYPED,
        )
        got = cache.get("doi", "10.1/a")
        assert got is not None
        assert got["resolved_object_type"] == "article"
        assert got["resolution_tier"] == "fully_typed"


def test_cache_idempotent(tmp_path: Path) -> None:
    cache_path = tmp_path / "res.db"
    with ResolutionCache(cache_path) as cache:
        for _ in range(3):
            cache.put(
                "doi", "10.1/b",
                resolver_used="crossref",
                http_status=200,
                raw_response=None,
                resolved_object_type=ObjectType.DATASET,
                resolution_tier=ResolutionTier.FULLY_TYPED,
            )
        assert cache.total() == 1


def test_cache_staleness(tmp_path: Path) -> None:
    cache_path = tmp_path / "res.db"
    # Use a zero-day staleness so every entry is instantly stale
    with ResolutionCache(cache_path, staleness_days=0) as cache:
        cache.put(
            "doi", "10.1/c",
            resolver_used="crossref",
            http_status=200,
            raw_response=None,
            resolved_object_type=ObjectType.ARTICLE,
            resolution_tier=ResolutionTier.FULLY_TYPED,
        )
        # Give the clock a nudge forward
        time.sleep(0.01)
        assert cache.get("doi", "10.1/c") is None


def test_weak_match_arxiv() -> None:
    ident = Identifier(scheme="arxiv", value="2307.00001")
    assert _weak_match(ident) == ObjectType.PREPRINT


def test_weak_match_swh() -> None:
    ident = Identifier(scheme="url", value="https://archive.softwareheritage.org/swh:1:rev:abc")
    assert _weak_match(ident) == ObjectType.SOFTWARE


def test_weak_match_pmc() -> None:
    ident = Identifier(scheme="url", value="https://www.ncbi.nlm.nih.gov/pmc/articles/PMC123/")
    assert _weak_match(ident) == ObjectType.ARTICLE


def test_weak_match_unknown_returns_none() -> None:
    ident = Identifier(scheme="url", value="https://random.example.org/thing")
    assert _weak_match(ident) is None


def test_resolve_identifier_datacite_hint_bypasses_network(tmp_path: Path) -> None:
    with ResolutionCache(tmp_path / "r.db") as cache:
        config = ResolutionConfig(contact_email="t@t")
        ident = Identifier(scheme="doi", value="10.1/hint")
        ot, tier = resolve_identifier(
            ident, cache, config, datacite_hint="Dataset"
        )
        assert ot == ObjectType.DATASET
        assert tier == ResolutionTier.FULLY_TYPED
        # Cache hit on second call
        ot2, tier2 = resolve_identifier(ident, cache, config)
        assert (ot2, tier2) == (ObjectType.DATASET, ResolutionTier.FULLY_TYPED)


def test_resolve_identifier_weak_tier_without_network(tmp_path: Path) -> None:
    with ResolutionCache(tmp_path / "r.db") as cache:
        config = ResolutionConfig(contact_email="t@t")
        ident = Identifier(scheme="arxiv", value="2307.12345")
        ot, tier = resolve_identifier(ident, cache, config)
        assert ot == ObjectType.PREPRINT
        assert tier == ResolutionTier.WEAKLY_TYPED


def test_resolve_identifier_unresolvable(tmp_path: Path) -> None:
    with ResolutionCache(tmp_path / "r.db") as cache:
        config = ResolutionConfig(contact_email="t@t")
        ident = Identifier(scheme="url", value="https://never.example.com/page")
        # Not doi, not weak-matchable → unresolved
        ot, tier = resolve_identifier(ident, cache, config)
        assert ot is None
        assert tier == ResolutionTier.UNRESOLVED


def test_doi_resolution_uses_crossref(monkeypatch, tmp_path: Path) -> None:
    """Mocked Crossref response drives a FULLY_TYPED verdict."""
    with ResolutionCache(tmp_path / "r.db") as cache:
        config = ResolutionConfig(contact_email="t@t")
        ident = Identifier(scheme="doi", value="10.1/real")

        # Build a fake httpx.Client whose .get() returns a 200 Crossref-like body
        class FakeClient:
            def get(self, url: str):
                resp = MagicMock(spec=httpx.Response)
                resp.status_code = 200
                resp.json.return_value = {"message": {"type": "journal-article"}}
                return resp

            def close(self) -> None:
                pass

        ot, tier = resolve_identifier(
            ident, cache, config, client=FakeClient()  # type: ignore[arg-type]
        )
        assert ot == ObjectType.ARTICLE
        assert tier == ResolutionTier.FULLY_TYPED
