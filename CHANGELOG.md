# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased] - Next Wave (Deeper Explorer, Standalone Deterministic Package, Production Local Graph)

### Added / In Progress
- `blockintql-deterministic` packaging polish: real console script (`blockintql-deterministic adjudicate ...` + `eval`), `__main__.py`, fixed pyproject entry points, updated README with source install + CLI examples, version 0.1.1. Now `pip install -e ./blockintql-deterministic` + direct use is fully supported and verified.
- Full local REPL default strengthened: bare `blockintql` (keyless or DEV_NO_AUTH / localhost) now produces the complete rich grounded experience (BLOCKINTQL panel + detailed narrative + full SONAR CONSENSUS with per-agent Sentinel/Cypher/Nova votes + reasons + citations + local_evidence_bundle + one-click export hint) using only the in-process deterministic core. No more "stub".
- Deeper explorer-v2 timeline UI: dedicated `Timeline` React component with focusable events, range scrubber, filter/sort, export buttons; wired into App + store `getTimeline()`.
- `blockintql-deterministic` as its own lightweight published package (separate `pyproject.toml`/`setup.py`, `blockintql_deterministic/` namespace, self-contained for `pip install blockintql-deterministic` while keeping main CLI re-exports for convenience).
- More production-grade local graph algorithms in `GraphBuilder`.
- Explorer workspace save/load + one-click evidence.
- CLI `deterministic adjudicate` + `eval` (13/13 on current suite).
- Expanded local/hybrid power.

See PR body for the prior foundation wave that this builds directly on.

## [Unreleased] - OSS Foundation Wave

### Added
- **First-class `blockintql.deterministic` library** (reusable, importable core):
  - `adjudicate()` primary API with canonical provider mapping + `sonar_consensus_v1` 3-agent swarm (Sentinel sanctions, Cypher real deterministic FIFO lot accounting per spec, Nova patterns/hops/velocity).
  - Custom `Policy` support (JSON loadable, overrides while preserving consensus shape).
  - Bring-your-own-labels via `own_labels` param.
  - Strong reproducibility with `_reproducibility_hash`.
- **Evidence bundles** (`export_evidence_bundle` + `verify_evidence_bundle`):
  - Full spec-aligned artifacts including policy hash/mapping, evidence_window, complete votes + per-agent rationale, signature support, etc.
- **Production MCP server** for agents:
  - Tools for adjudicate/swarm/evidence + custom policy, local graph, guardrails, human-in-the-loop (HIL) checkpoints, batch ops.
- **Expanded evaluation harness** (`blockintql.eval`):
  - `provider_ablation`, `PUBLIC_TEST_FIXTURE` (spec-derived cases), consistency checks, policy impact tests, `run_suite()`.
- **Local + hybrid power**:
  - Enhanced `GraphBuilder`: `add_local_taint_flow`, `compute_local_communities`, `compute_flow_analysis`, `add_timeline_view`, exports to GraphML/Neo4j Cypher/D3/HTML.
  - Explorer-v2 (`apps/explorer-v2`): Save/load portable workspaces (JSON), one-click evidence export from drawer, `getTimeline()` + timeline/attribution support.
- **CLI integration**:
  - `blockintql deterministic adjudicate` + `export-evidence` (supports `--labels` for BYO).
  - `deterministic eval --ablate`.
  - Rich chat REPL and graph explorer now **always surface** the local deterministic layer + evidence bundles (works in dev/no-key mode via `BLOCKINTQL_DEV_NO_AUTH`).
- **Transparency & ecosystem**:
  - New docs: `deterministic-library.md`, `how-to-implement-sonar-consensus-v1.md` (full open standard guide for implementing the spec).
  - Real examples: `example-custom-policy.json`, `example-own-labels.json`.
  - More agent starter templates: `compliance_agent_with_guardrails.py`, `local_graph_deterministic_agent.py`.
  - `tests/test_deterministic.py` (covers sanctions BLOCK, reproducibility, no silent CLEAR on high risk, evidence).
- **Positioning**: OSS is the open control plane + reasoning layer on top of *any* data sources. Company sells best data + scale + support.

This wave moves the project from "interesting CLI + graph toy" to a credible leading open-source agentic compliance **foundation**.

Builds on prior waves (rich BlockINTQL Chat default, operational graph shell, visible 3-agent voting in SONAR, DEV_NO_AUTH for keyless local testing).

## Previous Releases (selected)

- **Rich chat / grounded / default UX wave** (merged as #17, #18, #20 etc.):
  - Default bare `blockintql` to interactive BlockINTQL Chat REPL.
  - Grounded responses with [GROUNDED] narrative, SONAR CONSENSUS (3 agents voting), citations, cost.
  - Chart/graph operational (terminal charts, promptable graph REPL).
  - Improved first-run UX, auth guidance, error handling.
  - 3 agents (Sentinel/Cypher/Nova) now do substantive work and visibly vote.

See git history for full details of prior features (provider integration, x402 payments, LangChain tool, etc.).
