# v0.2 analysis results

## Per-repository bootstrap CIs (articles only)

| Repository | tier | n | relational (raw) | agent (raw) | object fully (raw) | relational adj | agent adj | object adj fully |
|---|---|---|---|---|---|---|---|---|
| tier1_dspace_example | 1 | 15 | 0.185 [0.079, 0.316] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.400 [0.133, 0.667] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] |
| tier2_datacite_partial | 2 | 22 | 0.315 [0.220, 0.414] | 0.170 [0.102, 0.250] | 0.000 [0.000, 0.000] | 0.432 [0.295, 0.591] | 0.170 [0.102, 0.250] | 0.000 [0.000, 0.000] |
| tier4_inveniordm_example | 4 | 20 | 0.894 [0.850, 0.936] | 0.475 [0.388, 0.562] | 0.000 [0.000, 0.000] | 0.838 [0.775, 0.900] | 0.475 [0.388, 0.562] | 0.000 [0.000, 0.000] |
| zenodo | 3 | 30 | 0.485 [0.396, 0.568] | 0.358 [0.308, 0.408] | 0.000 [0.000, 0.000] | 0.444 [0.356, 0.533] | 0.478 [0.411, 0.544] | 0.000 [0.000, 0.000] |

## Cross-tier Kruskal–Wallis (exploratory, n=4 repositories)

- **relational_raw_norm**: H=54.717, p=0.0000, ε²=0.623, n=87
- **agent_raw**: H=47.374, p=0.0000, ε²=0.535, n=87
- **object_raw_fully_norm**: H=nan, p=nan, ε²=nan, n=87
- **object_raw_fully_weakly_norm**: H=26.036, p=0.0000, ε²=0.278, n=87
- **relational_adjusted**: H=25.348, p=0.0000, ε²=0.269, n=87
- **agent_adjusted**: H=50.822, p=0.0000, ε²=0.576, n=87
- **object_adjusted_fully**: H=nan, p=nan, ε²=nan, n=87
- **object_adjusted_fully_weakly**: H=23.132, p=0.0000, ε²=0.243, n=87
- **overall_embeddedness_score**: H=62.387, p=0.0000, ε²=0.716, n=87

> Caveat: with n=4 repositories, cross-tier results are exploratory only. See within-repository comparisons for statistically defensible tests.

## Within-repository object-type comparisons (primary test)

### relational_raw_norm

- **tier1_dspace_example**: skipped (fewer than 2 object-type groups)
- **tier2_datacite_partial**: skipped (fewer than 2 object-type groups)
- **tier4_inveniordm_example**: H=2.572, p=0.2763, ε²=0.021, n=30
  - article_vs_dataset: U=43, p=0.2549, rank-biserial=0.283, article-lower=True
  - article_vs_software: U=50, p=0.3832, rank-biserial=-0.262, article-lower=False
- **zenodo**: skipped (fewer than 2 object-type groups)

### agent_raw

- **tier1_dspace_example**: skipped (fewer than 2 object-type groups)
- **tier2_datacite_partial**: skipped (fewer than 2 object-type groups)
- **tier4_inveniordm_example**: H=0.797, p=0.6715, ε²=-0.045, n=30
  - article_vs_dataset: U=52, p=0.6161, rank-biserial=0.133, article-lower=True
  - article_vs_software: U=30, p=0.45, rank-biserial=0.238, article-lower=True
- **zenodo**: skipped (fewer than 2 object-type groups)

### object_raw_fully_norm

- **tier1_dspace_example**: skipped (fewer than 2 object-type groups)
- **tier2_datacite_partial**: skipped (fewer than 2 object-type groups)
- **tier4_inveniordm_example**: H=nan, p=nan, ε²=nan, n=30
  - article_vs_dataset: U=60, p=1, rank-biserial=0.000, article-lower=False
  - article_vs_software: U=40, p=1, rank-biserial=0.000, article-lower=False
- **zenodo**: skipped (fewer than 2 object-type groups)

### object_raw_fully_weakly_norm

- **tier1_dspace_example**: skipped (fewer than 2 object-type groups)
- **tier2_datacite_partial**: skipped (fewer than 2 object-type groups)
- **tier4_inveniordm_example**: H=nan, p=nan, ε²=nan, n=30
  - article_vs_dataset: U=60, p=1, rank-biserial=0.000, article-lower=False
  - article_vs_software: U=40, p=1, rank-biserial=0.000, article-lower=False
- **zenodo**: skipped (fewer than 2 object-type groups)

### relational_adjusted

- **tier1_dspace_example**: skipped (fewer than 2 object-type groups)
- **tier2_datacite_partial**: skipped (fewer than 2 object-type groups)
- **tier4_inveniordm_example**: H=2.572, p=0.2763, ε²=0.021, n=30
  - article_vs_dataset: U=43, p=0.2549, rank-biserial=0.283, article-lower=True
  - article_vs_software: U=50, p=0.3832, rank-biserial=-0.262, article-lower=False
- **zenodo**: skipped (fewer than 2 object-type groups)

### agent_adjusted

- **tier1_dspace_example**: skipped (fewer than 2 object-type groups)
- **tier2_datacite_partial**: skipped (fewer than 2 object-type groups)
- **tier4_inveniordm_example**: H=0.797, p=0.6715, ε²=-0.045, n=30
  - article_vs_dataset: U=52, p=0.6161, rank-biserial=0.133, article-lower=True
  - article_vs_software: U=30, p=0.45, rank-biserial=0.238, article-lower=True
- **zenodo**: skipped (fewer than 2 object-type groups)

### object_adjusted_fully

- **tier1_dspace_example**: skipped (fewer than 2 object-type groups)
- **tier2_datacite_partial**: skipped (fewer than 2 object-type groups)
- **tier4_inveniordm_example**: H=nan, p=nan, ε²=nan, n=30
  - article_vs_dataset: U=60, p=1, rank-biserial=0.000, article-lower=False
  - article_vs_software: U=40, p=1, rank-biserial=0.000, article-lower=False
- **zenodo**: skipped (fewer than 2 object-type groups)

### object_adjusted_fully_weakly

- **tier1_dspace_example**: skipped (fewer than 2 object-type groups)
- **tier2_datacite_partial**: skipped (fewer than 2 object-type groups)
- **tier4_inveniordm_example**: H=nan, p=nan, ε²=nan, n=30
  - article_vs_dataset: U=60, p=1, rank-biserial=0.000, article-lower=False
  - article_vs_software: U=40, p=1, rank-biserial=0.000, article-lower=False
- **zenodo**: skipped (fewer than 2 object-type groups)

### overall_embeddedness_score

- **tier1_dspace_example**: skipped (fewer than 2 object-type groups)
- **tier2_datacite_partial**: skipped (fewer than 2 object-type groups)
- **tier4_inveniordm_example**: H=1.607, p=0.4477, ε²=-0.015, n=30
  - article_vs_dataset: U=41, p=0.2434, rank-biserial=0.317, article-lower=True
  - article_vs_software: U=34, p=0.6565, rank-biserial=0.150, article-lower=True
- **zenodo**: skipped (fewer than 2 object-type groups)
