# 0012. Store reports in DynamoDB, delete raw rows 30 days after the nightly copy, set aside impossible patterns

- Status: Accepted (John, Build Plan Decisions, Oct 9, 2026); recovery amended Oct 9, 2026 (Decided by John, Oct 9, 2026)
- Date: Oct 9, 2026
- Source: Build Plan Decisions "Visitor data", "DynamoDB", "Email addresses"; build plan 1B.8 and "Personal data"; engineering standard 16 (round-the-clock Lambda writes only to always-on storage)

## Context

Reports arrive at any hour while the session box is off. Personal data should stay in one place and not accumulate.

## Decision

- A Lambda function (AWS code that runs on demand) writes each report to DynamoDB, which is always on and free at this traffic (reason recorded: earlier options did not handle visitors writing at any hour). Point-in-time recovery is OFF for the hiker reports table (amended, ADR 0022), so deletion is final at 30 days. Other tables keep it on.
- The nightly run copies reports into the data lake (S3 storage with Iceberg tables) and into Snowflake. Raw report rows delete themselves 30 days after that copy.
- The copy sets aside impossible patterns (reports outside any mapped area, bursts that contradict nearby reports) for review.
- Report counts per area are shown on the page.

## Alternatives considered

- PostgreSQL on the box (off most of the time): not usable for writes at any hour.
- No other alternatives are recorded for this project.

## Consequences

- Lambda functions write only to always-on storage (engineering standard 16).
- The expiry is set by the nightly copy, so a failed copy never loses a row before it is copied.
- A bad write to the reports table cannot be undone; the copy in the data lake is the only other copy (ADR 0022).
- Definition of "area" for the counts: OQ-35.
- Where set-aside reports are stored is a design proposal (table `signal_report_set_aside`, OQ-21).
- The 30-day rule applies to the DynamoDB rows only. The lake and Snowflake copies (and the set-aside rows) follow the same 30-day rule, and the lake and Snowflake keep daily per-cell counts (OQ-43, ADR 0034).
