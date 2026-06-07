"""Build graph data from blockchain queries"""
import json
from typing import List, Dict, Any

class GraphBuilder:
    """Convert blockchain data to graph format"""
    
    def __init__(self):
        self.nodes = []
        self.links = []
        self._node_ids = set()
    
    def add_address(self, address: str, label: str = None, color: str = "#69b3a2", size: int = 10):
        """Add an address as a node"""
        if address not in self._node_ids:
            self.nodes.append({
                "id": address,
                "label": label or address[:8],
                "color": color,
                "size": size,
                "type": "address"
            })
            self._node_ids.add(address)
    
    def add_transaction(self, txid: str, from_addr: str, to_addr: str, value: float = None):
        """Add a transaction as a link between addresses"""
        # Ensure nodes exist
        self.add_address(from_addr)
        self.add_address(to_addr)
        
        self.links.append({
            "source": from_addr,
            "target": to_addr,
            "value": value or 1,
            "txid": txid
        })
    
    def from_trace_result(self, trace_data: Dict[str, Any]) -> 'GraphBuilder':
        """Build graph from /v1/trace API result"""
        for hop in trace_data.get("hops", []):
            self.add_transaction(
                txid=hop.get("txid"),
                from_addr=hop.get("from"),
                to_addr=hop.get("to"),
                value=hop.get("amount")
            )
        return self
    
    def from_cluster_result(self, cluster_data: Dict[str, Any]) -> 'GraphBuilder':
        """Build graph from /v1/cluster API result"""

    # --- More sophisticated local graph algorithms (for item 3: local + hybrid power) ---
    def add_local_taint_flow(self, seed: str, inflows: List[Dict[str, Any]]):
        """Simple local taint propagation for Cypher-style without central API."""
        self.add_address(seed, label="Seed", color="#ff6b6b", size=15)
        for flow in inflows:
            src = flow.get("from")
            amt = flow.get("amount", 0)
            self.add_address(src)
            self.links.append({
                "source": src,
                "target": seed,
                "value": amt,
                "taint": flow.get("taint_pct", 0),
                "type": "local-flow"
            })

    def compute_local_communities(self) -> Dict[str, List[str]]:
        """Very simple local community detection (label propagation style) on current links."""
        from collections import defaultdict
        communities: Dict[str, List[str]] = defaultdict(list)
        # Naive: group by connected components using basic traversal
        visited = set()
        def dfs(node, comm_id):
            if node in visited: return
            visited.add(node)
            communities[comm_id].append(node)
            for link in self.links:
                if link["source"] == node and link["target"] not in visited:
                    dfs(link["target"], comm_id)
                if link["target"] == node and link["source"] not in visited:
                    dfs(link["source"], comm_id)
        comm_id = 0
        for node in [n["id"] for n in self.nodes]:
            if node not in visited:
                dfs(node, f"community-{comm_id}")
                comm_id += 1
        return dict(communities)

    def to_d3(self) -> Dict[str, Any]:
        """Export for D3 or other local viz (standalone OSS value)."""
        return {"nodes": self.nodes, "links": self.links, "communities": self.compute_local_communities()}
        seed = cluster_data.get("seed_address")
        self.add_address(seed, label="Seed", color="#ff6b6b", size=15)
        
        for addr in cluster_data.get("cluster_addresses", []):
            self.add_address(addr, color="#4ecdc4")
            self.add_transaction(txid="cluster", from_addr=seed, to_addr=addr, value=1)
        
        return self
    
    def to_json(self) -> str:
        """Export as JSON"""
        return json.dumps({"nodes": self.nodes, "links": self.links}, indent=2)
    
    def to_html(self, template: str = "force") -> str:
        """Export as interactive HTML"""
        from .templates import GraphTemplate
        html = GraphTemplate.get_template(template)
        return html.replace("{{DATA}}", self.to_json())

    # --- Next wave: more sophisticated local exports and algorithms for standalone OSS value ---
    def to_graphml(self) -> str:
        """Export to GraphML format (for yEd, Gephi, etc. - pure local)."""
        lines = ['<?xml version="1.0" encoding="UTF-8"?>']
        lines.append('<graphml xmlns="http://graphml.graphdrawing.org/xmlns"')
        lines.append('         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"')
        lines.append('         xsi:schemaLocation="http://graphml.graphdrawing.org/xmlns')
        lines.append('         http://graphml.graphdrawing.org/xmlns/1.0/graphml.xsd">')
        lines.append('  <key id="label" for="node" attr.name="label" attr.type="string"/>')
        lines.append('  <key id="value" for="edge" attr.name="value" attr.type="double"/>')
        lines.append('  <graph id="G" edgedefault="directed">')
        for i, node in enumerate(self.nodes):
            nid = node.get("id", f"n{i}")
            label = node.get("label", nid)
            lines.append(f'    <node id="{nid}">')
            lines.append(f'      <data key="label">{label}</data>')
            lines.append('    </node>')
        for i, link in enumerate(self.links):
            src = link.get("source")
            tgt = link.get("target")
            val = link.get("value", 1)
            lines.append(f'    <edge id="e{i}" source="{src}" target="{tgt}">')
            lines.append(f'      <data key="value">{val}</data>')
            lines.append('    </edge>')
        lines.append('  </graph>')
        lines.append('</graphml>')
        return '\n'.join(lines)

    def to_neo4j_cypher(self) -> str:
        """Generate Cypher statements for Neo4j import (local power)."""
        stmts = []
        for node in self.nodes:
            nid = node.get("id", "")
            label = node.get("label", nid)
            stmts.append(f"CREATE (n:Address {{id: '{nid}', label: '{label}'}});")
        for link in self.links:
            src = link.get("source")
            tgt = link.get("target")
            val = link.get("value", 1)
            stmts.append(f"MATCH (a:Address {{id: '{src}'}}), (b:Address {{id: '{tgt}'}}) CREATE (a)-[:TRANSFER {{value: {val}}}]->(b);")
        return '\n'.join(stmts)

    def add_timeline_view(self, events: List[Dict[str, Any]]):
        """Add time-based attribution for timeline views (next wave item)."""
        for ev in events:
            ts = ev.get("timestamp", "")
            tx = ev.get("txid", "")
            self.links.append({
                "source": ev.get("from"),
                "target": ev.get("to"),
                "value": ev.get("amount", 1),
                "timestamp": ts,
                "txid": tx,
                "type": "timeline"
            })

    def compute_flow_analysis(self, seed: str) -> Dict[str, Any]:
        """Simple local flow taint and attribution (sophisticated local algo)."""
        inflow = 0.0
        outflow = 0.0
        counterparties = set()
        for link in self.links:
            if link.get("target") == seed:
                inflow += float(link.get("value", 0))
                counterparties.add(link.get("source"))
            if link.get("source") == seed:
                outflow += float(link.get("value", 0))
                counterparties.add(link.get("target"))
        return {
            "seed": seed,
            "total_inflow": inflow,
            "total_outflow": outflow,
            "net": inflow - outflow,
            "unique_counterparties": len(counterparties),
            "counterparties": list(counterparties)[:10]
        }
