"""
Proper, production-grade MCP server for the BlockINTQL open-source deterministic core.

This is the primary way agents (Claude, Cursor, custom ReAct loops, etc.) should
interact with the reasoning layer. It exposes the full audited contracts.

Install: pip install "mcp[cli]"
Run:     python -m blockintql.mcp.server

Tools exposed:
- adjudicate (full pipeline + swarm)
- swarm (just the 3 named agents)
- export_evidence (the audit artifact)
- load_policy + adjudicate_with_policy (custom org policies)
- build_local_graph
- verify_evidence
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    FastMCP = None

from ..deterministic import (
    adjudicate,
    run_sonar_consensus_v1,
    export_evidence_bundle,
    verify_evidence_bundle,
    Policy,
    load_policy,
)
from ..graph.builder import GraphBuilder


def create_mcp_server(name: str = "blockintql-deterministic") -> "FastMCP":
    if FastMCP is None:
        raise RuntimeError("pip install 'mcp[cli]' to use the BlockINTQL MCP server")

    mcp = FastMCP(name)

    @mcp.tool(
        description="Run the complete deterministic screening pipeline + 3-agent swarm (Sentinel/Cypher/Nova). "
                    "Works 100% locally if you supply provider_result + optional flow/graph data."
    )
    def blockintql_adjudicate(
        address: str,
        chain: str = "ethereum",
        provider_result: Optional[Dict[str, Any]] = None,
        flow_data: Optional[Dict[str, Any]] = None,
        graph_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return adjudicate(
            address=address,
            chain=chain,
            provider_result=provider_result,
            local_flow_data=flow_data,
            local_graph_data=graph_data,
        )

    @mcp.tool(description="Run only the 3-agent sonar_consensus_v1 swarm for explainability.")
    def blockintql_swarm(
        address: str,
        chain: str = "ethereum",
        provider_result: Optional[Dict[str, Any]] = None,
        flow_data: Optional[Dict[str, Any]] = None,
        graph_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return run_sonar_consensus_v1(
            address=address,
            chain=chain,
            provider_result=provider_result,
            flow_data=flow_data,
            graph_data=graph_data,
        )

    @mcp.tool(description="Export a full, hashable, reproducible evidence bundle for audit / SAR / defensibility.")
    def blockintql_export_evidence(
        address: str,
        chain: str = "ethereum",
        provider_result: Optional[Dict[str, Any]] = None,
        flow_data: Optional[Dict[str, Any]] = None,
        graph_data: Optional[Dict[str, Any]] = None,
        sign_with_secret: Optional[str] = None,
    ) -> Dict[str, Any]:
        result = adjudicate(address, chain=chain, provider_result=provider_result,
                            local_flow_data=flow_data, local_graph_data=graph_data)
        secret = sign_with_secret.encode() if sign_with_secret else None
        bundle = export_evidence_bundle(
            subject=address,
            chain=chain,
            policy=Policy(),
            provider_result=provider_result or {},
            consensus=result["consensus"],
            final_verdict=result,
            local_inputs={"flow": flow_data, "graph": graph_data},
            secret=secret,
        )
        return bundle.to_dict()

    @mcp.tool(description="Verify a previously exported evidence bundle (consistency + optional signature).")
    def blockintql_verify_evidence(bundle: Dict[str, Any], secret: Optional[str] = None) -> Dict[str, Any]:
        # Reconstruct minimal bundle object for verification
        from ..deterministic.evidence import EvidenceBundle, verify_evidence_bundle
        b = EvidenceBundle(**{k: v for k, v in bundle.items() if k in EvidenceBundle.__dataclass_fields__})
        ok = verify_evidence_bundle(b, secret=secret.encode() if secret else None)
        return {"valid": ok, "bundle_hash": b.bundle_hash}

    @mcp.tool(description="Adjudicate using a custom policy (organizations maintain their own rule sets).")
    def blockintql_adjudicate_with_policy(
        address: str,
        policy: Dict[str, Any],
        chain: str = "ethereum",
        provider_result: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        p = load_policy(policy)
        return adjudicate(address, chain=chain, provider_result=provider_result, policy=p)

    @mcp.tool(description="Build and export a local investigation graph from data you already own. Supports advanced formats for standalone use.")
    def blockintql_build_local_graph(
        addresses: List[str],
        edges: Optional[List[Dict[str, Any]]] = None,
        format: str = "json",
    ) -> Any:
        builder = GraphBuilder()
        for a in addresses:
            builder.add_node(a)
        if edges:
            for e in edges:
                builder.add_edge(e.get("from"), e.get("to"), e)
        if format == "html":
            return builder.to_html()
        if format == "d3":
            return builder.to_d3()
        if format == "graphml":
            return builder.to_graphml()
        if format == "neo4j":
            return builder.to_neo4j_cypher()
        if format == "flow":
            # Example local flow analysis
            return builder.compute_flow_analysis(addresses[0] if addresses else "")
        return builder.to_json()

    # --- Human-in-the-loop primitives and guardrails (more MCP surface) ---
    @mcp.tool(description="Guardrail: require human review for BLOCK or high-risk CAUTION decisions. Returns decision + required action.")
    def blockintql_guardrail_decision(verdict: str, risk_score: float, auto_approve_clear: bool = True) -> Dict[str, Any]:
        if verdict == "BLOCK":
            return {"decision": "BLOCK", "requires_human": True, "action": "Escalate to compliance officer. Do not auto-execute. Log for SAR."}
        if verdict == "CAUTION" and risk_score > 60:
            return {"decision": "CAUTION", "requires_human": True, "action": "Human review required before any transaction. Collect additional evidence."}
        if auto_approve_clear and verdict == "CLEAR":
            return {"decision": "CLEAR", "requires_human": False, "action": "Auto-approve with standard monitoring."}
        return {"decision": verdict, "requires_human": True, "action": "Manual review recommended per policy."}

    @mcp.tool(description="Human-in-the-loop checkpoint. Log decision with rationale for audit trail.")
    def blockintql_hil_checkpoint(address: str, decision: str, rationale: str, reviewer: str = "agent") -> Dict[str, Any]:
        return {
            "checkpoint": "HIL",
            "address": address,
            "decision": decision,
            "rationale": rationale,
            "reviewer": reviewer,
            "timestamp": "now",
            "next": "Export evidence bundle and attach to case file.",
        }

    @mcp.tool(description="Apply guardrails across a batch of addresses using local deterministic layer.")
    def blockintql_batch_with_guardrails(addresses: List[str]) -> List[Dict[str, Any]]:
        results = []
        for addr in addresses:
            res = adjudicate(addr)
            guard = blockintql_guardrail_decision(res["verdict"], res["risk_score"])  # type: ignore
            results.append({"address": addr, "verdict": res["verdict"], "guardrail": guard})
        return results

    return mcp


if __name__ == "__main__":
    mcp = create_mcp_server()
    mcp.run()
