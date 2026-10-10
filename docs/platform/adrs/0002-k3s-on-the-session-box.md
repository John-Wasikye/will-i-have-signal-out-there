# 0002. Run the session box on k3s, not Docker Compose

- Status: Accepted. Decided by John, Oct 9, 2026 (BPD, "Kubernetes"; BP step 0.3).
- Date: Oct 9, 2026.

## Context

The session box is the temporary AWS server that runs the nightly pipelines (Airflow, Spark, Kafka, Superset, PostgreSQL for Airflow, Grafana). It starts and stops every night. Something has to run the services on it.

## Decision

Use k3s, a lightweight Kubernetes, on the session box. John's reason: hands-on Kubernetes experience, which production data platforms commonly use. Docker experience already exists. k3s also gives each pipeline memory and CPU limits, restarts failed services, and carries over unchanged to the one-day EKS deploy in the second round (step 0.7).

## Alternatives considered

- Docker Compose: rejected by John. It is simpler, but gives less of the Kubernetes practice he wants, and it would need redoing for the EKS deploy.
- Full Kubernetes (EKS) every night: rejected for cost and time. EKS is planned as a one-day deploy only (step 0.7).

## Consequences

- About one extra day of setup (BP step 0.3). Accepted as the trade-off.
- The box must fit 32 GB of memory with the full stack. That is an open question (design doc OQ-P04).
- Links: [ADR-0012](0012-nightly-run-spot-with-two-hour-maximum.md); [design doc](../design-doc.md) sections 6 and 11.
