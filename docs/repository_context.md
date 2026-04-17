# Repository context

The `available-vs-used` decomposition in the capability profile (see
`docs/scoring.md`) partially separates **infrastructural capacity** from
**documentary practice**. It does not, however, fully separate
**curation policy** from **depositor behavior** — both of which show up
as "used" affordances in the metrics. This document records, per
repository, the qualitative context the paper's discussion needs in
order to interpret observed patterns responsibly.

Fill in each field at harvest time from the repository's published
documentation, policy pages, and (where available) published studies of
the repository's deposit practices. This file is referenced in the
paper's methods and limitations sections.

## Schema

For each repository, record:

- **Deposit model.** Mediated (librarian- or editor-checked before
  publication), self-archived (depositor controls metadata), or hybrid.
- **Mandatory metadata fields.** What the repository's deposit workflow
  requires. This directly shapes "used" rates for those fields.
- **DOI assignment policy.** Does the repository mint DOIs
  automatically (DataCite client), on request, or not at all? This
  directly shapes identifier-based analyses.
- **Aggregator vs primary.** Is the repository a primary deposit site
  for the material it carries, or does it aggregate from elsewhere?
  Aggregators inherit schema limitations from their sources.
- **Known curation interventions.** Published policies or studies
  describing metadata enrichment, crosswalk normalization, or deposit
  rejection criteria that might inflate or depress observed field
  populations.
- **Known caveats.** Any repository-specific quirks relevant to the
  analysis (e.g. known overloaded type labels, ORCID-mandate timelines,
  ROR-rollout dates).

## Entries

### tier1_dspace_example (anchor for Tier 1)

- Deposit model: _(fill in)_
- Mandatory fields: _(fill in)_
- DOI assignment: _(fill in)_
- Aggregator vs primary: _(fill in)_
- Curation interventions: _(fill in)_
- Caveats: DSpace's `Text` dc:type is overloaded; the type mapping
  downgrades confidence on `Text` so the rule-based classifier can
  override. Handle-based identifiers predominate; DOI coverage depends
  on institutional policy.

### tier2_datacite_partial (anchor for Tier 2)

- Deposit model: _(fill in)_
- Mandatory fields: _(fill in)_
- DOI assignment: _(fill in)_
- Aggregator vs primary: _(fill in)_
- Curation interventions: _(fill in)_
- Caveats: Partial DataCite exposure means some records carry typed
  relations and others carry only DC-level `dc:relation`. The capability
  profile separates them per-record via `FieldPresenceFlags`.

### zenodo (anchor for Tier 3)

- Deposit model: Self-archived; depositors control metadata with light
  automated validation.
- Mandatory fields: Title, creators (at least one), resource type,
  upload type; license, description, publication date.
- DOI assignment: Automatic DataCite DOI minting on publication. This
  gives Zenodo universal DOI coverage and therefore universal DOI-based
  identifier presence.
- Aggregator vs primary: Primary deposit site; not an aggregator.
- Curation interventions: Light; some community-curated sub-collections
  enforce additional metadata standards.
- Caveats: ROR is not exposed in the public v1 REST API, so the
  FieldPresenceFlags record `has_affiliation_ror_field: false` for
  Zenodo. This means Zenodo's adjusted agent score divides by a smaller
  denominator than a ROR-exposing repository's; the paper must discuss
  this explicitly. Zenodo's `related_identifiers` list is typed but the
  type vocabulary is DataCite's, so typed-relation presence is
  comparable with DataCite-based repositories.

### tier4_inveniordm_example (anchor for Tier 4)

- Deposit model: _(fill in)_
- Mandatory fields: _(fill in)_
- DOI assignment: _(fill in)_
- Aggregator vs primary: _(fill in)_
- Curation interventions: _(fill in)_
- Caveats: If a rich custom schema exposes funder/project linking
  fields that the v0.2 normalized schema does not capture, extend the
  schema and bump `SCHEMA_VERSION`. Silent field-dropping is a bug.

## Discussion template for the paper

Pattern: "Repository X shows high relational embeddedness in articles.
Its deposit model is {mediated | self-archived | hybrid}; {N} metadata
fields are mandatory at deposit including {list}. This suggests that
the observed pattern {is / is not} plausibly attributable to curation
policy rather than depositor behavior." Fill this in per repository for
the paper's discussion section, using the entries above.
