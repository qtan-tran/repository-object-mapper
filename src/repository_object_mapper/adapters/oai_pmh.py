"""Generic OAI-PMH adapter with format negotiation and resumption-token defense.

Covers tiers 1, 2, and commonly 4. The adapter negotiates the richest
available metadata format in this preference order:

    datacite4 > oai_datacite > oai_dc

Negotiation decisions are logged and carried into the capability profile so
that analysis sees what the adapter actually received, not what the repository
*might* have exposed.

Parsing is defensive: every field is optional. Missing fields are recorded as
``None`` with their ``presence`` flag set according to whether the underlying
format exposes the field at all.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

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
from . import AdapterBase, AdapterConfig, HarvestCheckpoint

log = structlog.get_logger(__name__)


# Canonical preference order
FORMAT_PREFERENCE = ["datacite4", "oai_datacite", "oai_dc"]

# XML namespaces we care about
NS = {
    "oai": "http://www.openarchives.org/OAI/2.0/",
    "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "dcterms": "http://purl.org/dc/terms/",
    "dct": "http://purl.org/dc/terms/",
    "datacite": "http://datacite.org/schema/kernel-4",
    "datacite3": "http://datacite.org/schema/kernel-3",
    "oaidc": "http://www.openarchives.org/OAI/2.0/oai_datacite",
}


class OAIPMHParseError(Exception):
    """Raised for unrecoverable parse problems on an individual record."""


class OAIPMHAdapter(AdapterBase):
    """Generic OAI-PMH adapter used across tiers 1, 2, and (frequently) 4."""

    name = "oai_pmh"
    version = "0.2.0"

    def __init__(self, config: AdapterConfig, output_dir: Path, mock: bool = False) -> None:
        super().__init__(config, output_dir, mock)
        self.negotiated_format: str | None = None

    # ------------------------------------------------------------------
    # Capabilities (static, schema-derived)
    # ------------------------------------------------------------------

    def describe_capabilities(self) -> dict[str, Any]:
        """Return a *static* view of what this adapter's format exposes.

        Runtime observation (what fields actually appear in records) is
        separately tracked by ``profile.py`` — this method answers only the
        question "what does the format permit in principle?"
        """
        fmt = self.negotiated_format or self._preferred_format()
        base = {
            "adapter": self.name,
            "format_negotiated": fmt,
            "permits_relations": False,
            "permits_creator_orcid": False,
            "permits_affiliation_ror": False,
            "permits_funder": False,
            "permits_typed_relations": False,
        }
        if fmt in {"datacite4", "oai_datacite"}:
            base.update(
                permits_relations=True,
                permits_creator_orcid=True,
                permits_affiliation_ror=True,
                permits_funder=True,
                permits_typed_relations=True,
            )
        elif fmt == "oai_dc":
            # Dublin Core has dc:relation but not typed relations
            base["permits_relations"] = True
        return base

    def _preferred_format(self) -> str:
        for f in FORMAT_PREFERENCE:
            if f in self.config.metadata_formats:
                return f
        return "oai_dc"

    # ------------------------------------------------------------------
    # Harvest
    # ------------------------------------------------------------------

    def harvest(self, limit: int | None = None) -> Iterator[NormalizedRecord]:
        cp = self.load_checkpoint()
        self.negotiated_format = self._preferred_format()
        log.info(
            "harvest_start",
            repository=self.config.name,
            format=self.negotiated_format,
            resuming_from=cp.last_cursor,
            already=cp.records_harvested,
        )

        limit_eff = limit or self.config.target_record_count

        # Mock mode reads canned XML responses from data/mock/oai_pmh/<name>/
        if self.mock:
            yield from self._harvest_mock(cp, limit_eff)
            return

        yield from self._harvest_live(cp, limit_eff)

    # ------------------------------------------------------------------
    # Mock harvest (used for tests and `make demo`)
    # ------------------------------------------------------------------

    def _harvest_mock(
        self, cp: HarvestCheckpoint, limit: int
    ) -> Iterator[NormalizedRecord]:
        mock_root = Path("data/mock/oai_pmh") / self.config.name
        if not mock_root.exists():
            log.warning("mock_dir_missing", path=str(mock_root))
            return

        files = sorted(mock_root.glob("*.xml"))
        files = files[cp.records_harvested : cp.records_harvested + limit]

        for idx, xml_file in enumerate(files):
            try:
                payload = xml_file.read_text(encoding="utf-8")
                record = self._parse_record(payload, source_endpoint=str(xml_file))
                if record is not None:
                    yield record
            except OAIPMHParseError as exc:
                log.warning(
                    "mock_parse_error",
                    file=str(xml_file),
                    error=str(exc),
                )
                continue

            cp.records_harvested += 1
            if idx % 50 == 49:
                self.save_checkpoint(cp)
        self.save_checkpoint(cp)

    # ------------------------------------------------------------------
    # Live harvest (network) — uses sickle with defensive retry
    # ------------------------------------------------------------------

    def _harvest_live(
        self, cp: HarvestCheckpoint, limit: int
    ) -> Iterator[NormalizedRecord]:
        try:
            from sickle import Sickle  # type: ignore[import-untyped]
            from sickle.oaiexceptions import (  # type: ignore[import-untyped]
                BadResumptionToken,
                NoRecordsMatch,
            )
        except ImportError as exc:  # pragma: no cover - install guard
            log.error("sickle_missing", error=str(exc))
            raise

        sickle = Sickle(self.config.endpoint)
        sickle.default_headers["User-Agent"] = self.user_agent()

        fmt = self.negotiated_format

        try:
            iterator = sickle.ListRecords(
                metadataPrefix=fmt,
                resumptionToken=cp.last_cursor,
                ignore_deleted=False,
            )
        except NoRecordsMatch:
            log.info("harvest_empty", repository=self.config.name)
            return

        count = 0
        for sickle_rec in iterator:
            if count >= limit:
                break

            try:
                payload = sickle_rec.raw  # sickle exposes raw XML
                if sickle_rec.deleted:
                    log.info("record_deleted", identifier=sickle_rec.header.identifier)
                    count += 1
                    cp.records_harvested += 1
                    continue

                record = self._parse_record(payload, source_endpoint=self.config.endpoint)
                if record is not None:
                    yield record
            except BadResumptionToken as exc:
                log.warning("resumption_token_bad", error=str(exc))
                # Restart without token; the caller can detect via missing records
                break
            except Exception as exc:  # noqa: BLE001
                log.warning("record_parse_error", error=str(exc))

            count += 1
            cp.records_harvested += 1
            if count % 50 == 0:
                # Sickle exposes the token on its iterator
                cp.last_cursor = getattr(iterator, "resumption_token", None)
                self.save_checkpoint(cp)
                time.sleep(1.0 / self.config.request_rate_per_second)

        cp.last_cursor = None
        self.save_checkpoint(cp)

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def _parse_record(
        self, payload: str, source_endpoint: str
    ) -> NormalizedRecord | None:
        """Parse an OAI-PMH record XML blob into a NormalizedRecord.

        Never raises for recoverable defects: returns ``None`` and logs.
        """
        try:
            root = ET.fromstring(payload)
        except ET.ParseError as exc:
            log.warning("xml_parse_error", error=str(exc))
            return None

        # If given a full OAI-PMH envelope, descend to the record element
        record_el = root.find(".//oai:record", NS)
        if record_el is None:
            record_el = root
        header = record_el.find("oai:header", NS)
        if header is not None and header.get("status") == "deleted":
            return None

        identifier_el = record_el.find("oai:header/oai:identifier", NS)
        if identifier_el is None or not identifier_el.text:
            # Try fallback: direct attribute
            raise OAIPMHParseError("no_local_identifier")
        local_id = identifier_el.text.strip()

        metadata_el = record_el.find("oai:metadata", NS)
        if metadata_el is None:
            raise OAIPMHParseError("no_metadata_element")

        fmt = self.negotiated_format or self._preferred_format()
        if fmt in {"datacite4", "oai_datacite"}:
            parsed = self._parse_datacite(metadata_el)
        else:
            parsed = self._parse_oai_dc(metadata_el)

        # Persist raw payload
        record_hash = hashlib.sha1(local_id.encode("utf-8")).hexdigest()[:12]
        raw_path = self.save_raw(f"{record_hash}", payload, extension="xml")

        provenance = HarvestProvenance(
            timestamp=datetime.now(timezone.utc),
            endpoint=source_endpoint,
            format_negotiated=fmt,
            http_status=200,
            adapter_name=self.name,
            adapter_version=self.version,
        )

        return NormalizedRecord(
            repository_name=self.config.name,
            repository_a_priori_tier=self.config.a_priori_tier,
            local_identifier=local_id,
            raw_path=str(raw_path),
            provenance=provenance,
            **parsed,
        )

    # ------------------------------------------------------------------
    # Format-specific parsers
    # ------------------------------------------------------------------

    def _parse_oai_dc(self, metadata_el: ET.Element) -> dict[str, Any]:
        dc_root = metadata_el.find("oai_dc:dc", NS)
        if dc_root is None:
            dc_root = metadata_el.find("dc")
        out: dict[str, Any] = {}
        presence = FieldPresenceFlags(
            has_relation_field=True,  # DC always has dc:relation slot
            has_subject_field=True,
            has_license_field=True,
        )

        def findall_text(tag: str) -> list[str]:
            if dc_root is None:
                return []
            nodes = dc_root.findall(f"dc:{tag}", NS)
            return [n.text.strip() for n in nodes if n.text]

        titles = findall_text("title")
        out["title"] = titles[0] if titles else None

        descs = findall_text("description")
        out["description"] = descs[0] if descs else None

        out["declared_type_raw"] = (findall_text("type") or [None])[0]
        out["subjects"] = findall_text("subject")
        rights = findall_text("rights")
        out["license"] = rights[0] if rights else None

        langs = findall_text("language")
        out["language"] = langs[0] if langs else None

        # Creators (no ORCID in oai_dc)
        creators = [Creator(name=n) for n in findall_text("creator")]
        out["creators"] = creators

        # Identifiers
        identifiers: list[Identifier] = []
        for v in findall_text("identifier"):
            if v.lower().startswith("doi:") or "doi.org/" in v.lower():
                identifiers.append(Identifier(scheme="doi", value=_strip_doi(v)))
            elif "hdl.handle.net" in v:
                identifiers.append(Identifier(scheme="handle", value=v))
            elif v.lower().startswith("http"):
                identifiers.append(Identifier(scheme="url", value=v))
            else:
                identifiers.append(Identifier(scheme="local", value=v))
        out["identifiers"] = identifiers

        # Dates
        dates = findall_text("date")
        out["publication_date"] = _parse_date(dates[0]) if dates else None
        out["creation_date"] = out["publication_date"]

        # Relations (untyped in DC)
        relations: list[Relation] = []
        for v in findall_text("relation"):
            ident = _guess_identifier_from_string(v)
            relations.append(
                Relation(native_relation_type="dc:relation", target_identifier=ident)
            )
        out["relations"] = relations

        out["funders"] = []
        out["presence"] = presence
        return out

    def _parse_datacite(self, metadata_el: ET.Element) -> dict[str, Any]:
        # Try kernel-4 then kernel-3
        resource = metadata_el.find(".//datacite:resource", NS)
        if resource is None:
            resource = metadata_el.find(".//datacite3:resource", NS)
        if resource is None:
            raise OAIPMHParseError("no_datacite_resource")

        presence = FieldPresenceFlags(
            has_relation_field=True,
            has_creator_orcid_field=True,
            has_affiliation_ror_field=True,
            has_funder_field=True,
            has_license_field=True,
            has_subject_field=True,
        )

        def _dc4(path: str) -> list[ET.Element]:
            nodes = resource.findall(path, NS)
            if not nodes:
                # Try kernel-3 namespace
                nodes = resource.findall(path.replace("datacite:", "datacite3:"), NS)
            return nodes

        # Title
        title_nodes = _dc4("datacite:titles/datacite:title")
        title = title_nodes[0].text.strip() if title_nodes and title_nodes[0].text else None

        # Description
        desc_nodes = _dc4("datacite:descriptions/datacite:description")
        description = (
            desc_nodes[0].text.strip() if desc_nodes and desc_nodes[0].text else None
        )

        # Declared type
        rt_nodes = _dc4("datacite:resourceType")
        declared_type_raw = None
        if rt_nodes:
            rt = rt_nodes[0]
            declared_type_raw = rt.get("resourceTypeGeneral") or (rt.text or "").strip()

        # DOI primary identifier
        identifiers: list[Identifier] = []
        doi_nodes = _dc4("datacite:identifier")
        for n in doi_nodes:
            if n.text and (n.get("identifierType") == "DOI" or "doi" in (n.text or "").lower()):
                identifiers.append(Identifier(scheme="doi", value=_strip_doi(n.text)))

        # Alternate identifiers
        for alt in _dc4("datacite:alternateIdentifiers/datacite:alternateIdentifier"):
            if alt.text:
                identifiers.append(
                    Identifier(
                        scheme=(alt.get("alternateIdentifierType") or "other").lower(),
                        value=alt.text.strip(),
                    )
                )

        # Creators with ORCID and affiliations with ROR
        creators: list[Creator] = []
        for c in _dc4("datacite:creators/datacite:creator"):
            name_el = c.find("datacite:creatorName", NS)
            if name_el is None:
                name_el = c.find("datacite3:creatorName", NS)
            name = name_el.text.strip() if name_el is not None and name_el.text else "Unknown"
            orcid = None
            for nid in c.findall("datacite:nameIdentifier", NS):
                if (nid.get("nameIdentifierScheme") or "").upper() == "ORCID" and nid.text:
                    orcid = nid.text.strip()
                    break
            affiliations = []
            for aff in c.findall("datacite:affiliation", NS):
                ror = None
                if (
                    aff.get("affiliationIdentifierScheme") or ""
                ).upper() == "ROR" and aff.get("affiliationIdentifier"):
                    ror = aff.get("affiliationIdentifier")
                affiliations.append(
                    Affiliation(name=(aff.text or "").strip() or "Unknown", ror=ror)
                )
            creators.append(Creator(name=name, orcid=orcid, affiliations=affiliations))

        # Relations (typed)
        relations: list[Relation] = []
        for rel in _dc4("datacite:relatedIdentifiers/datacite:relatedIdentifier"):
            if not rel.text:
                continue
            native = rel.get("relationType") or "Related"
            scheme = (rel.get("relatedIdentifierType") or "other").lower()
            value = rel.text.strip()
            ident = Identifier(scheme=scheme, value=value)
            # If DataCite directly gives resourceTypeGeneral, we'll use it in resolve.py
            relations.append(
                Relation(native_relation_type=native, target_identifier=ident)
            )

        # Subjects
        subjects = [
            (s.text or "").strip()
            for s in _dc4("datacite:subjects/datacite:subject")
            if s.text
        ]

        # Rights / license
        rights_nodes = _dc4("datacite:rightsList/datacite:rights")
        license_ = (
            rights_nodes[0].get("rightsURI")
            or (rights_nodes[0].text if rights_nodes[0].text else None)
            if rights_nodes
            else None
        )

        # Funders
        funders: list[Funder] = []
        for fr in _dc4("datacite:fundingReferences/datacite:fundingReference"):
            fname = fr.find("datacite:funderName", NS)
            fid = fr.find("datacite:funderIdentifier", NS)
            award = fr.find("datacite:awardNumber", NS)
            funders.append(
                Funder(
                    name=fname.text.strip() if fname is not None and fname.text else None,
                    funder_id=fid.text.strip() if fid is not None and fid.text else None,
                    award_number=award.text.strip() if award is not None and award.text else None,
                )
            )

        # Publication year
        year_nodes = _dc4("datacite:publicationYear")
        pub_date = None
        if year_nodes and year_nodes[0].text:
            try:
                pub_date = datetime(int(year_nodes[0].text.strip()), 1, 1, tzinfo=timezone.utc)
            except ValueError:
                pub_date = None

        return {
            "title": title,
            "description": description,
            "declared_type_raw": declared_type_raw,
            "identifiers": identifiers,
            "creators": creators,
            "relations": relations,
            "subjects": subjects,
            "license": license_,
            "funders": funders,
            "publication_date": pub_date,
            "creation_date": pub_date,
            "presence": presence,
        }


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _strip_doi(raw: str) -> str:
    raw = raw.strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if raw.lower().startswith(prefix):
            return raw[len(prefix) :]
    return raw


def _guess_identifier_from_string(raw: str) -> Identifier:
    s = raw.strip()
    if "doi.org/" in s.lower() or s.lower().startswith("doi:"):
        return Identifier(scheme="doi", value=_strip_doi(s))
    if "arxiv.org" in s.lower():
        return Identifier(scheme="arxiv", value=s)
    if "ncbi.nlm.nih.gov/pmc" in s.lower():
        return Identifier(scheme="pmc", value=s)
    if "softwareheritage.org" in s.lower():
        return Identifier(scheme="swh", value=s)
    if "hdl.handle.net" in s.lower():
        return Identifier(scheme="handle", value=s)
    if s.lower().startswith("http"):
        return Identifier(scheme="url", value=s)
    return Identifier(scheme="other", value=s)


def _parse_date(raw: str) -> datetime | None:
    raw = raw.strip()
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


# Retry wrapper used during live harvesting
@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=30),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
def _resumption_protected_list(sickle: Any, **kwargs: Any) -> Any:
    return sickle.ListRecords(**kwargs)
