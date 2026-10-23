# 0017. The trip-planning assistant answers through defined metric tools first, with logged raw SQL as a fallback

- Status: Accepted (John, Build Plan Decisions, Oct 9, 2026)
- Date: Oct 9, 2026
- Source: Build Plan Decisions "Agent queries", "Tracing", "Model", "AI spending", "AI placement"; build plan 1B.5 to 1B.7; engineering standard 13 (least privilege for agents)

## Context

The assistant answers plain-language trip questions with a check-in plan. Wrong numbers are the main failure; agents that touch real systems are the main safety risk.

## Decision

- An MCP server (Model Context Protocol, a standard tool interface for AI models) exposes the metrics as tools; raw SQL is a read-only, allowlisted fallback that is logged separately (reason recorded: fewer wrong numbers).
- Every model call is logged to S3 (model, prompt version, tokens, latency, cost) and every agent run is traced into AWS X-Ray, which is always on because agents run on Lambda at any hour.
- Prompts are versioned in git; every call uses structured output; only the cheapest model is used for now, behind a $10 monthly spend limit, a daily question cap and a token limit per answer (reason recorded: keeps cost low until the evals justify more). A stronger model is compared in Phase C.
- Amendment (Decided by John, Oct 9, 2026): the assistant answers only within the prediction span and says so for later days (ADR 0021).
- The assistant cites the trail points and times it used and says so when the data cannot answer.
- The harness fails an answer that states a number that is not in the query result.
- Source text is treated as data, never as instructions; the assistant has no write tool.

## Alternatives considered

- Raw SQL first: not chosen; it risks more wrong numbers.
- A cross-project orchestrator: cut, because it was AI for show (platform-level cut; recorded for completeness).

## Consequences

- Eval thresholds, the daily cap and the token limit are open (OQ-16, OQ-17).
- The assistant is limited to the prediction span (ADR 0021).
- Model and provider: the Anthropic API, cheapest Claude model (ADR 0034; OQ-39).
