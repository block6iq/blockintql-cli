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
