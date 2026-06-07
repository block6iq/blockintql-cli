"""
Reference implementation of sonar_consensus_v1 — the 3-agent deterministic swarm.

This is deliberately simple, pure, and auditable. It is the OSS reference
implementation that anyone can read, test, fork, or re-implement.

Agents:
- Sentinel: sanctions + high-confidence label intelligence (hard BLOCK on sanctions)
- Cypher: source-of-funds continuity using deterministic FIFO / reverse-FIFO lot accounting
- Nova: structural / hop / velocity / counterparty pattern detection

The contract guarantees:
- No randomness
- Same inputs + same policy → identical votes and final decision
- Named voters appear in the `votes` array for agentic consumption and audit
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from .policy import Policy, DEFAULT_POLICY


def run_sonar_consensus_v1(
    address: str,
    chain: str,
    provider_result: Optional[Dict[str, Any]] = None,
    flow_data: Optional[Dict[str, Any]] = None,
    graph_data: Optional[Dict[str, Any]] = None,
    policy: Optional[Policy] = None,
) -> Dict[str, Any]:
    """
    Main entry point for the swarm.

    Returns the full sonar_consensus_v1 shaped object that the CLI, explorer,
    and agents expect.
    """
    p = policy or DEFAULT_POLICY
    provider = provider_result or {}
    flow = flow_data or {}
    graph = graph_data or {}

    votes: List[Dict[str, Any]] = []

    # Sentinel
    s_vote, s_reason = Sentinel.run(address, chain, provider, p)
    votes.append({
        "agent": "Sentinel",
        "codename": "sentinel",
        "role": "sanctions and label intelligence",
        "vote": s_vote,
        "reason": s_reason,
    })

    # Cypher (source-of-funds / FIFO)
    c_vote, c_reason = Cypher.run(address, chain, flow, p)
    votes.append({
        "agent": "Cypher",
        "codename": "cipher",
        "role": "source-of-funds continuity checks (FIFO)",
        "vote": c_vote,
        "reason": c_reason,
    })

    # Nova (patterns / hops / velocity)
    n_vote, n_reason = Nova.run(address, chain, graph, p)
    votes.append({
        "agent": "Nova",
        "codename": "nova",
        "role": "counterparty and hop-activity checks",
        "vote": n_vote,
        "reason": n_reason,
    })

    # Aggregation (any BLOCK wins — conservative and auditable per spec)
    block_count = sum(1 for v in votes if v["vote"] == "BLOCK")
    review_count = sum(1 for v in votes if v["vote"] == "REVIEW")
    clear_count = sum(1 for v in votes if v["vote"] == "CLEAR")

    if block_count > 0:
        decision = "BLOCK"
        risk = 85 + (block_count * 5)
    elif review_count >= 2 or (review_count == 1 and block_count == 0 and clear_count <= 1):
        decision = "CAUTION"
        risk = 40 + (review_count * 10)
    else:
        decision = "CLEAR"
        risk = max(5, 30 - (clear_count * 10))

    return {
        "enabled": True,
        "mode": "address_screening",
        "model": "sonar_consensus_v1",
        "consensus_reached": True,
        "decision": decision,
        "confidence": "high" if block_count or clear_count >= 2 else "medium",
        "vote_split": {"block": block_count, "review": review_count, "clear": clear_count},
        "votes": votes,
        "reasons": [v["reason"] for v in votes if v["vote"] != "CLEAR"][:3],
        "risk_score": min(100.0, risk),
        "policy_version": p.version,
        "policy_mapping": {
            "vendor_to_canonical": {},  # filled by caller when using real providers
            "block_basis": [v["agent"] for v in votes if v["vote"] == "BLOCK"],
        },
        "evidence_window": {
            "lookback_days": int(flow_data.get("lookback_days", graph_data.get("lookback_days", 30))),
            "hop_depth": int(graph_data.get("hops", graph_data.get("max_hop", 0))),
            "chains": [chain],
        },
    }


class Sentinel:
    """Sanctions and high-confidence label agent. Hard BLOCK on sanctions."""

    @staticmethod
    def run(address: str, chain: str, provider: Dict[str, Any], policy: Policy) -> tuple[str, str]:
        sanctions = bool(provider.get("sanctions_hit"))
        category = (provider.get("entity_category") or "").lower()
        labels = " ".join(str(x).lower() for x in provider.get("risk_indicators", []))

        if sanctions or "sanction" in category or any(t in labels for t in ("sanction", "ofac", "sdn")):
            return "BLOCK", f"Direct sanctions match for {address[:10]} (Sentinel hard rule)"

        if any(t in labels for t in ("mixer", "ransomware", "darknet", "scam")):
            return "REVIEW", f"High-risk label ({category or 'adverse'}) detected by Sentinel"

        return "CLEAR", "No sanctions or high-confidence adverse labels on resolved entities"


class Cypher:
    """
    Source-of-funds continuity agent (deterministic FIFO lot accounting).

    Implements the exact contract from deterministic-screening-spec-v1.md §5.4.

    Accepts flow_data with key "events": list of normalized transfers:
        [{"timestamp": "...", "token_symbol": "USDC", "direction": "inbound|outbound", "amount": 123.45}, ...]

    Produces taint metrics and a conservative vote.
    This is the OSS reference implementation — anyone can audit or reimplement it.
    """

    @staticmethod
    def run(address: str, chain: str, flow_data: Dict[str, Any], policy: Policy) -> tuple[str, str]:
        events = flow_data.get("events") or flow_data.get("transfers") or []
        if not events:
            return "CLEAR", "No flow data provided to Cypher — defaulting to CLEAR (conservative local mode)"

        # Group + sort by token (deterministic lot construction)
        from collections import defaultdict
        lanes: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

        for e in events:
            sym = str(e.get("token_symbol", "UNKNOWN")).upper()
            direction = str(e.get("direction", "")).lower()
            amt = float(e.get("amount", 0) or 0)
            ts = e.get("timestamp", "")
            if amt <= 0:
                continue
            lanes[sym].append({"ts": ts, "dir": direction, "amt": amt})

        total_in = 0.0
        total_out = 0.0
        funded_out = 0.0

        for sym, evs in lanes.items():
            evs.sort(key=lambda x: str(x["ts"]))  # deterministic time sort
            lots: List[float] = []  # remaining amounts in inbound lots (FIFO queue)

            for ev in evs:
                if ev["dir"] == "inbound":
                    lots.append(ev["amt"])
                    total_in += ev["amt"]
                else:
                    remaining = ev["amt"]
                    total_out += ev["amt"]
                    while remaining > 0 and lots:
                        take = min(remaining, lots[0])
                        funded_out += take
                        remaining -= take
                        lots[0] -= take
                        if lots[0] <= 0:
                            lots.pop(0)
                    if remaining > 0:
                        # unfunded / unknown depletion per spec
                        pass

        coverage = (funded_out / total_out) if total_out > 0 else 1.0
        unknown = max(0.0, total_out - funded_out)
        taint_pct = (1.0 - coverage) * 100.0

        reasons = [f"coverage_ratio={coverage:.2f}", f"unknown_depletion={unknown:.2f}"]

        if taint_pct >= 70 or unknown > total_out * 0.5:
            return "BLOCK", f"High source-of-funds taint via deterministic FIFO ({taint_pct:.0f}% unknown) " + " | ".join(reasons)
        if taint_pct >= 30 or unknown > 0:
            return "REVIEW", f"Partial source-of-funds taint via FIFO lot accounting ({taint_pct:.0f}% unknown) " + " | ".join(reasons)
        return "CLEAR", f"Source-of-funds continuity checks passed (FIFO coverage {coverage:.0%})"


class Nova:
    """
    Counterparty / hop / velocity / concentration agent.

    Fully deterministic. Operates purely on data the caller provides in graph_data.
    This is what lets the open source swarm do meaningful work without any central service.
    """

    @staticmethod
    def run(address: str, chain: str, graph_data: Dict[str, Any], policy: Policy) -> tuple[str, str]:
        if not graph_data:
            return "CLEAR", "No graph data provided to Nova — defaulting to CLEAR (local mode)"

        hops = int(graph_data.get("hops", graph_data.get("counterparty_depth", graph_data.get("max_hop", 0))))
        velocity = float(graph_data.get("velocity", graph_data.get("activity_velocity", 0)))
        concentration = float(graph_data.get("concentration", graph_data.get("counterparty_concentration", 0)))
        terminal_services = int(graph_data.get("terminal_service_count", 0))

        reasons: List[str] = []
        if hops > 3:
            reasons.append(f"deep counterparty reach ({hops} hops)")
        if velocity > 65:
            reasons.append(f"high velocity ({velocity:.0f})")
        if concentration > 60:
            reasons.append("unusual counterparty concentration")
        if terminal_services > 2:
            reasons.append(f"heavy terminal service node exposure ({terminal_services})")

        if not reasons:
            return "CLEAR", "No significant structural or hop-activity signals (Nova)"

        score = max(hops * 12, velocity, concentration * 1.1)
        if score >= 78 or (hops > 4 and concentration > 55):
            return "BLOCK", " | ".join(reasons) + " (Nova)"
        if score >= 42 or hops > 2:
            return "REVIEW", " | ".join(reasons) + " (Nova)"
        return "CLEAR", " | ".join(reasons) + " (Nova)"
