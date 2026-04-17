# Manual validation labels

This directory holds the stratified manual validation set for object-type
classification.

- `labels.csv` — schema: `repository,local_id,expected_object_type,note`
- At v0.2, the target is **200 records (50 per repository)**. The committed
  sample in this file is a small demonstration subset; the full 200-record set
  is produced for real harvests by sampling from the normalized records
  parquet and labeling manually.

At v0.5 this is scaled to 1,000 records (50 per repository across 20
repositories), with a 200-record subset independently labeled by a second
coder for inter-rater reliability (Cohen's kappa).

## Reproducing the validation procedure

1. Run the pipeline through `rom classify`.
2. Stratify by repository; random-sample 50 articles from each.
3. Open the `raw_path` for each sampled record and label against the
   published closed vocabulary.
4. Write the resulting rows to `labels.csv`.
5. Run the validation scoring helper (see `tests/test_classify.py` for
   the comparison logic) to produce `output/classification_validation.json`.
