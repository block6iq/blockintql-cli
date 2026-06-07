"""
Advanced Compliance Agent Starter with Guardrails + HIL.

Uses the open deterministic core + MCP-exposed guardrails.

Pattern for real agents:
1. Always adjudicate locally first (deterministic layer).
2. Apply guardrails (HIL for BLOCK/CAUTION).
3. Export evidence bundle on every material decision.
4. Log provenance.
"""

from blockintql.deterministic import adjudicate, export_evidence_bundle, Policy
# In real agent: from mcp client call blockintql_guardrail_decision etc.

def safe_investigate(address: str, chain: str = "ethereum", provider_data: dict | None = None):
    # 1. Deterministic layer (OSS core)
    res = adjudicate(address, chain=chain, provider_result=provider_data or {})
    
    # 2. Guardrail (via MCP or local)
    requires_hil = res["verdict"] != "CLEAR" or res["risk_score"] > 50
    
    # 3. Evidence always
    bundle = export_evidence_bundle(
        subject=address, chain=chain, policy=Policy(),
        provider_result=provider_data or {},
        consensus=res["consensus"], final_verdict=res
    )
    
    if requires_hil:
        print(f"HIL REQUIRED for {address}: {res['verdict']} risk={res['risk_score']}")
        print("Action: Human review + attach this bundle to case.")
        # In agent loop: call HIL checkpoint tool, wait for human
    else:
        print(f"AUTO: {address} → {res['verdict']}")
    
    return {"result": res, "bundle": bundle.to_dict(), "requires_hil": requires_hil}

# Example usage in agent:
# decision = safe_investigate("0x7F19...")
# if not decision["requires_hil"]:
#     proceed()
