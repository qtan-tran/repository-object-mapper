# Pre-analysis plan — v0.2

This document is committed **before** the final analysis run on live
repository data. It specifies hypotheses, tests, sample design, exclusion
criteria, and scoring formulas in their raw and available-adjusted forms.
Any deviation from this plan in the submitted paper is reported as a
deviation, not silently revised.

## Hypotheses

- **H2 (primary).** The documentary autonomy of the scholarly article in
  open repositories is inversely related to the relational richness of the
  repository's metadata infrastructure.
- **H0.** Article-record embeddedness does not vary systematically with
  repository metadata schema richness.

## Sample design

Stratified: one repository per a priori schema tier.

| Tier | A priori characterization |
|---|---|
| 1 | Basic Dublin Core via OAI-PMH (`oai_dc` only) |
| 2 | DC + partial DataCite |
| 3 | Full DataCite with typed relations |
| 4 | Rich custom/extended schema with funder/project linking |

Per repository: approximately 1,500 article records, sampled systematically
with `random_seed = 42`. Total target ≈ 6,000 article records. Non-article
records from the same harvests are retained for the within-repository
comparison.

Repositories are documented in `config/sample_v0_2.yaml`. Tier assignments
are a priori classifications, **validated empirically** against the
capability profile at harvest time. Where the empirical profile contradicts
the a priori tier, the empirical tier is used as the primary tier indicator
in analysis and the discrepancy is reported in methods.

## Scoring formulas

**Relational embeddedness**

- Raw: `relational_raw = log(1 + relation_count) + distinct_relation_types / 10`
- Adjusted: `relational_adjusted = used_relation_types / available_relation_types`

**Agent embeddedness**

- Raw components (each in `[0, 1]`):
  - ORCID coverage ratio among creators
  - ROR present on any affiliation (indicator)
  - Funder identifier present on any funder (indicator)
  - Project identifier present on any funder (indicator)
- Raw = mean of the four components
- Adjusted = observed identifier types / schema-exposed identifier slots

**Object embeddedness**

- Raw = `log(1 + resolved_link_count) + distinct_resolved_types / 10`
- Computed under **fully-typed-only** (primary) and **fully+weakly-typed**
  (sensitivity) resolution-inclusion policies
- Adjusted = `distinct_resolved_types / infrastructure_proxy`, where the
  proxy is the count of distinct native relation types observed in the
  repository corpus.

All raw dimensions are min-max normalized to `[0, 1]` pooled across the
v0.2 corpus for cross-repository comparability.

**Composite (secondary, reported but not primary):**

- `overall_embeddedness_score = mean(relational_norm, agent_raw, object_fully_norm)`
- `article_autonomy_score = 1 − overall_embeddedness_score` (legacy inverse)

## Exclusion criteria

- Records flagged as deleted by the source repository are excluded.
- Records failing to parse are excluded and logged; per-repository
  parse-failure rate is reported.
- Records whose classified object type is not `article` are excluded from
  the cross-tier H2 test but **retained** for the within-repository
  object-type comparison.
- For H2 testing, records are restricted to `object_type == article` with
  classification confidence `medium` or `high`. A sensitivity analysis
  including `low` confidence is reported.

## Tests

**Primary test (cross-tier, exploratory at v0.2):**

- Kruskal–Wallis across a priori tiers on each scoring column (raw and
  adjusted), articles only. ε² effect size reported. **Exploratory only**
  at n = 4 repositories; explicit low-power caveat.
- Per-repository mean and 95% bootstrap CI (2,000 iterations) for each
  scoring column.

**Primary statistically defensible test (within-repository):**

- For each repository, Kruskal–Wallis across `article | dataset | software`
  object types on each scoring column. ε² effect size reported.
- Pairwise Mann–Whitney U with rank-biserial effect size (article vs
  dataset, article vs software).

**Sensitivity analyses:**

- Primary resolution-inclusion policy: `fully_typed` only. Secondary:
  `fully_and_weakly_typed`. Object-dimension analyses are reported under
  both.
- Confidence threshold: primary medium+high, sensitivity includes low.

## Outputs

- Machine-readable: `output/analysis/results.json`
- Human-readable: `output/analysis/results.md`
- Capability profile: `output/repository_profile.json`
- Classification validation: `output/classification_validation.json`
- Resolution report: `output/resolution_report.json`
- Methods-ready summary: `output/report.md`

## Handling of deviations

Any change to the analysis plan after this document is committed is recorded
in `CHANGELOG.md` with a justification and in the paper's methods section.
If a scoring error is discovered post-hoc, v0.2 is re-run with the
corrected formula, the Zenodo deposit is updated, and the paper reports both
versions.
