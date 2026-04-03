"""Agent-native graph generation"""
from typing import Dict, Any
from .builder import GraphBuilder

class AgentGraph:
    """Autonomous graph generation for AI agents"""
    
    @staticmethod
    def from_api_response(response: Dict[str, Any], graph_type: str = "force") -> str:
        """Generate HTML graph from any BlockINTQL API response"""
        builder = GraphBuilder()
        
        if "hops" in response:
            builder.from_trace_result(response)
        elif "cluster_addresses" in response or "addresses" in response:
            builder.from_cluster_result(response)
        
        return builder.to_html(template=graph_type)
