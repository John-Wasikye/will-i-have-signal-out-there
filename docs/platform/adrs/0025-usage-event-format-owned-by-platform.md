# 0025. The platform owns the usage-event format and collection point; each project adds its site as it ships

- Status: Accepted for ownership (Decided by John, Oct 9, 2026, John's answer 17, recorded in the archived shared log). The field-level format is accepted as drafted in contracts/usage_events.yaml. Session: 30 minutes without an event. Events are deleted after 90 days. These are defaults John may change before any site sends events.
- Date: Oct 9, 2026.

## Context

Usage analytics span all five sites (Project 2, FR-33). One place must define the event format and where events are collected, so every site sends the same shape and no raw IP address reaches the warehouse.

## Decision

1. The platform defines the event format and the collection endpoint, in contracts/usage_events.yaml.
2. Usage events carry no raw IP address and no cookie. Visitors are identified by a random ID kept on the phone or in the browser (Project 1's rule, BPD "Visitor identity").
3. Project 2 builds the Snowflake tables and reports and adds each site as it ships (John's answer 17).

## Alternatives considered

- Each project defines its own events: rejected by John (John's answer 17).
- Collecting IP addresses for unique-user counts: excluded by the requirement.

## Consequences

- The field list in contracts/usage_events.yaml is accepted as a default; John may change it before any site sends events.
- Links: [contracts/usage_events.yaml](../contracts/usage_events.yaml).
