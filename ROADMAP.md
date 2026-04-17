# Roadmap

Expansion plan from v0.2 to v0.5 and v1.0. The adapter framework, normalized
schema, scoring formulas, and resolution cache are designed to scale without
rewrite: new repositories are added via configuration and adapters, not by
editing the pipeline.

## Decision point after v0.2

After v0.2 is implemented, executed, and the paper draft stabilizes,
decide explicitly: **submit v0.2 to JDoc as an exploratory study, or
expand to v0.5 before first submission?** The answer depends on v0.2
results:

- If v0.2 shows clear, theoretically interesting patterns — especially if
  the available-vs-used decomposition reveals substantive differences
  between schema capacity and documentary practice — **submit the
  exploratory version**. Reviewers often prefer a clearly scoped
  exploratory paper to an overextended one.
- If results are ambiguous, or if within-repository comparisons dominate
  the cross-repository story to the point that cross-tier claims cannot be
  supported, **expand to v0.5 first**.

## Phase 1 — widen sampling (1–2 weeks)

Commit `config/sample_v0_5.yaml` implementing the full stratified design:

- 20 repositories, 4 per stratum cell across repository type
  (institutional / disciplinary / national / funder-mandated / generalist)
  and schema tier (1–4).
- Target ≈ 2,000 article records per repository, ≈ 40,000 total.
- Include the four v0.2 repositories as anchors for cross-version
  consistency checking. Discrepancies between v0.2 and v0.5 harvests of
  the same repository indicate pipeline drift, repository change, or
  harvest-window effects and **must be investigated**.
- Preserve `sample_v0_2.yaml` for reproducibility of the v0.2 results.

## Phase 2 — remaining adapters (2–3 weeks)

Dedicated adapters for:

- Figshare REST
- DSpace 7+ REST
- Standalone InvenioRDM REST
- Dataverse REST

Each inherits `AdapterBase` established in v0.2, each with
adapter-specific mock-based tests. Prioritize by sample coverage — the
adapter unlocking the most v0.5 repositories comes first. Budget
conservatively; adapter engineering dominates the v0.5 timeline.

## Phase 3 — strengthen inference (1 week)

With n = 20 repositories, upgrade the analysis module to a
**mixed-effects regression** of record-level embeddedness on
repository-level schema tier, with repository as a random effect,
controlling for:

- repository size
- repository age
- disciplinary focus (encoded from a simple taxonomy)

Run separately on raw and available-adjusted scores. Report fixed-effect
estimates with 95% CIs. Sensitivity analyses:

- exclude the most and least connected repositories
- vary the resolution-inclusion policy
- exclude low-confidence classifications

Rewrite the paper's analysis section with v0.5 as primary; demote v0.2 to
a pilot described briefly in methods.

## Phase 4 — validation and robustness (1 week)

- Scale manual classification validation to **1,000 records** (50 per
  repository).
- **Inter-rater reliability**: second coder independently labels a
  200-record subset; report **Cohen's κ**.
- **Resolution accuracy check**: manual cross-check on 500 resolved
  identifiers, verifying assigned type against source record. Report
  resolution accuracy per tier.
- Full validation statistics in the final paper.

## Phase 5 — infrastructure scaling (variable)

Add only as needed:

- Parallel harvesting via async `httpx` with per-repository concurrency
  limits.
- Parquet partitioning by repository for analysis efficiency.
- Persistent resolution cache shared across runs (already established
  in v0.2 — simply persist it).

**Do not add infrastructure preemptively.** Work-queue systems (`rq`,
`celery`) are deferred unless resume semantics become unmanageable.

## Phase 6 — paper revision (1–2 weeks)

Rewrite empirical sections with v0.5 results. Add robustness checks.
Revise abstract, discussion, limitations. Final Zenodo deposit with DOI.
Tag v1.0 on revised manuscript submission.

## Schema discipline between versions

The normalized schema, three embeddedness dimensions, scoring formulas,
type classification logic, available-vs-used distinction, and
pre-analysis plan **remain stable v0.2 → v0.5**. Any change must be
documented in `CHANGELOG.md` with justification; if v0.2 analysis reveals
a scoring error, document it, re-run v0.2 with the corrected formula,
re-deposit, and proceed to v0.5 with the corrected form. Never silently
change scoring between versions.
