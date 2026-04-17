"""Generate mock fixtures for demo and tests.

Run from the project root:

    python scripts/generate_mock_data.py

Produces a small but realistic corpus spanning all four mock repositories,
including the edge cases the spec requires: missing relations, malformed
DataCite, untyped relatedIdentifier, partial ORCID coverage, type-declaration
conflicts, deleted OAI records, URL-only relations, unresolvable DOIs.
"""

from __future__ import annotations

import json
import random
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MOCK_ROOT = ROOT / "data" / "mock"


OAI_DC_TEMPLATE = """<?xml version='1.0' encoding='UTF-8'?>
<record xmlns="http://www.openarchives.org/OAI/2.0/">
  <header>
    <identifier>{identifier}</identifier>
    <datestamp>{date}T00:00:00Z</datestamp>
  </header>
  <metadata>
    <oai_dc:dc
        xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/"
        xmlns:dc="http://purl.org/dc/elements/1.1/">
      <dc:title>{title}</dc:title>
      <dc:creator>{creator}</dc:creator>
      <dc:subject>{subject}</dc:subject>
      <dc:description>{description}</dc:description>
      <dc:publisher>Mock Publisher</dc:publisher>
      <dc:date>{date}</dc:date>
      <dc:type>{dtype}</dc:type>
      <dc:identifier>{doi}</dc:identifier>
      {relations}
      <dc:rights>CC-BY-4.0</dc:rights>
      <dc:language>en</dc:language>
    </oai_dc:dc>
  </metadata>
</record>
"""


DATACITE_TEMPLATE = """<?xml version='1.0' encoding='UTF-8'?>
<record xmlns="http://www.openarchives.org/OAI/2.0/">
  <header>
    <identifier>{identifier}</identifier>
    <datestamp>{date}T00:00:00Z</datestamp>
  </header>
  <metadata>
    <resource xmlns="http://datacite.org/schema/kernel-4">
      <identifier identifierType="DOI">{doi}</identifier>
      <titles><title>{title}</title></titles>
      <creators>{creators}</creators>
      <publisher>Mock Publisher</publisher>
      <publicationYear>{year}</publicationYear>
      <resourceType resourceTypeGeneral="{rtg}">{declared}</resourceType>
      <subjects><subject>{subject}</subject></subjects>
      <descriptions><description descriptionType="Abstract">{description}</description></descriptions>
      <rightsList><rights rightsURI="https://creativecommons.org/licenses/by/4.0/">CC-BY-4.0</rights></rightsList>
      <relatedIdentifiers>{related}</relatedIdentifiers>
      {funding}
    </resource>
  </metadata>
</record>
"""


DELETED_TEMPLATE = """<?xml version='1.0' encoding='UTF-8'?>
<record xmlns="http://www.openarchives.org/OAI/2.0/">
  <header status="deleted">
    <identifier>{identifier}</identifier>
    <datestamp>2023-06-01T00:00:00Z</datestamp>
  </header>
</record>
"""


MALFORMED_DATACITE = """<?xml version='1.0' encoding='UTF-8'?>
<record xmlns="http://www.openarchives.org/OAI/2.0/">
  <header>
    <identifier>oai:malformed:1</identifier>
    <datestamp>2024-01-01T00:00:00Z</datestamp>
  </header>
  <metadata>
    <resource xmlns="http://datacite.org/schema/kernel-4">
      <identifier identifierType="DOI">10.9999/malformed
      <titles><title>Broken</title></titles>
    </resource>
  </metadata>
</record>
"""


def _creator_xml(name: str, orcid: str | None, aff: str | None, ror: str | None) -> str:
    parts = [f"<creator><creatorName>{name}</creatorName>"]
    if orcid:
        parts.append(
            f'<nameIdentifier nameIdentifierScheme="ORCID">{orcid}</nameIdentifier>'
        )
    if aff:
        attr = ""
        if ror:
            attr = f' affiliationIdentifier="{ror}" affiliationIdentifierScheme="ROR"'
        parts.append(f"<affiliation{attr}>{aff}</affiliation>")
    parts.append("</creator>")
    return "".join(parts)


def _related_xml(rel_type: str, scheme: str, value: str, type_general: str | None = None) -> str:
    attrs = f'relationType="{rel_type}" relatedIdentifierType="{scheme}"'
    if type_general:
        attrs += f' resourceTypeGeneral="{type_general}"'
    return f"<relatedIdentifier {attrs}>{value}</relatedIdentifier>"


def _funding_xml(name: str, funder_id: str | None, award: str | None) -> str:
    inner = f"<funderName>{name}</funderName>"
    if funder_id:
        inner += f'<funderIdentifier funderIdentifierType="Crossref Funder ID">{funder_id}</funderIdentifier>'
    if award:
        inner += f"<awardNumber>{award}</awardNumber>"
    return f"<fundingReferences><fundingReference>{inner}</fundingReference></fundingReferences>"


# ----------------------------------------------------------------------
# Per-tier generators
# ----------------------------------------------------------------------


def gen_tier1_dspace(n: int = 30, rng: random.Random | None = None) -> None:
    rng = rng or random.Random(1)
    out = MOCK_ROOT / "oai_pmh" / "tier1_dspace_example"
    out.mkdir(parents=True, exist_ok=True)

    declared_mix = ["Article", "Text", "Text", "Thesis", "Working Paper"]
    for i in range(n):
        dtype = rng.choice(declared_mix)
        # Include URL-only relations occasionally (no DOI)
        relations = ""
        if rng.random() < 0.3:
            relations += f"<dc:relation>https://example.edu/resource/{i}</dc:relation>"
        if rng.random() < 0.2:
            relations += f"<dc:relation>doi:10.1234/tier1.{i}</dc:relation>"

        doi = f"doi:10.1234/tier1.{i}" if rng.random() < 0.4 else f"hdl.handle.net/10/{i}"

        xml = OAI_DC_TEMPLATE.format(
            identifier=f"oai:tier1:{i}",
            date="2023-05-15",
            title=f"Tier 1 study {i} on environmental monitoring",
            creator=f"Smith, J{i}",
            subject="environmental science",
            description="A short abstract on monitoring practices.",
            dtype=dtype,
            doi=doi,
            relations=relations,
        )
        (out / f"record_{i:03d}.xml").write_text(xml, encoding="utf-8")

    # One deleted record
    (out / "record_deleted.xml").write_text(
        DELETED_TEMPLATE.format(identifier="oai:tier1:deleted"), encoding="utf-8"
    )


def gen_tier2(n: int = 30, rng: random.Random | None = None) -> None:
    rng = rng or random.Random(2)
    out = MOCK_ROOT / "oai_pmh" / "tier2_datacite_partial"
    out.mkdir(parents=True, exist_ok=True)

    for i in range(n):
        # Partial ORCID / ROR: only some creators have them
        with_orcid = rng.random() < 0.4
        with_ror = rng.random() < 0.3
        creators = _creator_xml(
            f"Doe, A{i}",
            orcid=f"0000-0001-{i:04d}-0001" if with_orcid else None,
            aff="University of Example" if with_ror else None,
            ror="https://ror.org/0abcd1234" if with_ror else None,
        )
        # Some related identifiers are untyped (no resourceTypeGeneral)
        related = ""
        if rng.random() < 0.5:
            related += _related_xml(
                "IsSupplementTo", "DOI", f"10.5678/dataset.{i}", None  # untyped
            )
        if rng.random() < 0.3:
            related += _related_xml(
                "Cites", "arXiv", f"2307.{i:05d}", None
            )

        # Sometimes declared type is overloaded "Text"
        declared = rng.choice(["JournalArticle", "Text", "Text", "Report"])
        rtg = "Text" if declared == "Text" else declared

        xml = DATACITE_TEMPLATE.format(
            identifier=f"oai:tier2:{i}",
            date="2023-09-01",
            title=f"Tier 2 article {i}: partial metadata richness",
            creators=creators,
            year=2023,
            rtg=rtg,
            declared=declared,
            subject="information science",
            description="An abstract demonstrating partial DataCite population.",
            doi=f"10.5678/tier2.{i}",
            related=related,
            funding="",
        )
        (out / f"record_{i:03d}.xml").write_text(xml, encoding="utf-8")

    # Malformed record
    (out / "record_malformed.xml").write_text(MALFORMED_DATACITE, encoding="utf-8")


def gen_tier4(n: int = 30, rng: random.Random | None = None) -> None:
    rng = rng or random.Random(4)
    out = MOCK_ROOT / "oai_pmh" / "tier4_inveniordm_example"
    out.mkdir(parents=True, exist_ok=True)

    for i in range(n):
        creators = _creator_xml(
            f"Nguyen, L{i}",
            orcid=f"0000-0002-{i:04d}-0002" if rng.random() < 0.85 else None,
            aff="Example Institute",
            ror="https://ror.org/0xyz12345" if rng.random() < 0.7 else None,
        )
        related = (
            _related_xml("IsSupplementTo", "DOI", f"10.9101/data.{i}", "Dataset")
            + _related_xml("IsVersionOf", "DOI", f"10.9101/preprint.{i}", "Text")
            + (_related_xml("References", "DOI", f"10.9102/art.{i}", "JournalArticle")
               if rng.random() < 0.6 else "")
            + (_related_xml("IsDocumentedBy", "DOI", f"10.9103/software.{i}", "Software")
               if rng.random() < 0.4 else "")
        )
        funding = _funding_xml(
            "National Science Foundation",
            funder_id="https://doi.org/10.13039/100000001" if rng.random() < 0.7 else None,
            award=f"NSF-{2000+i}" if rng.random() < 0.6 else None,
        ) if rng.random() < 0.75 else ""

        declared = rng.choice(["JournalArticle", "JournalArticle", "Dataset", "Software"])
        rtg_map = {
            "JournalArticle": "JournalArticle",
            "Dataset": "Dataset",
            "Software": "Software",
        }

        xml = DATACITE_TEMPLATE.format(
            identifier=f"oai:tier4:{i}",
            date="2024-03-10",
            title=f"Tier 4 publication {i}: rich relational metadata",
            creators=creators,
            year=2024,
            rtg=rtg_map[declared],
            declared=declared,
            subject="scholarly communication",
            description="Rich metadata with typed relations and funder identifiers.",
            doi=f"10.9100/tier4.{i}",
            related=related,
            funding=funding,
        )
        (out / f"record_{i:03d}.xml").write_text(xml, encoding="utf-8")


def gen_zenodo(n: int = 30, rng: random.Random | None = None) -> None:
    rng = rng or random.Random(3)
    out = MOCK_ROOT / "zenodo"
    out.mkdir(parents=True, exist_ok=True)

    for i in range(n):
        creators = [
            {
                "name": f"Kowalski, K{i}",
                "orcid": f"0000-0003-{i:04d}-0003" if rng.random() < 0.75 else None,
                "affiliation": "Zenodo Example University" if rng.random() < 0.7 else None,
            }
        ]
        related: list[dict] = []
        if rng.random() < 0.5:
            related.append({
                "identifier": f"10.5281/zenodo.{1000+i}",
                "scheme": "doi",
                "relation": "isSupplementedBy",
            })
        if rng.random() < 0.4:
            related.append({
                "identifier": f"2307.{i:05d}",
                "scheme": "arxiv",
                "relation": "isVersionOf",
            })
        if rng.random() < 0.3:
            related.append({
                "identifier": f"https://github.com/example/repo{i}",
                "scheme": "url",
                "relation": "isSupplementedBy",
            })
        if rng.random() < 0.2:
            # Unresolvable DOI (bad prefix)
            related.append({
                "identifier": f"10.99999/unresolvable.{i}",
                "scheme": "doi",
                "relation": "cites",
            })

        # Type-declaration conflict: occasionally mark as article but clearly a dataset
        is_conflict = rng.random() < 0.1
        if is_conflict:
            rtype = {"type": "publication", "subtype": "article"}
            title = f"Dataset {i} measurements (csv)"  # dataset-ish title
        else:
            rtype = {"type": "publication", "subtype": "article"}
            title = f"Zenodo article {i}: open access study"

        doc = {
            "id": 10000 + i,
            "doi": f"10.5281/zenodo.{10000+i}",
            "metadata": {
                "title": title,
                "description": f"Abstract for study {i}. "
                               "Explores documentary status in OA infrastructure.",
                "publication_date": "2024-06-01",
                "creators": creators,
                "related_identifiers": related,
                "resource_type": rtype,
                "keywords": ["open access", "scholarly communication"],
                "license": {"id": "CC-BY-4.0"},
                "language": "en",
                "grants": [
                    {
                        "code": f"GRANT-{i}",
                        "funder": {"name": "European Commission",
                                   "doi": "https://doi.org/10.13039/501100000781"},
                    }
                ] if rng.random() < 0.5 else [],
            },
            "files": [{"key": f"article_{i}.pdf"}] if rng.random() < 0.85 else [],
            "links": {"self": f"https://zenodo.org/api/records/{10000+i}"},
        }
        (out / f"record_{i:03d}.json").write_text(
            json.dumps(doc, indent=2), encoding="utf-8"
        )


def main() -> None:
    MOCK_ROOT.mkdir(parents=True, exist_ok=True)
    gen_tier1_dspace()
    gen_tier2()
    gen_tier4()
    gen_zenodo()
    print("mock data generated under", MOCK_ROOT)


if __name__ == "__main__":
    main()
