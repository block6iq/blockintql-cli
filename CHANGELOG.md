# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added / In Progress
- **1.5.5 local OFAC screening**: package ships `blockintql/data/ofac_sanctioned_crypto_addresses.txt`. `verdict` / `screen` with no provider use bundled labels, so known OFAC addresses (e.g. Tornado Cash `0x7F1972…`) return BLOCK / 100 without an API key. `0x` addresses auto-detect as Ethereum even if a stray prefix is pasted.

### Added / In Progress
- `blockintql-deterministic` packaging polish: real console script (`blockintql-deterministic adjudicate ...` + `eval`), `__main__.py`, fixed pyproject entry points, updated README with source install + CLI examples, version 0.1.1. Now `pip install -e ./blockintql-deterministic` + direct use is fully supported and verified.
- Bare `blockintql` (no key, `DEV_NO_AUTH`, or localhost) runs the local deterministic core: BLOCKINTQL panel, narrative, SONAR CONSENSUS (Sentinel/Cypher/Nova votes, reasons, citations), and evidence bundle export.
- Deeper explorer-v2 timeline UI: dedicated `Timeline` React component with focusable events, range scrubber, filter/sort, export buttons; wired into App + store `getTimeline()`.
- `blockintql-deterministic` as its own lightweight published package (separate `pyproject.toml`/`setup.py`, `blockintql_deterministic/` namespace, self-contained for `pip install blockintql-deterministic` while keeping main CLI re-exports for convenience).
- Additional local graph algorithms in `GraphBuilder`.
- Explorer workspace save/load + one-click evidence.
- CLI `deterministic adjudicate` + `eval` (13/13 on current suite).
- Deeper explorer-v2 timeline UI: dedicated `Timeline` React component with focusable events, integrated into main view; `getTimeline()` + attribution support in store.
- `blockintql-deterministic` as its own lightweight published package (separate `pyproject.toml`/`setup.py`, `blockintql_deterministic/` namespace, self-contained for `pip install blockintql-deterministic` while keeping main CLI re-exports for convenience).
- Additional local graph algorithms in `GraphBuilder`: `compute_betweenness_centrality` (Brandes approx), `compute_pagerank`, `compute_flow_analysis`, `add_timeline_view`, plus GraphML + Neo4j Cypher exports.
- Explorer workspace save/load now fully functional (portable JSON); one-click evidence + timeline buttons wired.
- CLI `deterministic adjudicate` now supports `--labels` (BYO labels end-to-end).
- Local `blockintql.graph` and explorer work without a hosted service.

## [Unreleased] - Deterministic library

### Added
- **`blockintql.deterministic` library**:
  - `adjudicate()` with provider mapping and the `sonar_consensus_v1` swarm (Sentinel, Cypher FIFO, Nova patterns/hops/velocity).
  - Custom `Policy` JSON, same consensus output shape.
  - Bring-your-own-labels via `own_labels`.
  - Reproducibility hash.
- **Evidence bundles** (`export_evidence_bundle` + `verify_evidence_bundle`):
  - Policy hash/mapping, evidence_window, votes + per-agent rationale, signature support.
- **MCP server**:
  - Tools for adjudicate/swarm/evidence, custom policy, local graph, guardrails, human-in-the-loop checkpoints, batch ops.
- **Eval harness** (`blockintql.eval`):
  - `provider_ablation`, `PUBLIC_TEST_FIXTURE`, consistency checks, policy impact tests, `run_suite()`.
- **GraphBuilder + explorer-v2**:
  - `add_local_taint_flow`, `compute_local_communities`, `compute_flow_analysis`, `add_timeline_view`; GraphML/Neo4j Cypher/D3/HTML export.
  - Explorer-v2 save/load workspaces, evidence export from the drawer, `getTimeline()`.
- **CLI**:
  - `blockintql deterministic adjudicate` + `export-evidence` (`--labels` for BYO).
  - `deterministic eval --ablate`.
  - Chat REPL and graph explorer use the local deterministic layer with `BLOCKINTQL_DEV_NO_AUTH`.
- **Docs and examples**:
  - `deterministic-library.md`, `how-to-implement-sonar-consensus-v1.md`.
  - `example-custom-policy.json`, `example-own-labels.json`.
  - Agent starters: `compliance_agent_with_guardrails.py`, `local_graph_deterministic_agent.py`.
  - `tests/test_deterministic.py` (sanctions BLOCK, reproducibility, no silent CLEAR on high risk, evidence).

## Previous Releases (selected)

- **Rich chat / grounded / default UX** (merged as #17, #18, #20 etc.):
  - Default bare `blockintql` to interactive BlockINTQL Chat REPL.
  - Grounded responses with [GROUNDED] narrative, SONAR CONSENSUS (3 agents voting), citations, cost.
  - Chart/graph operational (terminal charts, promptable graph REPL).
  - Improved first-run UX, auth guidance, error handling.
  - 3 agents (Sentinel/Cypher/Nova) now do substantive work and visibly vote.

See git history for full details of prior features (provider integration, x402 payments, LangChain tool, etc.).

## Unreleased - Graph explorer redesign

### Changed
- Redesign explorer-v2 (`blockintql graph shell`) around search, node click, tx history, plot, expand, and image export.
- New prominent TopBar address search: paste real 0x... + "Add to Graph" (uploadSeeds + auto-focus).
- Click nodes in graph → loads full tx history + wallet summary in drawer.
- Double-click nodes → expand counterparties (graph growth).
- NodeDrawer: wallet summary (balance, volume, first/last activity, holdings), transaction table with Balance After, Flow/Risk pills, labeled From/To, checkboxes, "Plot Selected".
- Plot selected transactions now reliably adds real in/out directed edges + nodes to the live Cytoscape canvas.
- Graph image export: dedicated PNG (high-res dark bg) + SVG buttons in top bar using native Cytoscape export + download.
- Search and exports are primary; shell customization moved under "Advanced Shell".
- Real address smoke tests (e.g. 0x742d35Cc6634C0532925a3b844Bc9e7595f6EEd0).
- Globals exposed for standalone use; ShellSpec still sets the initial prompt but does not dominate the explorer chrome.

See feat/redesign-graph-explorer-ui for the diff.
