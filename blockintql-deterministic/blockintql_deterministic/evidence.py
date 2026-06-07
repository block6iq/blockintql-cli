"""Evidence bundles (lightweight standalone)."""
from __future__ import annotations
import json, hashlib, time, hmac
from dataclasses import dataclass, asdict, field
from typing import Any, Dict, Optional

@dataclass
class EvidenceBundle:
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
    signature: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def canonical_json(self) -> str:
        d = self.to_dict()
        d.pop("signature", None)
        return json.dumps(d, sort_keys=True, separators=(",", ":"))

    @property
    def bundle_hash(self) -> str:
        return hashlib.sha256(self.canonical_json().encode()).hexdigest()

def export_evidence_bundle(subject: str, chain: str, policy: Any, provider_result: Dict[str, Any],
                           consensus: Dict[str, Any], final_verdict: Dict[str, Any],
                           local_inputs: Optional[Dict[str, Any]] = None, secret: Optional[bytes] = None) -> EvidenceBundle:
    ts = time.time()
    inputs = {"address": subject, "chain": chain, "local_data": local_inputs or {}}
    repro = hashlib.sha256(json.dumps([subject, chain, getattr(policy, "hash", ""), provider_result, consensus, final_verdict], sort_keys=True, default=str).encode()).hexdigest()[:16]
    pm = consensus.get("policy_mapping", {"vendor_to_canonical": {}, "block_basis": []})
    ew = consensus.get("evidence_window", {"lookback_days": 30, "hop_depth": 0, "chains": [chain]})
    b = EvidenceBundle(subject=subject, chain=chain, policy_version=getattr(policy, "version", "policy-v1"),
                       policy_hash=getattr(policy, "hash", ""), inputs=inputs, provider_result=provider_result,
                       consensus=consensus, final_verdict=final_verdict, timestamp=ts, reproducibility_hash=repro,
                       policy_mapping=pm, evidence_window=ew)
    if secret:
        b.signature = hmac.new(secret, b.canonical_json().encode(), hashlib.sha256).hexdigest()
    return b

def verify_evidence_bundle(bundle: EvidenceBundle, expected_policy_hash: Optional[str] = None, secret: Optional[bytes] = None) -> bool:
    if expected_policy_hash and bundle.policy_hash != expected_policy_hash: return False
    recomputed = hashlib.sha256(json.dumps([bundle.subject, bundle.chain, bundle.policy_hash, bundle.provider_result, bundle.consensus, bundle.final_verdict], sort_keys=True, default=str).encode()).hexdigest()[:16]
    if recomputed != bundle.reproducibility_hash: return False
    if secret and bundle.signature:
        expected = hmac.new(secret, bundle.canonical_json().encode(), hashlib.sha256).hexdigest()
        if expected != bundle.signature: return False
    return True
