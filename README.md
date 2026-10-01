<a href="https://yashkhou.com"><img src="https://yashkhou.com/assets/v3/og.jpg" alt="Yash Khoury: the proof layer for AI agents" width="100%"></a>

### Agents say “done”. I build the tools that check.

I'm Yash. I build open-source infrastructure that sits between an AI agent and the real world. It records what the agent did, checks what it claims, and pins down what it's allowed to call. Everything is local-first and model-agnostic, built on boring formats you can inspect.

**[yashkhou.com](https://yashkhou.com/)** · [@yashkhou on X](https://x.com/yashkhou)

## The proof stack

| Project | What it proves |
| --- | --- |
| **[RunLedger](https://github.com/yashkhou/runledger)** | What the agent actually did. Tool calls, decisions and retries are hash-chained, so any edit, deletion or reordering breaks verification. |
| **[BrowserProof](https://github.com/yashkhou/browserproof)** | That the browser really ended up where the agent claims. Explicit assertions, evidence hashes, CI exit codes. |
| **[ActionMesh](https://github.com/yashkhou/actionmesh)** | What the agent is allowed to call. One typed contract per capability, served over MCP-style, HTTP and CLI. |
| **[Verify](https://github.com/yashkhou/verify)** | That the output is right. Checks DOCX/XLSX/PPTX/PDF files, repos and reversible actions without trusting the generator. |
| **[Agent Compat Lab](https://github.com/yashkhou/agent-compat-lab)** | That one repo tells Codex, Claude Code, Gemini CLI and OpenCode the same thing. Outputs SARIF. |
| **[Agent Reliability Lab](https://github.com/yashkhou/agent-reliability-lab)** | Twelve deterministic tools for hardening agent infrastructure: MCP chaos, contract fuzzing, context firewalls, replay, evals and more. |

```bash
npm install github:yashkhou/runledger && npx runledger verify
```

## Also building

- [Glyph](https://github.com/yashkhou/glyph): an experimental design language with memory, so agents can reason about structure instead of pixels.
- [Commander Plus](https://github.com/yashkhou/commander-plus): a local-first agent workstation with MCP workspaces, reusable skills, browser control and persistent project context.
- [OpenRetention](https://github.com/yashkhou/openretention): self-hosted customer-success software with explainable health scores and revenue-at-risk prioritisation.

## Recent upstream work

- Opened [Stellar-agentic #429](https://github.com/StellarAgent-AI-Agent-Payment-Rails/Stellar-agentic/pull/429) to repair repository-specific README links.
- Reviewed [pydantic-ai #8969](https://github.com/pydantic/pydantic-ai/pull/8969), a regression fix preventing shared `StructuredDict` schema metadata from leaking between output types.
- Added current-main implementation analysis to [MCP Python SDK #1933](https://github.com/modelcontextprotocol/python-sdk/issues/1933) around stdio ownership and process-stream lifecycle.

If one of these saves you a bad night, a ⭐ helps the next person find it.
