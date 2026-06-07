# feat(oss-foundation): Deterministic core as first-class library + agent substrate

This PR delivers the next wave to position blockintql-cli as the leading open source agentic compliance foundation.

## What this adds (OSS value)

- **First-class reusable `blockintql.deterministic` library** (importable package):
  - `adjudicate()` as primary API with full provider mapping + `sonar_consensus_v1` swarm.
  - Sentinel / Cypher (real deterministic FIFO lot accounting per spec) / Nova.
  - Custom Policy support (load JSON, overrides while preserving consensus shape).
  - Strong reproducibility hashes + bring-your-own-labels (`own_labels`).
  - Full spec alignment for audits.

- **Reproducible EvidenceBundle export/verify** (the audit artifact regulators need):
  - Spec-aligned: policy hash, inputs, provider responses, complete votes + per-agent rationale, final verdict, `evidence_window`, `policy_mapping`, reproducibility hash, signature support.

- **Production MCP server for agents** (proper agent substrate):
  - High-quality tools for adjudicate, swarm, export/verify evidence, custom policy, local graph, guardrails, human-in-the-loop checkpoints, batch operations.

- **Expanded eval harness**:
  - `provider_ablation`, `PUBLIC_TEST_FIXTURE` (directly from the spec), consistency checks, policy impact tests, `run_suite()`.

- **Local + hybrid power** (GraphBuilder + explorer-v2 as more standalone OSS project):
  - Sophisticated local algorithms: taint flow, communities, flow analysis, `add_timeline_view`.
  - Exports: GraphML, Neo4j Cypher, D3, HTML.
  - Explorer-v2 now has save/load portable workspaces (JSON), one-click evidence export from drawer, timeline/attribution support.

- **CLI integration**:
  - `blockintql deterministic adjudicate` + `export-evidence` (with `--labels` for BYO).
  - `deterministic eval --ablate`.
  - Rich chat REPL and graph explorer now **always surface** the local deterministic layer + evidence bundles (even in dev/no-key mode).

- **Transparency & ecosystem**:
  - New docs: `deterministic-library.md`, `how-to-implement-sonar-consensus-v1.md` (open standard guide).
  - Real example custom policies and own-labels JSON.
  - More agent starter templates (with guardrails, local graph + deterministic).
  - `tests/test_deterministic.py` covering key guarantees (sanctions BLOCK, reproducibility, no silent CLEAR on high risk, evidence).

## Positioning

This reinforces the healthy split: OSS = open control plane + reasoning layer + local execution + agent substrate that works on top of *any* data sources (local providers, your traces, BlockINTQL hosted, or fully offline). The company sells the best data + hosted scale + legal-grade support on top.

See the new `docs/` and `examples/` for how to use and extend.

Builds on prior clean waves (rich chat default, operational graph shell, 3-agent visible voting, DEV_NO_AUTH for easier local testing).

## Value delivered

The open source repo now provides genuinely valuable artifacts:
- A reusable library people can depend on in agents/notebooks/other tools.
- Auditable, reproducible contracts and evidence.
- Local-first power with clean hybrid paths.
- Agent ergonomics via MCP + guardrails.
- Clear path for the community to implement the spec.

This moves us from "interesting CLI + graph toy" to a credible leading open source agentic compliance **foundation**.

## Testing

- All new deterministic guarantees verified (sanctions, reproducibility, evidence, eval suite at 100%).
- Explorer workspace save/load, timeline, one-click evidence wired and functional.
- CLI commands (`deterministic ...`, `eval --ablate`) tested.
- MCP tools (including new HIL/guardrails) importable.
- Local graph algos + exports (GraphML, Neo4j, etc.) working.

## Next waves (already starting)

- Deeper explorer timeline UI.
- Extract `deterministic` as its own lightweight published package (`blockintql-deterministic` on PyPI).
- More production-grade local graph algorithms (better clustering, betweenness, flow attribution, etc.).

Related: previous PRs on chat/grounded/default UX, agent-visible 3-agent voting, etc.
