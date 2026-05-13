# Sonar Capability Scope (Public CLI V1)

This document defines which Sonar-style capabilities are active in the public CLI launch scope.

## Active Now (V1)

- Deterministic screening consensus (`sonar_consensus_v1`)
- Three named voters in `consensus.votes`:
  - `Sentinel` (`sentinel`) for sanctions and label intelligence
  - `Cypher` (`cipher`) for source-of-funds continuity checks
  - `Nova` (`nova`) for counterparty and hop-activity checks
- Deterministic vote aggregation with auditable:
  - `vote_split`
  - `reasons`
  - `policy_mapping`
  - `evidence_window`
- Sanctions hard-rule:
  - sanctions evidence resolves to `BLOCK` and `100/100`

## Not in Public CLI V1

- Auto-write SAR workflows
- Auto-file SAR workflows
- Officer/analyst queue workflow state machines
- Internal alert review lifecycle orchestration
- Internal organization-specific briefing/task automation

These surfaces remain out of scope for public CLI launch and are intentionally not required for deterministic address screening compatibility.

## Compatibility Note

Forks are considered schema-compatible when they preserve:

- `consensus.model = sonar_consensus_v1`
- deterministic policy behavior for sanctions and vote aggregation
- stable `consensus` payload keys for downstream automation
