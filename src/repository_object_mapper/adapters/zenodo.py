"""Zenodo REST API adapter (tier 3).

Zenodo exposes a rich JSON response that maps cleanly onto our normalized
schema. The adapter uses HTTPX with polite rate limiting and contact-email
identification in the User-Agent header.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ..schema import (
    Affiliation,
    Creator,
    FieldPresenceFlags,
    Funder,
    HarvestProvenance,
    Identifier,
    NormalizedRecord,
    Relation,
)
from . import AdapterBase, HarvestCheckpoint

log = structlog.get_logger(__name__)

BASE_URL = "https://zenodo.org/api/records"


class ZenodoAdapter(AdapterBase):
    name = "zenodo_rest"
    version = "0.2.0"

    def describe_capabilities(self) -> dict[str, Any]:
        return {
            "adapter": self.name,
            "format_negotiated": "zenodo_json",
            "permits_relations": True,
            "permits_creator_orcid": True,
            "permits_affiliation_ror": False,
            "permits_funder": True,
            "permits_typed_relations": True,
        }

    def harvest(self, limit: int | None = None) -> Iterator[NormalizedRecord]:
        cp = self.load_checkpoint()
        limit_eff = limit or self.config.target_record_count

        if self.mock:
            yield from self._harvest_mock(cp, limit_eff)
            return

        yield from self._harvest_live(cp, limit_eff)

    def _harvest_mock(
        self, cp: HarvestCheckpoint, limit: int
    ) -> Iterator[NormalizedRecord]:
        mock_root = Path("data/mock/zenodo")
        if not mock_root.exists():
            log.warning("mock_dir_missing", path=str(mock_root))
            return

        files = sorted(mock_root.glob("*.json"))
        files = files[cp.records_harvested : cp.records_harvested + limit]

        for idx, jf in enumerate(files):
            try:
                payload = jf.read_text(encoding="utf-8")
                doc = json.loads(payload)
                record = self._parse_record(doc, payload, endpoint=str(jf))
                if record is not None:
                    yield record
            except Exception as exc:
                log.warning("zenodo_parse_error", file=str(jf), error=str(exc))

            cp.records_harvested += 1
            if idx % 50 == 49:
                self.save_checkpoint(cp)

        self.save_checkpoint(cp)

    def _harvest_live(
        self, cp: HarvestCheckpoint, limit: int
    ) -> Iterator[NormalizedRecord]:
        client = httpx.Client(
            headers={"User-Agent": self.user_agent()},
            timeout=30.0,
        )

        # Pagination via "cursor"-style next links exposed by Zenodo; we use
        # `page` + `size` for simplicity. Resuming from cp.last_cursor.
        page = int(cp.last_cursor) if cp.last_cursor else 1
        size = 100
        count = 0

        while count < limit:
            params = {
                "q": "resource_type.type:publication AND resource_type.subtype:article",
                "page": page,
                "size": size,
                "sort": "mostrecent",
            }
            try:
                response = self._request(client, BASE_URL, params)
            except httpx.HTTPError as exc:
                log.error("zenodo_http_error", error=str(exc), page=page)
                break

            hits = response.get("hits", {}).get("hits", [])
            if not hits:
                log.info("zenodo_pagination_exhausted", page=page)
                break

            for doc in hits:
                if count >= limit:
                    break
                payload = json.dumps(doc)
                record = self._parse_record(doc, payload, endpoint=BASE_URL)
                if record is not None:
                    yield record
                count += 1
                cp.records_harvested += 1

            page += 1
            cp.last_cursor = str(page)
            self.save_checkpoint(cp)
            time.sleep(1.0 / self.config.request_rate_per_second)

        client.close()
        cp.last_cursor = None
        self.save_checkpoint(cp)

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        retry=retry_if_exception_type(httpx.HTTPError),
        reraise=True,
    )
    def _request(
        self, client: httpx.Client, url: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        r = client.get(url, params=params)
        r.raise_for_status()
        return r.json()

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def _parse_record(
        self, doc: dict[str, Any], raw_payload: str, endpoint: str
    ) -> NormalizedRecord | None:
        metadata = doc.get("metadata", {})
        local_id = str(doc.get("id") or metadata.get("id") or "")
        if not local_id:
            log.warning("zenodo_missing_id")
            return None

        record_hash = hashlib.sha1(local_id.encode("utf-8")).hexdigest()[:12]
        raw_path = self.save_raw(record_hash, raw_payload, extension="json")

        # Identifiers
        identifiers: list[Identifier] = []
        if doc.get("doi"):
            identifiers.append(Identifier(scheme="doi", value=str(doc["doi"])))
        for alt in metadata.get("alternate_identifiers", []) or []:
            identifiers.append(
                Identifier(
                    scheme=(alt.get("scheme") or "other").lower(),
                    value=str(alt.get("identifier") or ""),
                )
            )
        identifiers.append(
            Identifier(scheme="local", value=str(doc.get("links", {}).get("self", local_id)))
        )

        # Creators with ORCID
        creators: list[Creator] = []
        for c in metadata.get("creators", []) or []:
            orcid = c.get("orcid")
            affs = []
            if c.get("affiliation"):
                # Zenodo v1 doesn't expose ROR; use string only
                affs.append(Affiliation(name=c["affiliation"], ror=None))
            creators.append(
                Creator(name=c.get("name", "Unknown"), orcid=orcid, affiliations=affs)
            )

        # Related identifiers
        relations: list[Relation] = []
        for rel in metadata.get("related_identifiers", []) or []:
            ident_scheme = (rel.get("scheme") or "other").lower()
            value = rel.get("identifier")
            if not value:
                continue
            relations.append(
                Relation(
                    native_relation_type=rel.get("relation", "Related"),
                    target_identifier=Identifier(scheme=ident_scheme, value=str(value)),
                )
            )

        # Subjects / keywords
        subjects: list[str] = []
        for s in metadata.get("keywords", []) or []:
            subjects.append(s)
        for s in metadata.get("subjects", []) or []:
            term = s.get("term") if isinstance(s, dict) else s
            if term:
                subjects.append(term)

        # License
        lic = metadata.get("license")
        license_ = lic.get("id") or lic.get("title") if isinstance(lic, dict) else lic

        # Funders
        funders: list[Funder] = []
        for g in metadata.get("grants", []) or []:
            funder_node = g.get("funder", {}) if isinstance(g, dict) else {}
            funders.append(
                Funder(
                    name=funder_node.get("name"),
                    funder_id=funder_node.get("doi") or funder_node.get("id"),
                    award_number=g.get("code"),
                    project_id=g.get("internal_id"),
                )
            )

        # Declared type
        rt = metadata.get("resource_type", {})
        declared = rt.get("type")
        subtype = rt.get("subtype")
        declared_type_raw = f"{declared}/{subtype}" if subtype else declared

        # Publication date
        pub_date = _parse_iso_date(metadata.get("publication_date"))

        presence = FieldPresenceFlags(
            has_relation_field=True,
            has_creator_orcid_field=True,
            has_affiliation_ror_field=False,  # Zenodo v1 API lacks ROR
            has_funder_field=True,
            has_license_field=True,
            has_subject_field=True,
            has_fulltext_indicator_field=True,
        )

        provenance = HarvestProvenance(
            timestamp=datetime.now(timezone.utc),
            endpoint=endpoint,
            format_negotiated="zenodo_json",
            http_status=200,
            adapter_name=self.name,
            adapter_version=self.version,
        )

        # Full-text availability: Zenodo records with at least one file
        full_text_available = bool(doc.get("files")) or None

        return NormalizedRecord(
            repository_name=self.config.name,
            repository_a_priori_tier=self.config.a_priori_tier,
            local_identifier=local_id,
            raw_path=str(raw_path),
            provenance=provenance,
            identifiers=identifiers,
            title=metadata.get("title"),
            description=metadata.get("description"),
            publication_date=pub_date,
            creation_date=pub_date,
            creators=creators,
            funders=funders,
            subjects=subjects,
            license=license_,
            language=metadata.get("language"),
            full_text_available=full_text_available,
            relations=relations,
            declared_type_raw=declared_type_raw,
            presence=presence,
        )


def _parse_iso_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None
