# How to Implement `sonar_consensus_v1` as an Open Standard

This guide makes the deterministic consensus contract a true open standard.

## The Contract (from deterministic-screening-spec-v1.md)

Any implementation claiming compatibility **MUST**:

1. Accept normalized inputs: address/chain + optional provider_result + flow_data + graph_data.
2. Run three named deterministic agents:
   - **Sentinel**: sanctions + label intelligence. Sanctions hit → BLOCK 100.
   - **Cypher**: source-of-funds using deterministic FIFO lot accounting on provided events.
   - **Nova**: structural patterns (hops, velocity, concentration).
3. Emit exactly this shape:

```json
{
  "enabled": true,
  "mode": "address_screening",
  "model": "sonar_consensus_v1",
  "consensus_reached": true,
  "decision": "BLOCK|CAUTION|CLEAR",
  "confidence": "high|medium|low",
  "vote_split": {"block": 0, "review": 0, "clear": 0},
  "votes": [
    {"agent": "Sentinel", "codename": "sentinel", "role": "...", "vote": "...", "reason": "..."},
    ...
  ],
  "reasons": ["..."],
  "risk_score": 0,
  "policy_version": "policy-v1",
  "policy_mapping": { "vendor_to_canonical": {}, "block_basis": [] },
  "evidence_window": { "lookback_days": 30, "hop_depth": 0, "chains": ["ethereum"] }
}
```

4. Be fully deterministic: same inputs + same policy version = identical output + reproducibility_hash.
5. Support custom policies that still produce the above shape.
6. Provide evidence bundles (see evidence.py) with policy_hash, full votes, and provenance.

## Reference Implementation (Python OSS)

See `blockintql/deterministic/swarm.py` and `core.py`:

- `Sentinel.run(...)` → hard BLOCK on sanctions.
- `Cypher.run(...)` → real FIFO lot accounting on `events` list (per spec §5.4).
- `Nova.run(...)` → deterministic structural signals.
- `run_sonar_consensus_v1(...)` → aggregates with "any BLOCK wins" rule.
- `adjudicate(...)` → full pipeline + merge.

The Python version is the reference. Port it, test it, publish it.

## Test Requirements (from spec §10)

Your impl must pass:

- Sanctions hit → BLOCK + 100.0
- Same normalized input → same verdict + hash
- Unmapped high-risk never silently CLEAR
- Stable consensus keys and `sonar_consensus_v1` model

Use the public fixture in `blockintql/eval/__init__.py` (PUBLIC_TEST_FIXTURE) + `run_suite()`.

Example test:

```python
from blockintql.eval import PUBLIC_TEST_FIXTURE
for case in PUBLIC_TEST_FIXTURE:
    res = your_adjudicate(case["address"], provider_result=case["provider"])
    assert res["verdict"] == case["expected"]
```

## Interop with Agents & Graph Explorer

- Expose via MCP (see our server.py) or OpenAI/Anthropic tool schemas.
- Graph explorer can call your impl for "local deterministic" layer on uploaded seeds.
- Always emit evidence bundles for audit.

## Custom Policy Example

See `docs/example-custom-policy.json`. Load it and pass to adjudicate.

Your impl must respect overrides while keeping the votes shape.

## Versioning

- Bump `model` and spec doc on breaking changes.
- Policy has its own `version` + hash for provenance.

## Call to Action

Fork this, implement in your language, run the tests, publish with "sonar_consensus_v1 compatible".

Together we create an open, auditable standard that closed vendors will have to match for credibility in agentic compliance.

See also:
- deterministic-library.md
- deterministic-screening-spec-v1.md
- The reference Python library in this repo.
