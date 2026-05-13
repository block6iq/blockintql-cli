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
  - `monitoring_evidence.source_of_funds`
  - `monitoring_evidence.pattern_signals`
  - `monitoring_evidence.terminal_service_nodes`
- Sanctions hard-rule:
  - sanctions evidence resolves to `BLOCK` and `100/100`

## Optional Workflow Extensions

The public CLI focuses on deterministic screening contracts and auditable consensus output.
Additional workflow layers (for example, filing automation or case-management orchestration) are implementation choices for downstream deployments and are not required for schema compatibility.

## Compatibility Note

Forks are considered schema-compatible when they preserve:

- `consensus.model = sonar_consensus_v1`
- deterministic policy behavior for sanctions and vote aggregation
- stable `consensus` payload keys for downstream automation
