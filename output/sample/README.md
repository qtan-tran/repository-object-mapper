# Committed sample output

This directory contains a committed subset of pipeline outputs produced
from the mock-data run (`make demo`). It exists so reviewers and readers
can inspect the shape of the pipeline's artifacts without having to run
the full harvest themselves.

- `repository_profile.json` — per-repository capability profile (available
  vs used affordances, resolved-object-type distribution, empirical tier
  indicator).
- `repository_summary.csv` — per-repository descriptive statistics.
- `sampling_frame.json` — the v0.2 sampling frame as loaded from
  `config/sample_v0_2.yaml`.
- `classification_disagreement.json` — declared-vs-rule disagreement rate
  per repository (a data-quality indicator).
- `resolution_report.json` — per-repository breakdown of resolution tiers.
- `tier_discrepancies.json` — a priori vs empirical tier comparison.
- `analysis/` — machine-readable and human-readable analysis outputs.

These files are from the **mock-data** run and are illustrative only.
The full v0.2 corpus is deposited on Zenodo at paper submission; see
`DATA_AVAILABILITY.md`.
