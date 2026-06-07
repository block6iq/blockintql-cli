# blockintql-deterministic

First-class, versioned, pure-Python deterministic screening core + `sonar_consensus_v1` 3-agent swarm (Sentinel / Cypher / Nova) for agentic on-chain compliance.

This is the reusable open standard / library extracted from the blockintql-cli OSS project.

**Install independently:**
```bash
pip install blockintql-deterministic
```

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

See the full open standard guide and CLI integration in the main repo:
https://github.com/block6iq/blockintql-cli/tree/main/docs/how-to-implement-sonar-consensus-v1.md

All logic is deterministic, auditable, and works fully locally / hybrid with any data sources.

MIT licensed. Part of the effort to make blockintql-cli the leading open source agentic compliance foundation.
