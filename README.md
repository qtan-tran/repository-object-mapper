# repository-object-mapper

An empirical pipeline for measuring how scholarly articles are **embedded**
within the metadata infrastructures of open access repositories.
Part of a forthcoming *Journal of [XXX]* article on the changing
documentary status of the scholarly article in open access infrastructures.

> **v0.2 — paper-submittable minimum.** Four repositories, one per schema
> tier, ~1,500 articles per repository (≈6,000 article records total), plus
> non-article records for the within-repository object-type comparison.
> v0.5 expands to ~20 repositories (see `ROADMAP.md`); the pipeline is
> designed to scale without rewrite.

---

## Research question and hypothesis

The paper argues that the scholarly article is **symbolically central but
infrastructurally decentered** in contemporary open access infrastructures:
it remains the legitimating unit of scholarship while being represented in
repository systems as a node in a relational documentary assemblage.

**H2 (primary).** The documentary autonomy of the scholarly article in open
repositories is inversely related to the relational richness of the
repository's metadata infrastructure.

**H0.** Article-record embeddedness does not vary systematically with
repository metadata schema richness.

## Theoretical framing

The argument proceeds from Briet's proposition that a document is any object
treated as evidence, extended by Buckland's "information-as-thing" and by
Frohmann's emphasis on documentary *practice* over documentary *content*.
Borgman's account of scholarly infrastructures and Bowker & Star's
classification-as-infrastructure show that metadata schemas are not neutral
containers but active shapers of what a document can be. More recently,
Blanchette's *Burdens of Proof* and Moore's work on the political economies
of open access have foregrounded how the material specifics of digital
representation (i.e., identifier schemes, relation types, agent identifiers)
constitute a document's documentary status. This pipeline operationalizes
that framing: it measures the degree to which an article record, as carried
by repository metadata, remains an autonomous documentary object versus
existing as one node in a relational graph.

## The critical conceptual distinction: available vs used affordances

A single reviewer-facing risk dominates this work: measured cross-repository
differences in embeddedness may reflect **depositor behavior or curation
policy**, not **infrastructural structure**. The pipeline addresses this
head-on by computing two parallel quantities per repository:

- **Available affordances** — which relation fields, agent identifier slots,
  and linked-object types the schema *permits* and the repository *exposes*.
  A property of infrastructure.
- **Used affordances** — which of those fields are actually populated in
  harvested article records. A property of depositor behavior and curation.

Both are reported. The paper interprets the relationship between them:
H2 concerns their interaction, not either alone. If articles are poorly
embedded even in rich-schema repositories, that is not a refutation of
decentering — it is a *refinement*, evidence that infrastructural capacity
outruns documentary practice. This distinction is built into the
`repository_profile.json`, into the raw-vs-adjusted scoring forms, and into
the paper's discussion.

## Installation

```bash
git clone https://github.com/EXAMPLE/repository-object-mapper.git
cd repository-object-mapper
pip install -e ".[dev]"
```

Python ≥ 3.10. See `requirements.txt` for the runtime-only install.

## CLI pipeline

The pipeline is a sequence of idempotent, resumable stages that are orchestrated by
`typer`. Each stage reads and writes files under `output/`; rerunning any
stage never corrupts prior results. `rom resolve` owns its own SQLite state
at `data/cache/resolution.db` and is independently runnable.

```bash
# Validate the sampling frame
rom sample --config config/sample_v0_2.yaml

# Harvest normalized records + emit capability profile
rom harvest --config config/sample_v0_2.yaml --mock   # use --live for real data

# Hierarchical object-type classification with confidence
rom classify

# 500-identifier resolution pilot (writes docs/resolution_pilot.md)
rom resolve-pilot --mock

# Full resolution pass against the SQLite cache
rom resolve --mock

# Compute embeddedness dimensions (raw + available-adjusted)
rom score

# H2 exploratory test + within-repository object-type comparison
rom analyze

# Figures + Zenodo article network graph
rom visualize

# Methods-ready summary
rom report
```

Or run the whole pipeline on mock data with one command:

```bash
make demo
```

## v0.2 sampling design and its limitations

v0.2 uses a deliberately limited but (fairly) principled stratified design:

| Tier | Description                        | Repository (anchor)                                |
| ---- | ---------------------------------- | -------------------------------------------------- |
| 1    | Basic Dublin Core via OAI-PMH      | DSpace 6 institutional repository                  |
| 2    | DC + partial DataCite              | national or institutional repo with `oai_datacite` |
| 3    | Full DataCite with typed relations | Zenodo (REST)                                      |
| 4    | Rich custom/extended schema        | InvenioRDM or Dataverse                            |

Target: ~1,500 article records per repository, ≈6,000 total, plus
non-article records for the within-repository comparison. See
`config/sample_v0_2.yaml` for the committed choices.

**Limitations of the v0.2 design, stated plainly:**

- n = 4 repositories. The cross-tier H2 test is **exploratory**, not
  statistically decisive.
- The **primary statistically defensible test is the within-repository
  object-type comparison**: within each repository, do articles exhibit
  lower embeddedness than datasets or software? With hundreds to thousands
  of records per repository, this is genuinely powered.
- Tier assignments are **a priori classifications validated empirically**
  against the capability profile. Where they diverge, the empirical tier is
  primary in analysis and the discrepancy is reported.
- No longitudinal inference. No reading or citation behavior claims. Only
  repository metadata representation.
- Measured differences may reflect schema capacity, curation policy, or
  depositor behavior. The available-vs-used decomposition partially
  addresses this; qualitative discussion of the residual in
  `docs/repository_context.md` addresses the rest.

## Scoring methodology

Three theoretically distinct dimensions are computed per record, each in
**raw** and **available-adjusted** forms. Exact formulas are in
`docs/scoring.md`, with hand-calculated worked examples. The executable
counterpart is `tests/test_score.py`.

1. **Relational embeddedness** — breadth and variety of the record's typed
   relations. Raw = `log(1 + relation_count) + distinct_types/10`.
   Adjusted = `used_relation_types / available_relation_types`.

2. **Agent embeddedness** — ORCID coverage, ROR presence, funder / project
   identifiers. Raw = mean of four presence components.
   Adjusted = observed identifier types / schema-exposed identifier slots.

3. **Object embeddedness** — presence and typed diversity of resolved links
   to other object classes. Computed under **fully-typed-only** (primary)
   and **fully+weakly-typed** (sensitivity) resolution-inclusion policies.
   Adjusted normalizes by the repository's infrastructural capacity proxy.

A secondary composite `overall_embeddedness_score` is the equal-weight mean
of the three normalized raw dimensions.
`article_autonomy_score = 1 − overall_embeddedness_score` is a legacy
inverse, kept for backward-compatible reporting only.

## Resolution pipeline

Identifier resolution is the highest-impact technical risk in this work.
It is treated as a **separate micro-pipeline** with its own SQLite cache
(`data/cache/resolution.db`), its own CLI subcommand (`rom resolve`), and
its own reporting (`output/resolution_report.json`). Re-running is cheap
(cache hits); cache survives v0.2 → v0.5.

Three resolution tiers are reported, never conflated:

1. **Fully typed** — Crossref / DataCite API returns a structured
   `type`, or DataCite `relatedIdentifier` supplies `resourceTypeGeneral`
   directly.
2. **Weakly typed** — identifier pattern alone maps to a type
   (arXiv → preprint, Software Heritage → software, PMC → article) without
   API confirmation.
3. **Unresolved** — URL only, failed DOI lookup, or unknown scheme.

The pilot (`rom resolve-pilot`) runs on 500 identifiers from Zenodo *first*,
before the final resolution pass, and writes `docs/resolution_pilot.md`.
If the fully-typed rate is materially below expectation, object
embeddedness claims must be conditioned on resolution tier; sensitivity
analyses under each inclusion policy are reported.

## Reproducibility

- Fixed random seeds in `config/sample_v0_2.yaml`.
- `PRE_ANALYSIS_PLAN.md` is committed before final analysis.
- `DATA_AVAILABILITY.md` describes the Zenodo deposit at paper submission.
- `make demo` reproduces the full pipeline on committed mock data in
  under a minute.
- MIT license. `CITATION.cff` provided.

## Outputs

All outputs land in `output/` (gitignored). A sample subset is committed
under `output/sample/`.

- `records_raw/` — raw native metadata per record, organized by repository
- `records_normalized.parquet` — canonical normalized records
- `relations.parquet` — one row per relation edge with resolved target type
- `scores.parquet` — per-record embeddedness scores (raw + adjusted)
- `repository_profile.json` — **per-repository capability profile**
  (available vs used), a primary paper artifact
- `repository_summary.csv` — per-repository descriptive statistics
- `resolution_report.json` — resolution tier breakdown per repository
- `classification_validation.json` — manual validation results
- `analysis/` — test statistics, sensitivity analyses
- `figures/` — distributions, boxplots, scatter, capability heatmap, network
- `report.md` — methods-ready summary

## Limitations

- **Scope.** Repository metadata representation only. No claims about
  citation, reading, or use.
- **n = 4 repositories at v0.2.** Cross-tier inference is exploratory; the
  within-repository comparison carries the statistical weight.
- **Conflation risk.** Schema capacity, curation policy, and depositor
  behavior are not fully separable without repository-level intervention
  data. The available-vs-used decomposition partially isolates them; the
  residual is addressed qualitatively in `docs/repository_context.md`.
- **Resolution coverage.** Object embeddedness is conditioned on resolution
  tier. Repositories whose relations are primarily URL-only cannot be
  compared on the object dimension on equal footing with repositories
  whose relations are primarily DOI-based.
- **No longitudinal inference.** v0.2 is a cross-sectional snapshot.

## Roadmap to v0.5 and v1.0

See `ROADMAP.md` for the full expansion specification. Summary:

- v0.5 widens sampling to 20 repositories (4 per stratum cell across
  institutional / disciplinary / national / funder-mandated / generalist
  repositories × schema tier 1–4), adds dedicated adapters for Figshare,
  DSpace 7+ REST, Dataverse, and standalone InvenioRDM, scales manual
  validation to 1,000 records with inter-rater reliability, and upgrades
  the analysis to a mixed-effects regression of record-level embeddedness
  on repository-level tier with repository as a random effect.
- v1.0 accompanies the final, revised manuscript. The schema, scoring,
  and pre-analysis plan remain stable v0.2 → v1.0. Any scoring change is
  documented in `CHANGELOG.md`; if v0.2 reveals a scoring error, v0.2 is
  re-run with the correction and re-deposited before proceeding.

## License

MIT. See `LICENSE`.

## Citation

See `CITATION.cff`.
