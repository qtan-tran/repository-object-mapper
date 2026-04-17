# Methods

This document is the narrative methods reference, intended as a drafting
source for the paper's Methods section. It describes the pipeline as
executed, including decisions made at implementation time that the paper
must disclose for reproducibility.

## Overview

The pipeline harvests normalized metadata records from a stratified
sample of open access repositories, classifies each record's object type
with a hierarchical rule set, resolves outgoing relational identifiers to
typed targets through a cached micro-pipeline, and scores each record on
three embeddedness dimensions in both raw and available-adjusted forms.
The stages are orchestrated by a `typer`-based CLI (`rom`) whose
subcommands are idempotent and resumable; state lives in `output/` and
`data/cache/` and rerunning any stage never corrupts prior results.

## Sampling

v0.2 implements a deliberately limited stratified design: one
representative repository per a priori schema tier, four tiers total,
≈1,500 article records per repository, yielding an article corpus of
≈6,000 records. Non-article records from the same harvests are retained
for the within-repository object-type comparison. Sampling is systematic
with `random_seed = 42`; the sampling frame is recorded in
`config/sample_v0_2.yaml` and validated by `rom sample`.

Tier assignments are **a priori classifications validated empirically**
against each repository's capability profile. Where the two diverge, the
empirical tier from the profile is primary in analysis and the
discrepancy is reported.

## Harvest and normalization

Two adapters share a common `AdapterBase`:

- A **generic OAI-PMH adapter** used for tiers 1, 2, and (typically) 4.
  It negotiates the richest available metadata format in the order
  `datacite4 > oai_datacite > oai_dc`, logs the negotiation decision,
  and exposes both the negotiated format and a static declaration of
  which fields that format permits. It uses `sickle` for iteration with
  `tenacity`-backed retry; per-page checkpointing (written atomically)
  allows resumption without restart after resumption-token failures.
- A **Zenodo REST adapter** for tier 3 using `httpx`, page-based
  pagination, a contact email in the User-Agent header, and per-request
  rate limiting. It queries
  `resource_type.type:publication AND resource_type.subtype:article`.

Every record's raw native response (XML or JSON) is persisted under
`output/records_raw/<repository>/` before normalization; the raw bytes
are never discarded. A `HarvestProvenance` block (timestamp, endpoint,
format negotiated, HTTP status, adapter name and version) is carried on
every normalized record.

Parsing is defensive: missing fields are explicitly null rather than
absent from the normalized record, and every record carries a
`FieldPresenceFlags` block recording *schema-level* availability of
relations, creator ORCIDs, affiliation RORs, funders, license, subjects,
and full-text indicators. This is the central mechanism for separating
"field not present in source" from "field present but empty" — a
distinction the analysis depends on.

## Object-type classification

A two-pass hierarchical classifier (`classify.py`) assigns each record
an `ObjectType` drawn from a closed vocabulary (`article`, `dataset`,
`thesis`, `software`, `book`, `book_chapter`, `preprint`,
`conference_paper`, `report`, `supplementary_material`, `other`) and a
confidence level (`high`, `medium`, `low`).

1. The record's declared type is mapped via the documented
   `config/type_mapping.yaml`. Overloaded source types (e.g. DSpace's
   `Text`, which covers articles, reports, and theses) are mapped with
   `confidence: low` so the rule-based pass can override them.
2. A rule-based classifier examines title/description keywords, DOI
   registrant prefixes (e.g. arXiv, bioRxiv), filename extensions, and
   ISBN/ISSN identifier hints.

Decision logic preserves the declared type when its confidence is
`high`; otherwise the rule-based verdict is preferred when declared
confidence is `low`. Every instance of declared-vs-rule disagreement is
flagged on the record (`type_disagreement = true`) and logged; the
per-repository disagreement rate is reported as a data-quality
indicator (`output/classification_disagreement.json`).

Manual validation labels for a stratified sample of 200 records (50 per
repository) are committed to `data/validation/labels.csv` for
reproducibility. Per-repository and per-type accuracy are reported.

## Resolution

Identifier resolution is treated as a separate micro-pipeline with its
own persistent state (`data/cache/resolution.db`), its own CLI
subcommand (`rom resolve`), and its own reporting. The cache is keyed
by `scheme:value` and stores the resolver used, HTTP status, raw
response, resolved `ObjectType`, and resolution tier. It is idempotent
across runs with a configurable staleness window (default 90 days).

Three tiers are reported, never conflated:

1. **Fully typed.** DOI resolved via Crossref or DataCite returns a
   structured `type`, or the source record's DataCite
   `relatedIdentifier` carries `resourceTypeGeneral` directly.
2. **Weakly typed.** Identifier pattern alone maps to a type (arXiv →
   preprint, Software Heritage → software, PMC → article) without API
   confirmation.
3. **Unresolved.** URL only, failed DOI lookup, or unknown scheme.

A **500-identifier pilot** runs first (`rom resolve-pilot`), sampling
Zenodo relations, and writes `docs/resolution_pilot.md`. If the
fully-typed rate is materially below expectation, object embeddedness
claims are conditioned on resolution tier; sensitivity analyses under
the `fully-only` and `fully+weakly` inclusion policies are reported.

Crossref and DataCite requests identify themselves via a User-Agent
containing a contact email, use exponential backoff via `tenacity`, and
respect a per-second request rate configured in `config.contact_email`
and `config.request_rate_per_second`.

## Capability profile

For each repository, `rom harvest` and `rom classify` together produce
a `repository_profile.json` entry that records, separately:

- **Available affordances.** Which relation field types appear anywhere
  in the raw corpus; which identifier slots the schema exposes; the
  adapter's static declaration of what the negotiated format permits.
- **Used affordances** (among article records). The proportion
  populating each native relation type; the proportion with ORCID on
  at least one creator; the proportion with ROR on at least one
  affiliation; the proportion with a funder identifier.
- **Resolved-object-type distribution** across article records'
  relations, per resolution tier.

The profile also reports an **empirical tier indicator** inferred from
the observed data; where this diverges from the a priori tier, the
empirical value is primary in analysis.

The capability profile is a **first-class paper artifact**, not a
diagnostic appendix, because it independently supports the decentering
argument: even without cross-tier inferential tests, showing that
rich-schema repositories expose relational affordances that poor-schema
repositories do not is substantive evidence.

## Embeddedness scoring

Three dimensions are computed per record, each in raw and
available-adjusted forms. Exact formulas, with hand-calculated worked
examples, are in `docs/scoring.md`; the executable counterpart is
`tests/test_score.py`.

- **Relational embeddedness.** Raw: `log(1 + |R|) + |T|/10`, where `R`
  is the relation set and `T` its distinct native-type set. Adjusted:
  `|T| / available_relation_types` (clipped at 1).
- **Agent embeddedness.** Raw: mean of four components — ORCID coverage
  ratio among creators, indicator for any ROR on an affiliation,
  indicator for any funder identifier, indicator for any project
  identifier. Adjusted: observed identifier types over schema-exposed
  identifier slots.
- **Object embeddedness.** Raw: `log(1 + |R^π|) + |S^π|/10`, where `R^π`
  is the set of relations resolved under policy π (fully-only, or
  fully+weakly), and `S^π` is the set of distinct resolved object
  types. Adjusted: `|S^π| / K_ρ`, where `K_ρ` is the infrastructure
  proxy (count of distinct native relation types in the repository's
  corpus).

Raw scores are pooled min-max normalized to `[0, 1]` across the v0.2
corpus. Adjusted scores are already ratios. A secondary composite
`overall_embeddedness_score` is the equal-weight mean of the three
normalized raw dimensions; `article_autonomy_score = 1 − overall` is
retained as a legacy inverse only.

## Analysis

- **Per-repository descriptives.** Mean and 95% bootstrap CI (2,000
  iterations) on each scoring column, restricted to articles with
  `medium` or `high` classification confidence.
- **Cross-tier exploratory test.** Kruskal–Wallis across a priori
  tiers on each scoring column, with ε² effect size. Reported with an
  explicit low-power caveat at n = 4 repositories.
- **Primary statistically defensible test — within-repository
  comparison.** For each repository, Kruskal–Wallis across `article |
  dataset | software` on each scoring column, with ε² effect size, and
  pairwise Mann–Whitney U with rank-biserial effect size for `article
  vs dataset` and `article vs software`. With hundreds to thousands of
  records per repository, this test is genuinely powered.
- **Sensitivity analyses.** Results are reported under both
  `fully-only` and `fully+weakly` resolution-inclusion policies, and
  under both `medium+high` and `all` confidence thresholds.

Results are emitted in machine-readable (`output/analysis/results.json`)
and human-readable (`output/analysis/results.md`) forms.

## Figures

Generated by `rom visualize` into `output/figures/`:

- KDE distributions per dimension, one trace per repository.
- Per-repository boxplots comparing `article`, `dataset`, `software`,
  `preprint`, and `thesis` on each dimension.
- Tier-vs-dimension scatter plots with per-repository points, rendered
  separately for raw and available-adjusted scores.
- Capability-profile heatmap (repositories × native relation types, cells
  = article population rate).
- Network graph centered on a selected Zenodo article with its resolved
  relational context, colored by resolved object type.

## Reporting

`rom report` assembles `output/report.md` from the capability profile,
classification validation, resolution report, and analysis results —
a methods-ready summary that can be pasted near-verbatim into the
paper.

## Handling of conflation risks

Measured differences across repositories can arise from schema capacity,
repository curation policy, or depositor behavior. The available-vs-used
decomposition partially separates schema capacity from the other two.
The residual — curation policy versus depositor behavior — is addressed
qualitatively in `docs/repository_context.md`, which records for each
repository its deposit model (mediated / self-archived / hybrid), known
mandatory metadata fields, DOI assignment policy, and aggregator-vs-primary
status. These factors are discussed explicitly in the paper's discussion.
