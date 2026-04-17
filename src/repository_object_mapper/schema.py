"""Normalized pydantic v2 schema for harvested repository records.

The schema is intentionally small and stable: every record must be serializable
to parquet, every field must survive round-tripping to JSON, and every
``schema_version`` change must be logged in CHANGELOG.md. v0.5 will not change
these model shapes — new repositories are accommodated via adapters, not via
schema extension.

Explicit missingness
--------------------
Two states are distinguished throughout:

- ``field_present_in_source=False`` — the source format did not carry this
  field at all (e.g. ``oai_dc`` record lacking a relation slot).
- ``field_present_in_source=True`` with an empty list / null value — the
  source exposes the field but it was not populated in this record.

Conflating these destroys signal about depositor behavior versus schema
capacity. Adapters populate both the value and the "present" flag.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from . import SCHEMA_VERSION


class ObjectType(str, Enum):
    """Closed vocabulary of object-type classifications.

    See ``classify.py`` for the hierarchical rules that assign values.
    """

    ARTICLE = "article"
    DATASET = "dataset"
    THESIS = "thesis"
    SOFTWARE = "software"
    BOOK = "book"
    BOOK_CHAPTER = "book_chapter"
    PREPRINT = "preprint"
    CONFERENCE_PAPER = "conference_paper"
    REPORT = "report"
    SUPPLEMENTARY_MATERIAL = "supplementary_material"
    OTHER = "other"


class ConfidenceLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ResolutionTier(str, Enum):
    """Resolution outcome classification per identifier.

    Matches the three tiers defined in the spec's resolution section.
    """

    FULLY_TYPED = "fully_typed"
    WEAKLY_TYPED = "weakly_typed"
    UNRESOLVED = "unresolved"


class Identifier(BaseModel):
    """A single identifier attached to a record (local, DOI, handle, URL, ...)."""

    model_config = ConfigDict(extra="forbid")

    scheme: str  # "doi", "handle", "local", "url", "arxiv", "pmc", "urn", ...
    value: str


class Creator(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    orcid: str | None = None
    affiliations: list[Affiliation] = Field(default_factory=list)


class Affiliation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    ror: str | None = None


# Resolve forward reference
Creator.model_rebuild()


class Funder(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    funder_id: str | None = None  # e.g. ROR, Crossref Funder ID, Fundref
    award_number: str | None = None
    project_id: str | None = None


class Relation(BaseModel):
    """A single outgoing relation to another object.

    The ``native_relation_type`` preserves the exact label emitted by the
    source schema (``IsSupplementTo``, ``isPartOf``, ``dcterms:references``,
    ...). Normalization is deferred to analysis so that we do not destroy the
    capability-profile evidence by collapsing labels too eagerly.
    """

    model_config = ConfigDict(extra="forbid")

    native_relation_type: str
    target_identifier: Identifier
    # The following are populated by ``resolve.py`` and are null pre-resolution.
    resolved_object_type: ObjectType | None = None
    resolution_tier: ResolutionTier | None = None


class HarvestProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp: datetime
    endpoint: str
    format_negotiated: str
    http_status: int | None = None
    adapter_name: str
    adapter_version: str


class FieldPresenceFlags(BaseModel):
    """Per-record flags recording *schema-level* availability of key fields.

    Distinguishes "source format exposes this field" from
    "source populated this field." Populated by the adapter before
    parsing values.
    """

    model_config = ConfigDict(extra="forbid")

    has_relation_field: bool = False
    has_creator_orcid_field: bool = False
    has_affiliation_ror_field: bool = False
    has_funder_field: bool = False
    has_license_field: bool = False
    has_subject_field: bool = False
    has_fulltext_indicator_field: bool = False


class NormalizedRecord(BaseModel):
    """The canonical record emitted by every adapter.

    Analysis code reads only from this model; adapter-specific peculiarities
    are confined to ``adapters/``. The ``raw_path`` points to the raw native
    response on disk; the raw bytes are never discarded.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.2"] = SCHEMA_VERSION  # type: ignore[assignment]

    # Source bookkeeping
    repository_name: str
    repository_a_priori_tier: int = Field(ge=1, le=4)
    local_identifier: str
    raw_path: str
    provenance: HarvestProvenance

    # Identifiers and content
    identifiers: list[Identifier] = Field(default_factory=list)
    title: str | None = None
    description: str | None = None
    publication_date: datetime | None = None
    creation_date: datetime | None = None

    # Agents
    creators: list[Creator] = Field(default_factory=list)
    funders: list[Funder] = Field(default_factory=list)

    # Descriptive metadata
    subjects: list[str] = Field(default_factory=list)
    license: str | None = None
    language: str | None = None
    full_text_available: bool | None = None

    # Relations (populated pre-resolution; resolved_* fields set later)
    relations: list[Relation] = Field(default_factory=list)

    # Classification (populated by ``classify.py``)
    declared_type_raw: str | None = None
    object_type: ObjectType | None = None
    object_type_confidence: ConfidenceLevel | None = None
    type_disagreement: bool = False  # declared vs rule-based disagreement

    # Field-level availability flags
    presence: FieldPresenceFlags = Field(default_factory=FieldPresenceFlags)

    # Free-form extras for adapter-specific debug context (not used in analysis)
    extras: dict[str, Any] = Field(default_factory=dict)
