"""
Deterministic core (standalone lightweight package version).

See the main blockintql-cli repo for the full context, spec, and CLI integration.
This file is intentionally self-contained for easy independent publishing as
`blockintql-deterministic`.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import hashlib
import json

from .policy import Policy, DEFAULT_POLICY

CANONICAL_PROVIDER_RULES: List[Dict[str, Any]] = [
    {"category": "sanctions", "recommended_verdict": "BLOCK", "severity": "critical", "label_tokens": {"sanction", "sanctions", "ofac", "sdn", "blocked"}},
    {"category": "mixer", "recommended_verdict": "CAUTION", "severity": "high", "label_tokens": {"mixer", "mixing", "tumbler", "coinjoin", "tornado cash"}},
    {"category": "ransomware", "recommended_verdict": "BLOCK", "severity": "critical", "label_tokens": {"ransomware", "extortion"}},
    {"category": "darknet", "recommended_verdict": "BLOCK", "severity": "critical", "label_tokens": {"darknet", "dark market", "darknet market"}},
    {"category": "scam", "recommended_verdict": "BLOCK", "severity": "critical", "label_tokens": {"scam", "fraud", "phishing", "drainer", "hack", "exploit"}},
    {"category": "exchange", "recommended_verdict": "CLEAR", "severity": "low", "label_tokens": {"exchange", "cex"}},
    {"category": "defi", "recommended_verdict": "CLEAR", "severity": "low", "label_tokens": {"defi", "dex", "amm", "protocol"}},
    {"category": "bridge", "recommended_verdict": "CAUTION", "severity": "medium", "label_tokens": {"bridge", "cross-chain"}},
    {"category": "wallet", "recommended_verdict": "CLEAR", "severity": "low", "label_tokens": {"wallet", "eoa", "externally_owned_account"}},
]

def _text_set(values: Any) -> set[str]:
    items: set[str] = set()
    if not values:
        return items
    if isinstance(values, (list, tuple, set)):
        for v in values:
            t = str(v or "").strip().lower()
            if t:
                items.add(t)
    else:
        t = str(values or "").strip().lower()
        if t:
            items.add(t)
    return items

def _hash_inputs(*parts: Any) -> str:
    blob = json.dumps(parts, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()

def adjudicate_provider_result(result: Dict[str, Any], policy: Optional[Policy] = None) -> Dict[str, Any]:
    p = policy or DEFAULT_POLICY
    indicators = _text_set(result.get("risk_indicators"))
    entity_category = str(result.get("entity_category") or "").strip().lower()
    haystack = " ".join(sorted(indicators | ({entity_category} if entity_category else set())))
    reasons: List[str] = []

    if result.get("sanctions_hit"):
        return {
            "canonical_category": "sanctions",
            "recommended_verdict": "BLOCK",
            "severity": "critical",
            "confidence": "high",
            "reasons": ["Provider reported a direct sanctions hit."],
        }

    for rule in CANONICAL_PROVIDER_RULES:
        if any(token in haystack for token in rule["label_tokens"]):
            reasons.append(f"Matched provider category tokens for {rule['category']}.")
            pol = next((r for r in p.rules if r.get("category") == rule["category"]), None)
            verdict = pol.get("verdict", rule["recommended_verdict"]) if pol else rule["recommended_verdict"]
            return {
                "canonical_category": rule["category"],
                "recommended_verdict": verdict,
                "severity": pol.get("severity", rule["severity"]) if pol else rule["severity"],
                "confidence": "medium",
                "reasons": reasons,
            }

    risk_score = float(result.get("risk_score") or 0)
    if risk_score >= 85:
        return {
            "canonical_category": "unknown_high_risk",
            "recommended_verdict": "CAUTION",
            "severity": "high",
            "confidence": "low",
            "reasons": ["Provider returned a high risk score but the category schema could not be mapped safely."],
        }
    if risk_score >= 40:
        return {
            "canonical_category": "unknown_review",
            "recommended_verdict": "UNKNOWN",
            "severity": "medium",
            "confidence": "low",
            "reasons": ["Provider returned elevated risk without a canonical category mapping."],
        }
    return {
        "canonical_category": "unknown_low_risk",
        "recommended_verdict": "CLEAR",
        "severity": "low",
        "confidence": "low",
        "reasons": ["No mapped high-risk provider category or confirmed sanctions evidence was found."],
    }

def adjudicate(
    address: str,
    chain: str = "ethereum",
    provider_result: Optional[Dict[str, Any]] = None,
    local_flow_data: Optional[Dict[str, Any]] = None,
    local_graph_data: Optional[Dict[str, Any]] = None,
    policy: Optional[Policy] = None,
    own_labels: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    p = policy or DEFAULT_POLICY
    addr = address.lower()
    ch = chain.lower()

    provider = dict(provider_result or {})
    flow = local_flow_data or {}
    graph = local_graph_data or {}

    if own_labels and addr in own_labels:
        own = own_labels[addr]
        provider.update({k: v for k, v in own.items() if k in ("entity_category", "risk_score", "sanctions_hit", "risk_indicators")})

    base = _apply_full_provider_policy(provider, p)

    from .swarm import run_sonar_consensus_v1
    consensus = run_sonar_consensus_v1(
        address=addr,
        chain=ch,
        provider_result=provider,
        flow_data=flow,
        graph_data=graph,
        policy=p,
    )

    final_verdict = _merge_verdict(base, consensus)
    risk = _compute_final_risk(base, consensus)

    return {
        "subject": addr,
        "subject_type": "address",
        "chain": ch,
        "verdict": final_verdict,
        "safe": final_verdict == "CLEAR",
        "risk_score": risk,
        "risk_indicators": sorted(set(base.get("risk_indicators", []) + consensus.get("reasons", []))),
        "action": _action_for_verdict(final_verdict),
        "entity": base.get("entity") or provider.get("entity_name"),
        "consensus": consensus,
        "policy_version": p.version,
        "deterministic": True,
        "_reproducibility_hash": _hash_inputs(addr, ch, provider, flow, graph, p.version, own_labels or {}),
    }

def _apply_full_provider_policy(provider: Dict[str, Any], policy: Policy) -> Dict[str, Any]:
    prov = adjudicate_provider_result(provider, policy)
    if prov.get("recommended_verdict") == "BLOCK" or prov.get("canonical_category") == "sanctions":
        return {
            "verdict": "BLOCK",
            "risk_score": 100.0,
            "risk_indicators": ["SANCTIONS"] + prov.get("reasons", []),
            "entity": provider.get("entity_name"),
            "canonical_category": prov.get("canonical_category", "sanctions"),
        }
    rec = prov.get("recommended_verdict", "CLEAR")
    cat = prov.get("canonical_category", "unknown_low_risk")
    risk = float(provider.get("risk_score") or 0)
    if rec == "BLOCK":
        return {"verdict": "BLOCK", "risk_score": max(80, risk), "risk_indicators": [cat.upper()] + prov.get("reasons", []), "entity": provider.get("entity_name"), "canonical_category": cat}
    if rec == "CAUTION":
        return {"verdict": "CAUTION", "risk_score": max(50, risk), "risk_indicators": [cat.upper()] + prov.get("reasons", []), "entity": provider.get("entity_name"), "canonical_category": cat}
    if cat in ("unknown_high_risk", "unknown_review"):
        v = "CAUTION" if cat == "unknown_high_risk" else "UNKNOWN"
        return {"verdict": v, "risk_score": max(40 if v == "CAUTION" else 20, risk), "risk_indicators": [cat] + prov.get("reasons", []), "canonical_category": cat}
    return {"verdict": "CLEAR", "risk_score": risk or 10.0, "risk_indicators": [], "canonical_category": cat}

def _merge_verdict(base: Dict[str, Any], consensus: Dict[str, Any]) -> str:
    if base.get("verdict") == "BLOCK" or consensus.get("decision") == "BLOCK":
        return "BLOCK"
    if consensus.get("decision") in ("CAUTION", "REVIEW"):
        return "CAUTION"
    if base.get("verdict") == "CAUTION":
        return "CAUTION"
    return base.get("verdict", "CLEAR")

def _compute_final_risk(base: Dict[str, Any], consensus: Dict[str, Any]) -> float:
    return max(float(base.get("risk_score", 0)), float(consensus.get("risk_score", 0)))

def _action_for_verdict(v: str) -> str:
    mapping = {
        "BLOCK": "BLOCKED — do not transact. File SAR if required.",
        "CAUTION": "Enhanced due diligence recommended.",
        "UNKNOWN": "Insufficient data — treat as elevated risk.",
        "CLEAR": "No action required per deterministic policy.",
    }
    return mapping.get(v, "Review required.")
