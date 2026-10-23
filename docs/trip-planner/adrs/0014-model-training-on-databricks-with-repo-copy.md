# 0014. Train the confidence model in Databricks Free Edition and score with a copy kept in the repo

- Status: Accepted (John, Build Plan Decisions, Oct 9, 2026); export amended Oct 9, 2026 (Decided by John, Oct 9, 2026)
- Date: Oct 9, 2026
- Source: Build Plan Decisions "ML training"; build plan 1B.4 and "Decisions and open items" ("Databricks")

## Context

Databricks Free Edition gives free managed MLflow and a model registry, but it is serverless only, has a daily fair-use quota, limited outbound internet, and is non-commercial.

## Decision

- John uploads training data to Databricks through its Files API, and MLflow (a tool that tracks training runs) tracks every model version.
- After each training run the results and the chosen model are exported manually (downloaded from Databricks and committed to GitHub). Amended, Decided by John, Oct 9, 2026; this replaces the automatic copy step. An open question stays to test whether automation is possible (OQ-19).
- A small monthly job keeps the free account active.
- The pipeline always scores with the copy in the repo, so the site never depends on Databricks being up.

Reason recorded by John: it shows Databricks while the site never depends on it.

## Alternatives considered

- Self-hosted MLflow: removed as a duplicate of the free managed MLflow.
- No other alternatives are recorded.

## Consequences

- The upload is an untested assumption (OQ-3). Whether the export can be automated given limited outbound internet is open (OQ-19).
- The model artifact lives in git; its size is unknown until the model family is chosen (OQ-18).
- Databricks Free Edition is non-commercial.
