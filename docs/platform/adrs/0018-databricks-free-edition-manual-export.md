# 0018. ML training runs on Databricks Free Edition with MLflow; results are copied to GitHub by hand

- Status: Accepted. Decided by John, Oct 9, 2026 (Project 1 answer 3 and Project 3 answer 36, in those projects' decision logs; BPD "ML training"). The licence and outbound limits were checked on Oct 9, 2026.
- Date: Oct 9, 2026.

## Context

Free managed MLflow and a model registry are wanted without a self-hosted server (BP, "One tool per job"). Databricks Free Edition is for non-commercial use, is serverless only, has a daily quota, and restricts outbound internet to trusted domains (checked on Databricks' Free Edition pages, Oct 9, 2026).

## Decision

1. Training and experiment tracking use Databricks Free Edition with MLflow.
2. Data is pushed in through the Files API (BP, "Decided").
3. After each training run, results and the chosen model are copied to the GitHub repository by hand (Project 1 answer 3). An automation test is still an open question.
4. A monthly job keeps the free account active (BPD, "ML training").

## Alternatives considered

- Self-hosted MLflow: rejected. Another server to run.
- Automatic export from Databricks: not chosen for now. Outbound internet is restricted (Project 1, OQ-19, tests this).

## Consequences

- The site never depends on Databricks. Only the trained model file is served (BPD, "ML training").
- Free Edition is non-commercial. Any future commercial use needs a different platform and a new ADR.
- Links: [security and privacy](../security-and-privacy.md) (licence register).
