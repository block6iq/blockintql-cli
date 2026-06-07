"""
Local Graph + Deterministic Agent Template (pure OSS, zero central API).

Fetch your own data (or use public explorers), build graph locally, run deterministic layer.
"""

from blockintql.graph.builder import GraphBuilder
from blockintql.deterministic import adjudicate, export_evidence_bundle

def investigate_with_local_graph(seed: str, your_inflows: list[dict]):
    # 1. Local graph (sophisticated local algos)
    builder = GraphBuilder()
    builder.add_local_taint_flow(seed, your_inflows)
    communities = builder.compute_local_communities()
    graph_json = builder.to_d3()
    
    # 2. Deterministic on the local data
    flow_for_cypher = {"events": your_inflows}  # normalized for FIFO
    res = adjudicate(seed, local_flow_data=flow_for_cypher, local_graph_data={"hops": 2, "concentration": 30})
    
    # 3. Evidence
    bundle = export_evidence_bundle(seed, "ethereum", None, {}, res["consensus"], res)
    
    return {
        "verdict": res,
        "local_graph": graph_json,
        "communities": communities,
        "evidence": bundle.to_dict(),
    }
