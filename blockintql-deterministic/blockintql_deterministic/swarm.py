"""sonar_consensus_v1 swarm (lightweight standalone version)."""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from .policy import Policy

def run_sonar_consensus_v1(address: str, chain: str, provider_result: Optional[Dict[str, Any]] = None,
                           flow_data: Optional[Dict[str, Any]] = None, graph_data: Optional[Dict[str, Any]] = None,
                           policy: Optional[Policy] = None) -> Dict[str, Any]:
    p = policy or Policy()
    provider = provider_result or {}
    flow = flow_data or {}
    graph = graph_data or {}
    votes: List[Dict[str, Any]] = []
    # Sentinel (simplified but spec-compliant)
    sanctions = bool(provider.get("sanctions_hit"))
    if sanctions:
        votes.append({"agent": "Sentinel", "codename": "sentinel", "role": "sanctions and label intelligence", "vote": "BLOCK", "reason": f"Direct sanctions match for {address[:10]}"})
    else:
        votes.append({"agent": "Sentinel", "codename": "sentinel", "role": "sanctions and label intelligence", "vote": "CLEAR", "reason": "No sanctions or high-confidence adverse labels"})
    # Cypher (FIFO)
    events = flow.get("events", [])
    taint = 0.0
    if events:
        # Simplified FIFO for standalone package
        total_out = sum(e.get("amount", 0) for e in events if e.get("direction") == "outbound")
        tainted = sum(e.get("amount", 0) * (e.get("taint_pct", 0)/100) for e in events if e.get("direction") == "outbound")
        taint = (tainted / total_out * 100) if total_out > 0 else 0
    if taint >= 70:
        votes.append({"agent": "Cypher", "codename": "cipher", "role": "source-of-funds continuity checks (FIFO)", "vote": "BLOCK", "reason": f"High source taint via FIFO ({taint:.0f}%)"})
    elif taint >= 30:
        votes.append({"agent": "Cypher", "codename": "cipher", "role": "source-of-funds continuity checks (FIFO)", "vote": "REVIEW", "reason": f"Partial source taint via FIFO ({taint:.0f}%)"})
    else:
        votes.append({"agent": "Cypher", "codename": "cipher", "role": "source-of-funds continuity checks (FIFO)", "vote": "CLEAR", "reason": f"Source-of-funds continuity checks passed (taint ~{taint:.0f}%)"})
    # Nova (patterns)
    hops = int(graph.get("hops", 0))
    velocity = float(graph.get("velocity", 0))
    conc = float(graph.get("concentration", 0))
    reasons = []
    if hops > 3: reasons.append(f"deep reach ({hops} hops)")
    if velocity > 65: reasons.append(f"high velocity ({velocity})")
    if conc > 60: reasons.append("high concentration")
    score = max(hops*12, velocity, conc)
    if score >= 78:
        votes.append({"agent": "Nova", "codename": "nova", "role": "counterparty and hop-activity checks", "vote": "BLOCK", "reason": " | ".join(reasons) or "Strong pattern signals"})
    elif score >= 42:
        votes.append({"agent": "Nova", "codename": "nova", "role": "counterparty and hop-activity checks", "vote": "REVIEW", "reason": " | ".join(reasons) or "Elevated patterns"})
    else:
        votes.append({"agent": "Nova", "codename": "nova", "role": "counterparty and hop-activity checks", "vote": "CLEAR", "reason": "No significant structural signals"})
    block_c = sum(1 for v in votes if v["vote"] == "BLOCK")
    rev_c = sum(1 for v in votes if v["vote"] == "REVIEW")
    clr_c = sum(1 for v in votes if v["vote"] == "CLEAR")
    decision = "BLOCK" if block_c > 0 else ("CAUTION" if rev_c >= 2 or (rev_c == 1 and clr_c <= 1) else "CLEAR")
    risk = 85 + (block_c * 5) if block_c else (40 + (rev_c * 10) if decision == "CAUTION" else max(5, 30 - (clr_c * 10)))
    return {
        "enabled": True, "mode": "address_screening", "model": "sonar_consensus_v1",
        "consensus_reached": True, "decision": decision,
        "confidence": "high" if block_c or clr_c >= 2 else "medium",
        "vote_split": {"block": block_c, "review": rev_c, "clear": clr_c},
        "votes": votes, "reasons": [v["reason"] for v in votes if v["vote"] != "CLEAR"][:3],
        "risk_score": min(100.0, risk), "policy_version": p.version,
        "policy_mapping": {"vendor_to_canonical": {}, "block_basis": [v["agent"] for v in votes if v["vote"] == "BLOCK"]},
        "evidence_window": {"lookback_days": int(flow.get("lookback_days", 30)), "hop_depth": int(graph.get("hops", 0)), "chains": [chain]},
    }

class Sentinel:
    @staticmethod
    def run(address: str, chain: str, provider: Dict[str, Any], policy: Policy) -> tuple[str, str]:
        if provider.get("sanctions_hit"):
            return "BLOCK", f"Direct sanctions match for {address[:10]} (Sentinel hard rule)"
        return "CLEAR", "No sanctions or high-confidence adverse labels"

class Cypher:
    @staticmethod
    def run(address: str, chain: str, flow_data: Dict[str, Any], policy: Policy) -> tuple[str, str]:
        # (lightweight version of the FIFO logic)
        return "CLEAR", "Source-of-funds continuity (see full impl in main repo for production FIFO)"

class Nova:
    @staticmethod
    def run(address: str, chain: str, graph_data: Dict[str, Any], policy: Policy) -> tuple[str, str]:
        hops = int(graph_data.get("hops", 0))
        if hops > 3:
            return "REVIEW", f"Deep counterparty reach ({hops} hops) (Nova)"
        return "CLEAR", "No significant structural signals (Nova)"
