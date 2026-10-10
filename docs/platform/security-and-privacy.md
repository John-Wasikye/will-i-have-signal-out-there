# Platform security and privacy

| Field | Value |
|---|---|
| Status | Draft for review. Shared by all five projects |
| Owner | John |
| Last updated | Oct 9, 2026 |
| Related | [platform-requirements.md](platform-requirements.md) (sections 2, 3 and 9), [operations.md](operations.md), each project's own security document |

This document covers the controls that every project relies on: keys, roles, environment separation, the Terraform state, the repository, and the platform's threats. Project-specific privacy (for example, the hiker reports in Project 1) is in each project's own security and privacy document.

---

## 1. Principles

1. **Every key is in one place.** AWS Systems Manager Parameter Store, as encrypted SecureStrings. No key is stored in code, in the repository, in GitHub, or on the session box.
2. **No stored AWS keys in CI.** GitHub Actions reaches AWS through OIDC, with a role trust policy that names this repository.
3. **Least privilege.** One role per pipeline. Read-only roles for agents. Dev roles cannot write live data.
4. **Dev and live are separate.** Separate buckets, Glue databases, DynamoDB tables and roles. Only merges to `main` reach live, and only after the changed pipelines pass in CI.
5. **Source text is data, never instructions.** Names and text from public sources cannot change what the platform does.
6. **Nothing can run up a bill.** Every paid item has a hard limit (operations, section 3).

## 2. Keys and secrets

| Secret | Used by | Stored as |
|---|---|---|
| AWS credentials for CI | None: CI uses OIDC | No stored key |
| Airflow connection keys | Airflow, through its secrets backend | Parameter Store SecureString |
| Project API keys (model API, Snowflake, Databricks, and others) | The project's pipelines and functions | Parameter Store SecureString |
| Signing and keyed-hash secrets (for example, the visitor-ID keyed hash in Project 1) | The project's functions | Parameter Store SecureString |
| Terraform state encryption | Terraform, through its KMS key | Customer-managed KMS key; no value stored |

Rules:

- Every read of a key is logged in CloudTrail.
- Keys are rotated when a project asks for it, and when a key is exposed (operations, PRB-5).
- Gitleaks runs on every push. Trivy scans the images.

## 3. Roles

| Who | Can read | Can write | Notes |
|---|---|---|---|
| John | Dev and live, through the console and Terraform | Terraform applies after approval; Parameter Store | Account access uses MFA (to be confirmed before the first deploy) |
| CI (GitHub Actions, OIDC) | Terraform state; sample files | Plan on pull requests; apply after approval; dev deploys | No stored key |
| Each pipeline role | Its own raw source and tables in its environment | Its own raw source and tables in its environment | One role per pipeline |
| Serving functions (Lambda) | The published data prefix only | Nothing | Always-on storage only (engineering standard 16) |
| Session box | Parameter Store (its secrets backend) | Its own pipelines' outputs in its environment | Starts and stops from Terraform |
| Agents (from the second round) | Allowlisted, read-only tools | Nothing | Write actions need human approval (standard 13) |

Exact policies are written in Terraform. This table is the requirement they must meet.

## 4. Environments and the Terraform state

- **Dev and live** share no bucket, database, table or role. A dev role's refusal to write live is a test (operations, PRB-6).
- **Terraform state** lives in its own S3 bucket. The bucket is versioned, encrypted with a customer-managed KMS key, has public access blocked, and is readable only by the Terraform role. It uses S3 locking. The state file never lives in the repository.
- **Public repository.** The repository is public, which the cost model relies on for free CI. No secrets are in it. Gitleaks and review check every change.

## 5. Threats

Each threat has a control, a way the control is checked, and what risk remains.

| # | Threat | Control | How it is checked | Remaining risk |
|---|---|---|---|---|
| S1 | A key is pasted into the repository or a log | Parameter Store only; gitleaks on each push; log redaction | CI scan; test of a planted fake key | Low. A key can still leak before the scan runs; rotation limits the damage |
| S2 | A dev change writes to live data | Separate resources and roles; live deploys only from `main` after tests | Role refusal test (PRB-6) | Low |
| S3 | A public bucket or endpoint exposes data | Public access blocked on every bucket except the public site; the site serves static files only | Terraform check that public access is blocked | Low |
| S4 | The Terraform state leaks secrets or the infrastructure map | Dedicated, encrypted, private bucket; role-only access | Bucket policy review | Low |
| S5 | A compromised container or library reaches production | Trivy scans; image manifests checked before first use; the Marquez image is pinned to one version and rebuilt only on purpose | Scan results in CI | Medium. Dependencies change often |
| S6 | Someone else gets into John's AWS account | Least privilege; budget action; session limit; idle shutdown | Account review; MFA check | Not assessed until MFA is confirmed |
| S7 | A paid service runs up a bill | Hard limits per item (operations, section 3); budget with an action; provider spend limits | Monthly cost review | Low to medium, bounded by the limits |
| S8 | Untrusted text from a source changes behavior | Source text is data; allowlisted tools; structured output | Project red-team tests | Medium for any project that uses a model |
| S9 | The session box is compromised and reads keys | The box holds no stored keys; keys are read by role at run time, and the role expires with the box | Review of the box's role | Low to medium while the box runs |

## 6. Privacy at platform level

- **Timestamps** are stored in UTC and converted only on the page (engineering standard 15).
- **Logs** are kept for the periods in operations, section 5. Security logs are kept one year.
- **Personal data** is handled by each project, under its own security and privacy document. The platform only provides the storage, the retention rules and the role separation those documents rely on.

## 7. Open items

| Item | Next step |
|---|---|
| MFA on John's AWS accounts | Confirm before the first deploy |
| Region for dev and live | Set to us-east-1 (Project 1, ADR 0034); the platform uses the same region |
| Alert address for email | Set in Terraform; not a secret |
