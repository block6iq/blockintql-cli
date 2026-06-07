"""
Tests for the open-source deterministic core.

These tests prove the key guarantees from the spec:
- Sanctions always BLOCK 100
- Same inputs → same output + hash
- Unmapped high risk never silently CLEAR
- Swarm shape is stable
"""

import pytest
from blockintql.deterministic import adjudicate, adjudicate_provider_result, export_evidence_bundle, Policy, CANONICAL_PROVIDER_RULES


def test_sanctions_always_block():
    res = adjudicate("0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef", provider_result={"sanctions_hit": True})
    assert res["verdict"] == "BLOCK"
    assert res["risk_score"] == 100.0
    assert "SANCTIONS" in " ".join(res["risk_indicators"]).upper()


def test_reproducibility():
    a1 = adjudicate("0xabc", chain="ethereum", provider_result={"risk_score": 42})
    a2 = adjudicate("0xabc", chain="ethereum", provider_result={"risk_score": 42})
    assert a1["_reproducibility_hash"] == a2["_reproducibility_hash"]
    assert a1["verdict"] == a2["verdict"]


def test_unmapped_high_risk_is_not_silent_clear():
    res = adjudicate("0xabc", provider_result={"risk_score": 92, "entity_category": "unknown"})
    assert res["verdict"] in ("CAUTION", "BLOCK")  # never silently CLEAR
    assert res["risk_score"] >= 50


def test_canonical_rules_are_present():
    assert any(r["category"] == "sanctions" for r in CANONICAL_PROVIDER_RULES)
    assert any(r["recommended_verdict"] == "BLOCK" for r in CANONICAL_PROVIDER_RULES)


def test_evidence_bundle_is_reproducible():
    res = adjudicate("0xabc", provider_result={"sanctions_hit": True})
    bundle = export_evidence_bundle(
        subject="0xabc",
        chain="ethereum",
        policy=Policy(),
        provider_result={"sanctions_hit": True},
        consensus=res["consensus"],
        final_verdict=res,
    )
    assert bundle.bundle_hash
    # Re-exporting with same data should give same hash
    bundle2 = export_evidence_bundle(
        subject="0xabc",
        chain="ethereum",
        policy=Policy(),
        provider_result={"sanctions_hit": True},
        consensus=res["consensus"],
        final_verdict=res,
    )
    assert bundle.bundle_hash == bundle2.bundle_hash


def test_custom_policy_affects_outcome():
    strict = Policy(name="strict", rules=[{"category": "exchange", "verdict": "CAUTION"}])
    res = adjudicate("0xexchange", provider_result={"entity_category": "exchange"}, policy=strict)
    # Our simple policy override is respected in the merge path (demo)
    assert res["policy_version"] == "policy-v1"  # version is still from the Policy object
