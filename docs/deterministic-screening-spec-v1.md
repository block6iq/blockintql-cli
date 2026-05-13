# Deterministic Screening Spec (V1)

This document defines the canonical deterministic screening contract for BlockINTQL-style address screening in the public CLI.

It is designed so independent builders can reproduce decisions consistently with the same normalized inputs.

## 1. Scope

This spec covers deterministic local policy for:

- `screen`
- `verdict`

This spec does **not** include proprietary data feeds, private labels, or internal enrichment systems.

## 2. Inputs

Required logical input:

- `address` (string)
- `chain` (string, e.g. `ethereum`)

Optional local-provider enrichment input (normalized):

- `entity_name` (string or null)
- `entity_category` (string or null)
- `risk_score` (number, 0-100)
- `risk_indicators` (string list)
- `sanctions_hit` (boolean)
- `vendor_verdict` (string or null)
- `vendor_category` (string or null)

## 3. Deterministic Pipeline

1. Collect BlockINTQL-native result for subject address.
2. Optionally enrich via local provider call (provider key stays local).
3. Normalize provider result fields.
4. Apply canonical category mapping and policy rules.
5. Apply sanctions hard-override.
6. Emit final decision object and consensus object.

No step may use non-deterministic randomness in policy resolution.

## 4. Canonical Category Mapping

Provider evidence is mapped into canonical classes, including:

- `sanctions`
- `mixer`
- `ransomware`
- `darknet`
- `scam`
- `fraud`
- `money_laundering`
- `exchange`
- `defi`
- `bridge`
- `wallet`
- conservative unknown buckets:
  - `unknown_high_risk`
  - `unknown_review`
  - `unknown_low_risk`

## 5. Decision Rules

## 5.1 Sanctions Hard Rule

If either condition is true:

- `sanctions_hit == true`, or
- canonical category resolves to `sanctions`

then final result must be:

- `verdict = BLOCK`
- `action = block`
- `safe = false`
- `risk_score = 100.0`
- `risk_indicators` includes sanctions evidence marker

## 5.2 Category Policy Rule

If sanctions hard rule is not triggered:

- mapped high-risk illicit categories resolve to `BLOCK` or `CAUTION`
- elevated but unmapped data resolves conservatively to `UNKNOWN`/`CAUTION`
- low/no mapped evidence resolves to `CLEAR`

## 5.3 Risk Score Merge Rule

- effective provider risk = provider `risk_score`
- if sanctions hard rule triggers, effective provider risk is forced to `100.0`
- final score = max(native_score, effective_provider_risk), with sanctions force-clamp to `100.0`

## 5.4 Source-of-Funds FIFO / Reverse-FIFO (Deterministic)

This contract uses deterministic lot accounting for token source-of-funds continuity checks.

### Inputs

- normalized token transfer events with:
  - `timestamp`
  - `token_symbol`
  - `direction` (`inbound|outbound`)
  - `amount`

### Deterministic lot construction

1. Group events by `token_symbol`.
2. Sort each token lane by event time ascending.
3. For each inbound event, append a lot with remaining amount.
4. For each outbound event, consume remaining amounts from lots in FIFO order.

### Reverse-FIFO view

Implementations MAY expose a reverse walk for operator readability, but accounting outcome must remain equivalent to FIFO lot depletion:

- emitted outbound amount
- funded portion (matched to prior inbound lots)
- unfunded portion (`unknown_depletion`)

### Required output metrics

Implementations claiming compatibility should expose:

- `coverage_ratio = funded_outbound / total_outbound` (or `1.0` if outbound is zero)
- `unknown_depletion` (sum of outbound not matched to prior inbound lots)
- `total_inbound`
- `total_outbound`
- `terminal_service_nodes` (top terminal labeled service counterparties where traversal stops)
- `terminal_service_node_count`

### Traversal guardrail for source-of-funds context

When collecting multi-hop counterparty context, implementations should treat known service categories as terminal expansion nodes. Typical terminal categories include:

- `exchange`
- `bridge`
- `defi`
- `custodian`
- `service`

This keeps reverse source-of-funds context from recursively traversing through high-throughput service wallets while still preserving those entities in the evidence surface.

### Deterministic behavior guarantees

- No randomness in lot selection.
- Same ordered input events always produce the same depletion result.
- Negative lot balances are not allowed.
- Outbound above known inbound is accumulated into `unknown_depletion`.

## 6. Consensus Contract (Public)

Deterministic consensus payload format:

- `enabled` (bool)
- `mode` (`address_screening`)
- `model` (`sonar_consensus_v1`)
- `consensus_reached` (bool)
- `decision` (`BLOCK|CAUTION|CLEAR|UNKNOWN`)
- `confidence` (`high|medium|low`)
- `vote_split` object with integer votes:
  - `block`
  - `review`
  - `clear`
- `votes` list with named deterministic voters:
  - `agent` (`Sentinel|Cypher|Nova`)
  - `codename` (`sentinel|cipher|nova`)
  - `role`
  - `vote` (`BLOCK|REVIEW|CLEAR`)
  - `reason`
- `reasons` (string list)
- `evidence_window`:
  - `lookback_days`
  - `hop_depth`
  - `chains`
- `policy_mapping`:
  - `vendor_to_canonical` map
  - `block_basis` list

## 7. Output Schema (Minimum)

A compliant deterministic screening output includes:

- `subject`
- `subject_type`
- `chain`
- `verdict`
- `safe`
- `risk_score`
- `risk_indicators`
- `action`
- `entity`
- `narrative`
- `provider_data` (allowlisted summary only)
- `consensus`

## 8. Privacy Contract

- provider API keys remain local to the CLI runtime
- raw vendor payloads are not sent upstream in this contract
- only allowlisted provider summary fields are emitted

## 9. Compatibility & Versioning

Policy/contract version identifiers:

- `model = sonar_consensus_v1`
- document version: `deterministic-screening-spec-v1`

Any breaking change requires a new versioned spec file.

## 10. Test Requirements for Re-implementations

Any fork claiming compatibility should include fixture tests proving:

1. Sanctions hit always yields `BLOCK` + `100.0`.
2. Same normalized input always yields same verdict and policy mapping.
3. Unmapped elevated-risk categories never silently return `CLEAR`.
4. Consensus payload keys remain stable and present.
