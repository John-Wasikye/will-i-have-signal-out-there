# 0007. Every key is in AWS Parameter Store; GitHub stores none

- Status: Accepted. Decided by John, Oct 9, 2026 (BPD, "Key storage").
- Date: Oct 9, 2026.

## Context

Keys for APIs, the keyed-hash secret, and the Model API must be stored somewhere. Two key locations seemed strange to John; one place is simpler (BPD).

## Decision

1. All keys and passwords are in AWS Systems Manager Parameter Store as SecureString values.
2. GitHub Actions reads them through OIDC, a way to sign in to AWS without stored keys. GitHub holds no keys (BP step 0.1).
3. Pipelines, Lambda and Airflow read keys from Parameter Store. Airflow uses its built-in secrets backend, so its backup contains no key (ADR-0008).
4. Keys are never in code or in the repository. Gitleaks scans run in CI (BP step 0.1).

## Alternatives considered

- Keys in GitHub secrets: rejected. It creates a second key location.
- Keys in Airflow connections saved to S3: rejected. The backup would then hold keys.

## Consequences

- Every key read is logged (BP, "Free, encrypted, every read logged").
- Access uses one least-privilege role per pipeline (BP step 0.2).
- Links: [ADR-0008](0008-airflow-database-saved-to-s3.md); [security and privacy](../security-and-privacy.md).
