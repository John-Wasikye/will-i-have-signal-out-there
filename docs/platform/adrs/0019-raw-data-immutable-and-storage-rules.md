# 0019. Raw data is kept immutable; static archives are stored as manifests; live raw files are locked for 30 days; clean-up rules apply to temporary data

- Status: Accepted. Confirmed by John, Oct 9, 2026. This includes the 30-day lock period, which was a Default (BPD, "Raw-file lock" and "Storage clean-up"; BP rule 1).
- Date: Oct 9, 2026.

## Context

Any result must be replayable and auditable at low storage cost (BP rule 1). Accidental deletion must be guarded without trapping a bad file for months (BPD, "Defaults used").

## Decision

1. Raw files are kept immutable, with source URL, fetch time and hash (BP rule 1).
2. Public archives that never change (for example the GEBCO grid, Copernicus elevation, Ookla tiles and the Apollo audio) are stored as a manifest of URL, size and hash, not as full copies (BP rule 1).
3. Live raw files use governance-mode S3 Object Lock for 30 days. Dev files are not locked, so the 14-day clean-up works (BP, "Where each job runs"; 30 days is a Default).
4. Clean-up: dev data 14 days, temporary files 7 days, failed uploads 7 days, pipeline logs 90 days, security logs 1 year, old versions 30 days. Raw and published data are kept (BPD, "Storage clean-up").
5. Terraform state has its own bucket (ADR-0023).

## Alternatives considered

- Full copies of every archive: rejected. Storage cost, with no gain in replay.
- Locking dev data: rejected. It would stop the 14-day clean-up.

## Consequences

- Every bucket has an alarm if storage passes a set size (BP, "Hard limits").
- Lifecycle rules are Terraform code (ADR-0003).
- Links: [ADR-0009](0009-iceberg-tables-with-glue-catalog.md); [security and privacy](../security-and-privacy.md).
