# Deterministic core as a library

Adds the local screening core as an importable package, plus evidence export, MCP tools, and CLI commands that use it.

## What this adds

- **`blockintql.deterministic` library**:
  - `adjudicate()` with provider mapping and the `sonar_consensus_v1` swarm.
  - Sentinel / Cypher (FIFO lot accounting) / Nova.
  - Custom Policy JSON, with the same consensus output shape.
  - Reproducibility hashes and bring-your-own-labels (`own_labels`).

- **EvidenceBundle export/verify**:
  - Policy hash, inputs, provider responses, votes + per-agent rationale, final verdict, `evidence_window`, `policy_mapping`, reproducibility hash, signature support.

- **MCP server**:
  - Tools for adjudicate, swarm, export/verify evidence, custom policy, local graph, guardrails, human-in-the-loop checkpoints, batch operations.

- **Eval harness**:
  - `provider_ablation`, `PUBLIC_TEST_FIXTURE`, consistency checks, policy impact tests, `run_suite()`.

- **GraphBuilder + explorer-v2**:
  - Taint flow, communities, flow analysis, `add_timeline_view`.
  - Exports: GraphML, Neo4j Cypher, D3, HTML.
  - Explorer-v2 save/load workspaces (JSON), evidence export from the drawer, timeline/attribution.

- **CLI**:
  - `blockintql deterministic adjudicate` + `export-evidence` (`--labels` for BYO).
  - `deterministic eval --ablate`.
  - Chat REPL and graph explorer use the local deterministic layer even with no API key.

- **Docs and examples**:
  - `deterministic-library.md`, `how-to-implement-sonar-consensus-v1.md`.
  - Example custom policies and own-labels JSON.
  - Agent starter templates.
  - `tests/test_deterministic.py` (sanctions BLOCK, reproducibility, no silent CLEAR on high risk, evidence).

The library runs against local providers, your own traces, BlockINTQL hosted data, or fully offline. See `docs/` and `examples/`.

## Testing

- Deterministic guarantees: sanctions, reproducibility, evidence, eval suite.
- Explorer workspace save/load, timeline, evidence export.
- CLI commands (`deterministic ...`, `eval --ablate`).
- MCP tools import.
- Local graph exports (GraphML, Neo4j, etc.).
