# 0010. Save reports on the phone and send them when signal returns

- Status: Accepted (John, Build Plan Decisions, Oct 9, 2026)
- Date: Oct 9, 2026
- Source: Build Plan Decisions "Offline reports"; build plan 1B.8

## Context

The hikers with no signal are the ones who need to report it.

## Decision

A report is saved on the phone and sent automatically when signal returns: in the background on Android; on iPhone, Safari sends it the next time the page is opened, with a "1 report waiting to send" note.

## Alternatives considered

- Requiring signal at the moment of the report: rejected, since those hikers are the ones who need to report.
- No other alternatives are recorded.

## Consequences

- The phone keeps each report in a local queue (storage that survives closing the page) until a send succeeds.
- On iPhone, reports can wait until the page is opened again.
- A burst of queued reports arriving at once is judged by the hour each report was made (ADR 0011); remaining details are in OQ-26.
- Verified by the airplane-mode test in AC-1B.8.
