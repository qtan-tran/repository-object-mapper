"""Stub adapter demonstrating the extension pattern for v0.5.

New v0.5 adapters (Figshare, DSpace 7+ REST, Dataverse, standalone
InvenioRDM) inherit :class:`AdapterBase` and implement :meth:`harvest` and
:meth:`describe_capabilities`. They reuse the raw-payload, checkpoint, and
rate-limiting scaffolding inherited from the base class — no pipeline rewrite
is required.

This stub is intentionally unusable for real harvesting so that it does not
creep into v0.2 analysis. It exists purely as a template.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from ..schema import NormalizedRecord
from . import AdapterBase


class AdapterStub(AdapterBase):
    """Skeleton adapter for v0.5. Do not instantiate in v0.2 pipelines."""

    name = "stub"
    version = "0.2.0-stub"

    def describe_capabilities(self) -> dict[str, Any]:
        # Real adapters declare which of the normalized fields their API
        # schema exposes. That list is consumed by capability profiling.
        return {
            "adapter": self.name,
            "format_negotiated": "stub",
            "permits_relations": False,
            "permits_creator_orcid": False,
            "permits_affiliation_ror": False,
            "permits_funder": False,
            "permits_typed_relations": False,
        }

    def harvest(self, limit: int | None = None) -> Iterator[NormalizedRecord]:
        # Real implementations:
        # 1. Authenticate if required; populate User-Agent with contact email.
        # 2. Page or cursor-iterate the target API, persisting raw responses.
        # 3. For each record, call a _parse_record helper that returns a
        #    NormalizedRecord with explicit FieldPresenceFlags.
        # 4. Update the checkpoint after each page; save raw always.
        raise NotImplementedError("AdapterStub exists to illustrate the v0.5 extension pattern.")
