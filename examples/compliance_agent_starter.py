"""
Compliance Agent Starter Template

This is an example of how to build an agent that uses the open-source
BlockINTQL deterministic core + swarm as its reasoning layer.

It can run fully locally (with your own provider data or fetched data)
or hybrid with the BlockINTQL API for richer context.

The agent should:
- Call the deterministic adjudicator / swarm for every material decision
- Produce evidence bundles for anything that might need audit
- Keep a human-in-the-loop for BLOCK or high-risk CAUTION decisions
- Be explicit about which data sources were used
"""

from __future__ import annotations

from typing import Any, Dict
from blockintql.deterministic import adjudicate, export_evidence_bundle


def investigate_address(address: str, chain: str = "ethereum", local_data: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """
    Core investigation step that every serious compliance agent should do.
    """
    result = adjudicate(
        address,
        chain=chain,
        provider_result=local_data.get("provider") if local_data else None,
        local_flow_data=local_data.get("flow") if local_data else None,
        local_graph_data=local_data.get("graph") if local_data else None,
    )

    # Always produce an evidence bundle for regulated workflows
    bundle = export_evidence_bundle(
        subject=address,
        chain=chain,
        policy=None,  # will use default
        provider_result=local_data.get("provider", {}) if local_data else {},
        consensus=result["consensus"],
        final_verdict=result,
    )

    return {
        "verdict": result,
        "evidence_bundle": bundle.to_dict(),
        "recommendation": _recommendation(result),
    }


def _recommendation(result: Dict[str, Any]) -> str:
    v = result.get("verdict")
    if v == "BLOCK":
        return "Do not transact. Escalate and file SAR if required."
    if v == "CAUTION":
        return "Enhanced due diligence required. Consider manual review + additional sources."
    return "Proceed with standard monitoring."
