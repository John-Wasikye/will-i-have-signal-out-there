# 0033. The session box runs on demand, not on spot

- Status: Accepted. Decided by John, Nov 13, 2026. It replaces point 3 of [ADR-0012](0012-nightly-run-spot-with-two-hour-maximum.md) ("Spot only"); the rest of ADR-0012 stands.
- Date: Nov 13, 2026.

## Context

ADR-0012 put the nightly run on spot capacity only, because spot is cheaper. From Nov 10, 2026, spot failed the live box on most nights:

| Night | Start | Spot stop notice |
|---|---|---|
| Nov 10 | 3 failed tries (no capacity) | About 2 minutes after boot; nothing published |
| Nov 11 | 2 failed tries | During the dbt step; nothing published until I reran it by hand |
| Nov 12 | 3 failed tries | None; published at 10:12 UTC |
| Nov 13 | First try | At 10:07 UTC, just after the publish |

Nov 2 was skipped outright (8 failed tries) and Nov 4 started late.

AWS rates spot capacity from 1 (scarce) to 10. On Nov 13, 2026, `t4g.2xlarge` scored 1 in every us-east-1 zone, and `m7g.2xlarge` scored 3. A mix of four 32 GB Arm sizes scored 9.

The run is short. A nightly run took about 8 to 12 minutes in November 2026, and the box ran about 13 hours in the 30 days to Nov 13, 2026, work sessions included.

## Decision

1. The session box (dev and live) runs on demand. Terraform no longer sets spot market options on it, and a postcondition fails the plan if the box is ever a spot instance.
2. Size, schedule, 2-hour nightly maximum, 4-hour session limit, idle stop and the $40 budget are unchanged.
3. The watchdog keeps its spot notice check. On an on-demand box AWS sends no notice, so the check never fires; it needs no Deploy to keep.

## Alternatives considered

- Keep spot and change the size to `m7g.2xlarge`: one variable, no new server. Rejected: a capacity score of 3 still loses nights, at about twice the spot price of `t4g.2xlarge`.
- Keep spot on a mix of sizes across zones (a fleet with a launch template, the box built fresh each night): score 9 and spot prices. Rejected for now: the largest change (Terraform, install script, watchdog), and AWS can still take the box back mid-run. Worth another look if runs grow long or the box grows.
- Move the start time: rejected, no evidence another hour has more capacity.

## Consequences

- No more spot stops or capacity failures at the start. A start can still fail if AWS has no on-demand capacity, which is rare; the start schedule still retries for 2 hours.
- Cost: `t4g.2xlarge` is $0.2688 an hour on demand against about $0.10 on spot (us-east-1, Nov 13, 2026). At the measured 13 hours a month that is about $3.50 instead of about $1.40. At the planned 70 hours of work sessions, 30 hours of heavy batch and 22 nightly hours, the AWS total is about $40 (operations, section 3), the size of the $40 backup budget, and the all-in month about $48 to $51 against the $50 plan. The measured hours are far below that plan, so the cost to watch is the monthly box hours.
- AWS cannot turn a spot instance into an on-demand one, and leaving the spot block out does not replace an existing box (the first plans said "No changes"). So the Terraform resource is renamed from `box` to `box_on_demand`: the apply removes the old spot box and creates an on-demand one. The new box gets a new instance ID and a fresh root disk, so it needs the install script once. The persistent spot request of the old box must be cancelled, or AWS could launch a new spot box from it.
- Runbook PRB-3 (spot stop) no longer applies to the session box. PRB-1 now points at on-demand capacity.
- Links: [ADR-0012](0012-nightly-run-spot-with-two-hour-maximum.md); [ADR-0013](0013-cost-guards-and-spend-limits.md); [operations](../operations.md).
