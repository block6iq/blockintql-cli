"""
Evidence bundles — the audit/export story that regulated entities actually need.

Produces a signed/hashable, reproducible artifact containing:
- exact policy version + hash
- normalized inputs + raw provider responses (allowlisted)
- full swarm votes + per-agent rationale
- final decision + risk
- reproducibility hash

This is what `blockintql deterministic export-evidence` and agents should emit.
"""

from __future__ import annotations

import json
import hashlib
import time
import hmac
from dataclasses import dataclass, asdict, field
from typing import Any, Dict, Optional, List


@dataclass
class EvidenceBundle:
    """Complete, reproducible, auditable artifact matching deterministic-screening-spec-v1."""
    subject: str
    chain: str
    subject_type: str = "address"
    policy_version: str = "policy-v1"
    policy_hash: str = ""
    inputs: Dict[str, Any] = field(default_factory=dict)
    provider_result: Dict[str, Any] = field(default_factory=dict)
    consensus: Dict[str, Any] = field(default_factory=dict)
    final_verdict: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0
    reproducibility_hash: str = ""
    policy_mapping: Dict[str, Any] = field(default_factory=dict)
    evidence_window: Dict[str, Any] = field(default_factory=dict)
    signature: Optional[str] = None           # HMAC or external detached sig (e.g. for provenance)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def canonical_json(self) -> str:
        """Deterministic serialization for hashing/signing (no signature field)."""
        d = self.to_dict()
        d.pop("signature", None)
        return json.dumps(d, sort_keys=True, separators=(",", ":"))

    @property
    def bundle_hash(self) -> str:
        return hashlib.sha256(self.canonical_json().encode()).hexdigest()


def export_evidence_bundle(
    subject: str,
    chain: str,
    policy: Any,
    provider_result: Dict[str, Any],
    consensus: Dict[str, Any],
    final_verdict: Dict[str, Any],
    local_inputs: Optional[Dict[str, Any]] = None,
    secret: Optional[bytes] = None,   # optional HMAC secret for simple signing
) -> EvidenceBundle:
    """
    Build a full evidence bundle.

    Callers (CLI, agents, notebooks) should pass whatever local data they used.
    The resulting bundle is the canonical artifact for audit/SAR/defensibility.
    """
    ts = time.time()
    inputs = {
        "address": subject,
        "chain": chain,
        "local_data": local_inputs or {},
    }

    # Include key parts of provider + swarm for full audit trail
    repro_material = [subject, chain, getattr(policy, "hash", ""), provider_result, consensus, final_verdict]
    repro_hash = hashlib.sha256(json.dumps(repro_material, sort_keys=True, default=str).encode()).hexdigest()[:16]

    policy_mapping = consensus.get("policy_mapping", {
        "vendor_to_canonical": {},
        "block_basis": [v.get("agent") for v in consensus.get("votes", []) if v.get("vote") == "BLOCK"],
    })
    evidence_window = consensus.get("evidence_window", {
        "lookback_days": 30,
        "hop_depth": 0,
        "chains": [chain],
    })

    bundle = EvidenceBundle(
        subject=subject,
        chain=chain,
        policy_version=getattr(policy, "version", "policy-v1"),
        policy_hash=getattr(policy, "hash", ""),
        inputs=inputs,
        provider_result=provider_result,
        consensus=consensus,
        final_verdict=final_verdict,
        timestamp=ts,
        reproducibility_hash=repro_hash,
        policy_mapping=policy_mapping,
        evidence_window=evidence_window,
    )

    if secret:
        bundle.signature = hmac.new(secret, bundle.canonical_json().encode(), hashlib.sha256).hexdigest()

    return bundle


def verify_evidence_bundle(bundle: EvidenceBundle, expected_policy_hash: Optional[str] = None, secret: Optional[bytes] = None) -> bool:
    """Verify internal consistency and optional signature."""
    if expected_policy_hash and bundle.policy_hash != expected_policy_hash:
        return False

    recomputed = hashlib.sha256(
        json.dumps([bundle.subject, bundle.chain, bundle.policy_hash, bundle.provider_result, bundle.consensus, bundle.final_verdict], sort_keys=True, default=str).encode()
    ).hexdigest()[:16]

    if recomputed != bundle.reproducibility_hash:
        return False

    if secret and bundle.signature:
        expected_sig = hmac.new(secret, bundle.canonical_json().encode(), hashlib.sha256).hexdigest()
        if expected_sig != bundle.signature:
            return False

    return True
