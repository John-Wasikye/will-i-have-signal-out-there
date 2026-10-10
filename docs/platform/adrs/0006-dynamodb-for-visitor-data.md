# 0006. Visitor data is stored in DynamoDB, not PostgreSQL

- Status: Accepted. Decided by John, Oct 9, 2026 (BPD, "Visitor data").
- Date: Oct 9, 2026.

## Context

Visitor data includes signal reports, votes, email sign-ups, API key requests and a review queue. Visitors write at any hour, and the session box is off most of the time (BP, "Platform skeleton"). Anything that runs 24/7 writes only to always-on storage (BP rule 16, see ADR-0011).

## Decision

Store visitor data in DynamoDB. It is always on, it accepts writes while the box is off, and the free tier covers this traffic. Point-in-time recovery is on, so a bad write or deletion can be undone (BPD, "DynamoDB"). The one exception: Project 1's hiker reports table has point-in-time recovery off, so that deletion at 30 days is final (Project 1, ADR 0022).

## Alternatives considered

- PostgreSQL on the session box: rejected. The box is off most of the time, so writes would fail (BP, "Visitor data" row).
- pgvector: removed (ADR-0016).

## Consequences

- Heavy traffic is throttled rather than billed, because tables are provisioned within the free tier (BP "Hard limits").
- Nightly copies go to the lake and Snowflake with personal data replaced by a keyed-hash code (BP "Visitor data" row; Project 1, ADR 0012).
- Links: [ADR-0011](0011-always-on-writes-only-to-always-on-storage.md); [security and privacy](../security-and-privacy.md).
