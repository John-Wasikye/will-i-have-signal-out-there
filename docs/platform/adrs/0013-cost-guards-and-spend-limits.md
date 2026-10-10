# 0013. Cost guards: a session limit, idle shutdown, a $40 backup budget, a 3-credit Snowflake cap and a $10 model limit

- Status: Accepted. Decided by John, Oct 9, 2026 (BPD, "Cost guards", "Snowflake" and "AI spending"; BP "Hard limits on everything that costs money").
- Date: Oct 9, 2026.

## Context

The whole plan stays under $50 a month and John works from a browser only (BPD, "Budget"). "Nothing in the project should surprise with cost" (BPD, "Surprise costs").

## Decision

1. Session limit: 4 hours per box session. Idle shutdown by CloudWatch alarm. These are the main guards (BPD, "Cost guards").
2. AWS Budget at $40, as a backup. It denies new launches and stops the box. AWS budget alerts lag by hours, so it is not the main guard (BP, "How the box is run").
3. Snowflake resource monitor suspends the warehouse at 3 credits a month, with a time limit on every query.
4. Model API: $10 monthly spend limit (Project 1, ADR 0038; the build plan's $15 is superseded) set in the API account before the first call, the cheapest model only, and a daily question cap (ADR-0014).
5. Every paid item has a hard limit. Spark jobs have row and runtime limits (ADR-0027).

## Alternatives considered

- Budget alerts as the main guard: rejected for the lag above.
- No model limit: rejected. The model is the largest single line item.

## Consequences

- The cost model is in the operating model table of the build plan. Measured costs are published in the README and operations document (BP rule 14).
- Limits are checked before each project's first paid call.
- Links: [ADR-0012](0012-nightly-run-spot-with-two-hour-maximum.md); [ADR-0014](0014-model-api-cheapest-model-batch-cached.md).
