# 0034. Region us-east-1; report copies deleted after 30 days, with daily counts kept; model provider Anthropic

- Status: Accepted (John, Oct 9, 2026, answering open questions OQ-42, OQ-43 and the provider part of OQ-39)
- Date: Oct 9, 2026
- Source: John's answers to the four major questions; the set-aside and call-log retention lines are defaults chosen by Claude, marked below

## Context

Three decisions were needed before the platform and the assistant can be built: the AWS region, how long the lake and Snowflake keep individual hiker reports, and which model provider the trip assistant uses.

## Decision

1. **AWS region (OQ-42).** Dev and live run in `us-east-1` (N. Virginia). Every resource name in design doc section 9.1 applies in this region.
2. **Report copies (OQ-43).** Raw report rows are deleted 30 days after the nightly copy in every store: DynamoDB, the lake table `signal_report`, and Snowflake. The lake and Snowflake keep one row per H3 resolution 9 cell and UTC day (table `report_cell_day`: the count of reports, and the count showing signal). That is enough for the label rule in ADR 0008, so model labels survive after the raw rows are gone.
3. **Set-aside rows (default, Claude).** The rows in `signal_report_set_aside` are raw reports, so they follow the same 30-day rule.
4. **Model provider (OQ-39).** The trip assistant and the LLM judge use the Anthropic API, on the cheapest Claude model. The exact model ID is pinned when the code is written. The $10 monthly spend limit is set in that account before the first call (FR-42).
5. **Call log retention (default, Claude).** The `llm_calls` log is kept 90 days, the same as pipeline logs. It holds no question text (ADR 0033).

## Alternatives considered

- Region: `us-west-2` was the other option. John chose `us-east-1`.
- Report copies: 90 days or indefinitely. Rejected: they keep individual reports longer than the privacy promise needs.
- Model provider: another provider. Not chosen.

## Consequences

- The `report_cell_day` table needs its own data contract before Phase B. It is not written yet.
- Snowflake and the lake lose individual reports after 30 days. Any analysis that needs them must be done inside that window.
- The Anthropic terms must be recorded in the licence register before the first model call (security and privacy, section 6).
