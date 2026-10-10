# 0014. The model API uses only the cheapest model for now, in batch and cached, with daily caps on live questions

- Status: Accepted. Decided by John, Oct 9, 2026 (BPD, "AI spending", "Model" and "AI placement"). The provider is the Anthropic API, decided for Project 1 (Project 1, ADR 0034).
- Date: Oct 9, 2026.

## Context

AI features exist in several projects. The largest cost is the model. John chose the cheapest model for now, with a stronger one compared only in Phase C once evals justify it (BPD, "Model").

## Decision

1. Only the cheapest model is used until evals justify another (Phase C comparison).
2. Generated content is made in batch and cached. Pages never call a model while a reader opens them.
3. Live questions have a daily cap and a token limit per answer.
4. A $10 monthly spend limit is set in the API account before the first call.
5. Every call is logged to the call log (`llm_calls`, contracts/llm_calls.yaml) in S3 (ADR-0015).

## Alternatives considered

- A stronger model from the start: rejected for cost. Evals first.
- Live calls on every page: rejected.

## Consequences

- Monthly model cost is about $5 to $10 (the cap in Project 1, ADR 0038) (BP, "Operating model"). It is checked against the call log each month.
- Links: [ADR-0013](0013-cost-guards-and-spend-limits.md); [ADR-0015](../decisions.md); [contracts/llm_calls.yaml](../contracts/llm_calls.yaml).
