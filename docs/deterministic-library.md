# BlockINTQL Deterministic Library (v0.1+)

This is the new first-class, importable core of the open source project.

## Installation & Usage

```bash
pip install blockintql
```

```python
from blockintql.deterministic import adjudicate, run_sonar_consensus_v1, export_evidence_bundle

result = adjudicate(
    "0x7F19720A857F834887FC9A7bC0a0fBe7Fc7f8102",
    chain="ethereum",
    # You can pass data from any source
    provider_result=your_local_provider_dict,
    local_flow_data=your_tracing_data,      # for Cypher
    local_graph_data=your_graph_data,       # for Nova
)

print(result["verdict"], result["risk_score"])
print(result["consensus"]["votes"])   # Sentinel, Cypher, Nova

bundle = export_evidence_bundle(...)
# Save this for audit / SAR
```

## The Swarm (sonar_consensus_v1)

The three named deterministic agents are implemented in pure Python in `blockintql.deterministic.swarm`:

- **Sentinel** — sanctions + high-confidence label hard rules
- **Cypher** — source-of-funds continuity (FIFO lot accounting style)
- **Nova** — structural / hop / velocity / concentration patterns

They are deliberately simple and auditable. The contract is that the same inputs + same policy version always produce the same votes.

## Custom Policies

Organizations can maintain their own rule sets:

```python
from blockintql.deterministic import Policy, load_policy, adjudicate

my_policy = Policy(
    name="my-fund-policy-v3",
    rules=[ ... ],
)
result = adjudicate(..., policy=my_policy)
```

The output still uses the `sonar_consensus_v1` shape so downstream agents and audit systems stay compatible.

## Evidence Bundles

`export_evidence_bundle(...)` produces a reproducible, hashable artifact containing:

- Exact policy version + hash
- Normalized inputs
- Provider result (if any)
- Full swarm votes + reasons
- Final verdict
- Reproducibility hash

This is what regulated entities need when something goes wrong six months later.

## MCP Server

```bash
python -m blockintql.mcp.server
```

Exposes `blockintql_adjudicate`, `blockintql_swarm`, `blockintql_export_evidence`, and local graph tools to any MCP-capable agent (Claude Desktop, Cursor, etc.).

## Reproducibility Guarantee

All functions in this library are pure and deterministic. Given the same normalized inputs and the same `Policy`, the output (including the `reproducibility_hash`) will be identical across runs, Python versions, and machines.

This is the foundation we are building the open source agentic compliance ecosystem on top of.
