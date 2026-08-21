# blockintql-deterministic

Python deterministic screening core and `sonar_consensus_v1` swarm (Sentinel / Cypher / Nova).

Extracted from blockintql-cli so it can be installed without the full CLI.

**Install independently:**
```bash
pip install blockintql-deterministic
```

**Or from source (monorepo / dev):**
```bash
pip install -e ./blockintql-deterministic
```

**Primary library usage:**
**Primary usage:**
```python
from blockintql_deterministic import adjudicate, run_sonar_consensus_v1, export_evidence_bundle, Policy, load_policy

result = adjudicate("0x7F19720A857F834887FC9A7bC0a0fBe7Fc7f8102", chain="ethereum",
                    provider_result=your_local_provider_dict,
                    own_labels=your_byo_labels,  # bring your own labels
                    local_flow_data=your_fifo_events,  # for real Cypher FIFO
                    local_graph_data=your_hops_data)
bundle = export_evidence_bundle(...)  # reproducible audit artifact
```

**Tiny standalone CLI (included):**
```bash
blockintql-deterministic --version
blockintql-deterministic adjudicate 0x7F19720A857F834887FC9A7bC0a0fBe7Fc7f8102
blockintql-deterministic adjudicate 0x0000000000000000000000000000000000000000 --provider-json '{"sanctions_hit": true}'
blockintql-deterministic eval
```

See the full open standard guide, custom policy examples, and how to implement `sonar_consensus_v1` yourself:
https://github.com/block6iq/blockintql-cli/tree/main/docs/how-to-implement-sonar-consensus-v1.md

For the full MCP server, rich REPL, graph explorer, and `blockintql` commands use the main package (`pip install blockintql`).

See the full open standard guide and CLI integration in the main repo:
https://github.com/block6iq/blockintql-cli/tree/main/docs/how-to-implement-sonar-consensus-v1.md

Deterministic, runs locally, and accepts data from any source.

MIT licensed.
