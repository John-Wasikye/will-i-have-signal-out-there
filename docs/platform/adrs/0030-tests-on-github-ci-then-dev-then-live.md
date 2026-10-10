# 0030. Tests run on GitHub's free CI machines with sample data, then dev, then live; no staged production failures

- Status: Accepted. Decided by John, Oct 9, 2026 (BPD, "Testing changes" and "Failure testing").
- Date: Oct 9, 2026.

## Context

Spark tests need machines. A test that runs the AWS server would cost money and time on every change (BPD, "Testing changes"). Staged failures in production were judged a waste of time at this stage (BPD, "Failure testing").

## Decision

1. Every change runs lint and tests on GitHub Actions (BP step 0.1).
2. Changed pipelines run with Spark on sample data on GitHub's free CI machines. The AWS server stays off (BP, "Automatic deploys, tested first").
3. Only if these pass does the change deploy to dev, then to live (ADR-0020).
4. No staged production failures. Real incidents are recorded (ADR-0024).
5. Each project's first-run checks run in dev before the phase is built.

## Alternatives considered

- Tests on the AWS server: rejected for cost.
- Chaos testing in production: rejected by John.

## Consequences

- GitHub's free CI machines are used for public repositories (BP, "Where each job runs").
- Links: [ADR-0020](0020-dev-and-live-separate-merges-gated.md).
