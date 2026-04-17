# Data availability — v0.2

## Source data

All v0.2 data are harvested from publicly accessible open access
repositories via their documented OAI-PMH or REST APIs. Repositories,
endpoints, and sampling parameters are recorded in
`config/sample_v0_2.yaml`.

No authentication is required for any source used at v0.2.

## Derived data

The full v0.2 corpus — raw native metadata, normalized records,
relations table, scores, capability profile, and analysis outputs — is
archived on Zenodo at paper submission with a persistent DOI. The
corresponding code revision is tagged in this repository and the tag is
referenced from the Zenodo record.

### Committed sample

A minimal sample of the output artifacts is committed to this repository
under `output/sample/` so the pipeline can be inspected without
re-harvesting. The full corpus is deposited on Zenodo.

### Formats

- Normalized records: Apache Parquet (schema: see `src/repository_object_mapper/schema.py`)
- Relations: Apache Parquet
- Capability profile: JSON
- Analysis results: JSON + Markdown
- Raw native metadata: XML or JSON, one file per record, organized by repository

## Reproducibility

- Code: this repository, tagged at submission.
- Configuration: `config/sample_v0_2.yaml`, `config/type_mapping.yaml`.
- Seeds: `random_seed = 42` in all sampling steps.
- Dependencies: pinned in `requirements.txt` / `pyproject.toml`.
- Single-command reproduction: `make demo` (on mock data) or
  `rom harvest --config config/sample_v0_2.yaml && rom classify && rom resolve && rom score && rom analyze` (on live data).

## Ethics and etiquette

- All live requests identify the client via a `User-Agent` header
  containing a contact email (`config.contact_email`).
- Rate limits are respected per repository via `request_rate_per_second`.
- Crossref and DataCite API etiquette (contact email, exponential
  backoff, failure logging) is enforced in `resolve.py`.
- No personal data beyond that published by the repositories themselves is
  retained. Creator names and ORCIDs are handled only in their
  repository-published form.
