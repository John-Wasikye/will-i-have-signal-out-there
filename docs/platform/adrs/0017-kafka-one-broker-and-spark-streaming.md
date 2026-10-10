# 0017. Kafka with one broker for event transport; Spark Structured Streaming for streams; Flink is removed

- Status: Accepted. Decided by the build plan (BP, "One tool per job": "Event transport" and "Batch processing and streaming"), and John's acceptance of that table, Oct 9, 2026.
- Date: Oct 9, 2026.

## Context

Live sources must be decoupled from processing and replayable (BP, "Event transport"). Flink would duplicate Spark's streaming job (BP, "One tool per job").

## Decision

1. Kafka runs with one broker on the session box. It runs only while the box is on (BP rule 16). Captures are written straight to S3 first, so a replay still works after the server is gone (BPD, "Ship captures").
2. Spark (Structured Streaming) processes streams. Flink is removed.

## Alternatives considered

- Flink: removed as a duplicate of Spark.
- Managed streaming services: not chosen. They bill while idle.

## Consequences

- Live streams run only in sessions and during the nightly replay of off-hours captures (Project 3's live stream, BPD).
- Links: [ADR-0011](0011-always-on-writes-only-to-always-on-storage.md).
