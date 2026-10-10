# 0011. Anything that runs 24/7 writes only to always-on storage; the nightly run picks the data up

- Status: Accepted. Decided by the build plan (BP rule 16) and John's acceptance of the build plan, Oct 9, 2026.
- Date: Oct 9, 2026.

## Context

The session box is off most of the time, so Kafka, Grafana and Superset exist only while it is on (BP rule 16). Lambda and Fargate run at any hour, so they must not depend on the box.

## Decision

Lambda and Fargate write only to S3, DynamoDB, CloudWatch or X-Ray. The nightly run on the session box reads those stores and processes the data. Always-on storage is the only place a request-time write can go.

## Alternatives considered

- Lambda writes to the box's database: rejected. The box is off.
- Always-on server for writes: rejected. It would break the budget (ADR-0013).

## Consequences

- Visitor writes land in DynamoDB (ADR-0006) and are copied to the lake by the nightly run.
- Realtime status and traces use CloudWatch and X-Ray (ADR-0015).
- Links: [ADR-0006](0006-dynamodb-for-visitor-data.md); [ADR-0012](0012-nightly-run-spot-with-two-hour-maximum.md).
