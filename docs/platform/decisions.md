# Platform: Decision log

Platform decisions that apply to all five projects. Significant decisions stay as ADRs in `adrs\`; minor ones are in the table below.

## Minor decisions (folded from ADRs)

These decisions were first written as separate ADRs. They are minor (a setting, a wording rule, a format or a repeat of a platform rule), so they were folded into this table on Oct 9, 2026. The old ADR numbers are kept so existing references still resolve. The full detail of each is in the design doc, section 14.

| Old ADR | Decision | Status |
|---|---|---|
| ADR-0003 | Use Terraform, not OpenTofu | Accepted |
| ADR-0015 | Agent traces go to AWS X-Ray; every model call is logged to S3 | Accepted |
| ADR-0016 | Vector search uses LanceDB files in S3; pgvector is removed | Accepted |
| ADR-0021 | Every timestamp is stored in UTC and converted to local time only on the page | Accepted |
| ADR-0022 | Public pages use the API Gateway HTTP type; routes that need API keys and per-key limits use the REST type | Accepted |
| ADR-0023 | Terraform state is in its own S3 bucket: versioned, encrypted with a customer-managed KMS key, public access blocked, readable only by the Terraform role, with S3 locking | Accepted |
| ADR-0029 | Each source has an H3 resolution chosen from its data; joins use cell_to_parent to the coarser resolution | Accepted |
| ADR-0031 | Container images run on ARM | Accepted |
| ADR-0032 | SHA-256 is the hash for every content hash | Accepted |
