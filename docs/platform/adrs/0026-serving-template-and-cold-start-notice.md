# 0026. One serving template: a React and TypeScript site, FastAPI on Lambda behind API Gateway, and the cold-start notice

- Status: Accepted. Decided by the build plan (BP step 0.4) and John's acceptance, Oct 9, 2026. The cold-start wording is the build plan's exact text.
- Date: Oct 9, 2026.

## Context

Every project serves a site and an API from published tables. One template is reused by all of them (BP, "Apps and APIs").

## Decision

1. Publish writes gold tables as Parquet. Lambda runs DuckDB over them behind API Gateway, with FastAPI.
2. A React and TypeScript site template has a map component, a lookup form, an answer card and a status page, with a preview deploy for every pull request.
3. The page shows the cold-start notice, in the plan's wording: "The first request after a period of inactivity may take up to 10 seconds while the service initializes."
4. Cold-start time and warm latency are measured in step 1B.9 and published in each README (BPD, "Cold starts").

## Alternatives considered

- A server that stays on: rejected for cost (BP, "Always-on parts").
- Per-project templates: rejected. One template, reused.

## Consequences

- Project 2 uses the template's adapter unchanged.
- Links: [openapi.yaml](../openapi.yaml); [ADR-0004](0004-duckdb-for-serving-trino-removed.md); [ADR-0022](../decisions.md).
