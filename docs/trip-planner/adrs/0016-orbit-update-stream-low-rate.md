# 0016. Publish orbit updates through Kafka and process them with an availableNow Structured Streaming job

- Status: Accepted (build plan 1B.2)
- Date: Oct 9, 2026
- Source: Build plan 1B.2; "When each tool is introduced"; engineering standards 3 (idempotent tasks) and 16 (round-the-clock Lambda writes only to always-on storage)

## Context

Kafka (a message queue) runs only while the session box (the rented AWS server) is on. Project 1 introduces Kafka and Structured Streaming in Phase B at a low rate; Project 3 later uses them for a live stream.

## Decision

The nightly run publishes each new element set to Kafka. A Structured Streaming job, run with Spark's availableNow trigger (process everything new since the last run, then stop), finds changed satellites and triggers re-propagation, with an explicit schema, checkpoints on S3, a watermark and dropDuplicatesWithinWatermark. The design note says plainly that this stream is low-rate.

## Alternatives considered

- Flink: removed as a duplicate of Spark Structured Streaming.
- No other alternatives are recorded.

## Consequences

- Replaying a day of updates must write the same rows (AC-1B.2).
- Checkpoints are temporary files removed after 7 days by the clean-up rules.
- Watermark value, topic and the definition of "changed" are decided in ADR 0028 (OQ-30).
