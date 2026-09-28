# Yash

I build applied AI systems around the parts that usually fail after the demo: tool execution, trust boundaries, replay, evals, observability, scheduling and operator workflows.

My work is mostly local-first and inspectable. I prefer deterministic cores, explicit failure modes and evidence you can verify over opaque orchestration.

**[yashkhou.com](https://yashkhou.com/)** · [Projects](https://yashkhou.com/projects) · [@yashkhou on X](https://x.com/yashkhou)

## Core systems

| Project | What it explores |
| --- | --- |
| [Commander Plus](https://github.com/yashkhou/commander-plus) | A local-first agent workstation: MCP tools, reusable skills, durable workspaces, browser/computer control and persistent project context. |
| [Glyph](https://github.com/yashkhou/glyph) | A semantic design system for AI-generated interfaces with constraints, stable IDs, diffs and deterministic rendering targets. |
| [Verify](https://github.com/yashkhou/verify) | Verification infrastructure for AI-written artifacts, code and reversible actions. |

## AI reliability lab

A set of focused, dependency-light tools for testing and hardening agent infrastructure. Each repository is built around a small deterministic core with tests, CI, examples and tagged releases.

| Project | Reliability boundary |
| --- | --- |
| [Context Firewall](https://github.com/yashkhou/context-firewall) | Provenance-aware trust boundaries and fail-closed checks before privileged actions. |
| [Tool Contract Fuzzer](https://github.com/yashkhou/tool-contract-fuzzer) | Deterministic valid/invalid JSON-Schema cases, boundary mutations and shrinking. |
| [MCP Chaos](https://github.com/yashkhou/mcp-chaos) | Deterministic JSON-RPC/MCP fault injection, method-scoped cadence and wire-level chaos testing. |
| [Agent Replay](https://github.com/yashkhou/agent-replay) | Redacted, hash-chained agent event logs with integrity-aware deterministic replay. |
| [Failure Corpus](https://github.com/yashkhou/failure-corpus) | Normalize, fingerprint and deduplicate failures into reusable regression corpora. |
| [Handoff Spec](https://github.com/yashkhou/handoff-spec) | Canonical, digestible handoffs with authority boundaries and continuation invariants. |
| [Toolgraph Profiler](https://github.com/yashkhou/toolgraph-profiler) | Critical paths, retries, fan-out, lock pressure and idle time in tool-call traces. |
| [Agent Policy Compiler](https://github.com/yashkhou/agent-policy-compiler) | Explainable policy-as-code for deterministic allow/deny decisions. |
| [Eval Capsule](https://github.com/yashkhou/eval-capsule) | Portable eval fixtures, assertions and integrity-checked reproducible archives. |
| [Schema Evolution Guard](https://github.com/yashkhou/schema-evolution-guard) | Detect compatibility-breaking changes in evolving tool and API schemas. |
| [Context Budgeter](https://github.com/yashkhou/context-budgeter) | Token allocation, duplicate detection and policy-collision analysis for prompt context. |
| [Agent Scheduler Sim](https://github.com/yashkhou/agent-scheduler-sim) | Deterministic worker/retry/starvation simulation for agent scheduling policies. |

## Product systems

- [OpenRetention](https://github.com/yashkhou/openretention) — self-hosted customer-success software with explainable health scoring, churn risk, renewals and revenue-at-risk prioritisation.
- [AI Real Estate CRM](https://github.com/yashkhou/ai-real-estate-crm) — evidence-aware CRM logic for property, owner and lead workflows with deterministic matching and voice-agent handoff.
- [AI Product Sourcing Agent](https://github.com/yashkhou/ai-product-sourcing-agent) — marketplace-agnostic sourcing engine for query planning, normalization, deduplication and evidence-based ranking.

## Recent upstream work

- Opened [Stellar-agentic #429](https://github.com/StellarAgent-AI-Agent-Payment-Rails/Stellar-agentic/pull/429) to repair repository-specific README links.
- Reviewed [pydantic-ai #8969](https://github.com/pydantic/pydantic-ai/pull/8969), a regression fix preventing shared `StructuredDict` schema metadata from leaking between output types.
- Added current-main implementation analysis to [MCP Python SDK #1933](https://github.com/modelcontextprotocol/python-sdk/issues/1933) around stdio ownership and process-stream lifecycle.

## Current focus

Agent infrastructure, evals and verification, local-first tooling, reliable computer use, and product systems where AI has to survive contact with real workflows.
