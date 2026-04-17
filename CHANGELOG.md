# Changelog

All notable changes to this project are recorded here. The scoring formulas,
normalized schema, three embeddedness dimensions, type classification logic,
available-vs-used distinction, and pre-analysis plan remain stable between
versions unless explicitly documented here with a justification. If a
post-hoc change to scoring is made, the affected version is re-run with the
corrected formula and re-deposited on Zenodo.

## [0.2.0] — 2026-04-17

### Added
- Normalized pydantic v2 schema (`SCHEMA_VERSION = "0.2"`) with explicit
  `FieldPresenceFlags` distinguishing "field not present in source" from
  "field present but empty."
- Adapter framework: `AdapterBase`, `OAIPMHAdapter` (format-negotiating
  `datacite4 > oai_datacite > oai_dc`), `ZenodoAdapter` (REST).
  `AdapterStub` demonstrates the v0.5 extension pattern.
- Hierarchical object-type classifier with confidence levels and per-record
  declared-vs-rule-based disagreement tracking.
- SQLite-backed resolution cache (`data/cache/resolution.db`) with
  configurable staleness window; three-tier resolution (fully, weakly,
  unresolved).
- 500-identifier resolution pilot (`rom resolve-pilot`) writing
  `docs/resolution_pilot.md`.
- Three embeddedness dimensions (relational, agent, object), each in raw
  and available-adjusted forms, pooled min-max normalized across corpus.
- Per-repository capability profile (`repository_profile.json`) as a
  first-class paper artifact.
- Statistical analysis: per-repository bootstrap CI, cross-tier
  Kruskal–Wallis (exploratory), within-repository object-type Kruskal–Wallis
  with Mann–Whitney pairwise effect sizes (primary defensible test).
- Figures: distributions, per-type boxplots, tier-vs-embeddedness scatter
  (raw and adjusted), capability heatmap, Zenodo article network graph.
- CLI (`rom`) with nine resumable, idempotent subcommands.
- Pytest suite covering parsing, classification, resolution cache and tier
  assignment, scoring with hand-calculated expectations, capability profile,
  end-to-end smoke test on mocks.

### Notes
- Tier assignments are a priori; empirical tier from the capability profile
  takes precedence in analysis where the two diverge.
- The cross-tier H2 test is exploratory at v0.2 (n=4 repositories).
  The within-repository object-type comparison is the primary statistically
  defensible test.
