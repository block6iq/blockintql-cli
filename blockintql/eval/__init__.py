"""
Serious (but lightweight) evaluation framework for the open-source deterministic core.

This lets anyone measure:
- Consistency (must be 100%)
- Behavior under different provider "personalities"
- Impact of custom policies
- False-positive / coverage characteristics on synthetic or real traces

The goal is to make the reasoning layer auditable and improvable by the community.
"""

from __future__ import annotations

from typing import Any, Dict, List
from ..deterministic import adjudicate, Policy


SYNTHETIC_CASES: List[Dict[str, Any]] = [
    {"name": "direct_sanctions", "address": "0xsanctioned", "provider": {"sanctions_hit": True}, "expect": "BLOCK"},
    {"name": "high_risk_unmapped", "address": "0xhigh", "provider": {"risk_score": 91}, "expect": "CAUTION"},
    {"name": "clean_exchange", "address": "0xexchange", "provider": {"entity_category": "exchange", "risk_score": 5}, "expect": "CLEAR"},
    {"name": "mixer_label", "address": "0xmixed", "provider": {"entity_category": "mixer"}, "expect": "CAUTION"},
]

# Public test case fixture (from the spec, for OSS compatibility testing)
PUBLIC_TEST_FIXTURE = [
    {"address": "0x0000000000000000000000000000000000000000", "provider": {"sanctions_hit": True}, "expected": "BLOCK", "rationale": "Direct sanctions per spec §5.1"},
    {"address": "0x1111111111111111111111111111111111111111", "provider": {"risk_score": 95, "entity_category": "unknown"}, "expected": "CAUTION", "rationale": "Unmapped high risk per spec §5.2"},
    {"address": "0x2222222222222222222222222222222222222222", "provider": {"entity_category": "exchange"}, "expected": "CLEAR", "rationale": "Low risk canonical per rules"},
]

SYNTHETIC_CASES.extend([
    {"name": f"public_fixture_{i}", "address": case["address"], "provider": case["provider"], "expect": case["expected"]} 
    for i, case in enumerate(PUBLIC_TEST_FIXTURE)
])


def run_case(case: Dict[str, Any]) -> Dict[str, Any]:
    res = adjudicate(case["address"], provider_result=case.get("provider"), policy=case.get("policy"))
    return {
        "name": case["name"],
        "verdict": res["verdict"],
        "risk_score": res["risk_score"],
        "expected": case.get("expect"),
        "match": res["verdict"] == case.get("expect"),
        "swarm": {v["agent"]: v["vote"] for v in res["consensus"]["votes"]},
    }


def run_suite(cases: List[Dict[str, Any]] | None = None) -> Dict[str, Any]:
    cases = cases or SYNTHETIC_CASES
    results = [run_case(c) for c in cases]
    passed = sum(1 for r in results if r["match"])
    return {
        "total": len(results),
        "passed": passed,
        "accuracy": passed / len(results) if results else 0,
        "results": results,
    }


def consistency_check(addresses: List[str], runs: int = 5) -> Dict[str, Any]:
    """Deterministic logic must be perfectly consistent."""
    out = []
    for addr in addresses:
        verdicts = [adjudicate(addr)["verdict"] for _ in range(runs)]
        out.append({"address": addr, "verdicts": verdicts, "consistent": len(set(verdicts)) == 1})
    return {"all_consistent": all(x["consistent"] for x in out), "cases": out}


def policy_impact_test(base_policy: Policy, custom_policy: Policy, addresses: List[str]) -> Dict[str, Any]:
    """Measure how a custom policy changes outcomes vs the default."""
    deltas = []
    for addr in addresses:
        base = adjudicate(addr, policy=base_policy)["verdict"]
        cust = adjudicate(addr, policy=custom_policy)["verdict"]
        deltas.append({"address": addr, "base": base, "custom": cust, "changed": base != cust})
    changed = sum(1 for d in deltas if d["changed"])
    return {"changed_count": changed, "deltas": deltas}


# --- Provider ablation examples (expand harness) ---
def provider_ablation(addresses: List[str], providers: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Ablation: how do different provider 'personalities' affect the deterministic outcome?
    Pass list of mock provider results.
    """
    results = []
    for prov in providers:
        for addr in addresses:
            res = adjudicate(addr, provider_result=prov)
            results.append({
                "provider": prov.get("entity_category", "unknown"),
                "address": addr,
                "verdict": res["verdict"],
                "risk": res["risk_score"],
            })
    return {"ablations": results, "summary": "Run with real provider outputs to measure sensitivity."}


# Small public test case fixture (synthetic but documented for OSS)
PUBLIC_TEST_FIXTURE = [
    {"address": "0x0000000000000000000000000000000000000000", "provider": {"sanctions_hit": True}, "expected": "BLOCK", "rationale": "Direct sanctions per spec §5.1"},
    {"address": "0x1111111111111111111111111111111111111111", "provider": {"risk_score": 95, "entity_category": "unknown"}, "expected": "CAUTION", "rationale": "Unmapped high risk per spec §5.2"},
    {"address": "0x2222222222222222222222222222222222222222", "provider": {"entity_category": "exchange"}, "expected": "CLEAR", "rationale": "Low risk canonical per rules"},
]
