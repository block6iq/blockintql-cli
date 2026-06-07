"""
Policy system — first-class support for custom deterministic rule sets.

Organizations can maintain their own policies that still produce the
`sonar_consensus_v1` output shape. This is critical for auditability
and for making the OSS useful beyond a single vendor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import json
import hashlib


@dataclass
class Policy:
    """A versioned, serializable deterministic policy."""
    version: str = "policy-v1"
    name: str = "default"
    rules: List[Dict[str, Any]] = field(default_factory=list)
    sanctions_override: bool = True
    conservative_unknown: bool = True
    # Future: custom category mappings, custom aggregation weights, etc.

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "name": self.name,
            "rules": self.rules,
            "sanctions_override": self.sanctions_override,
            "conservative_unknown": self.conservative_unknown,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Policy":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    @property
    def hash(self) -> str:
        blob = json.dumps(self.to_dict(), sort_keys=True).encode()
        return hashlib.sha256(blob).hexdigest()[:16]


# The default policy mirrors the spirit of the original CANONICAL rules.
DEFAULT_POLICY = Policy(
    version="policy-v1",
    name="blockintql-default-v1",
    rules=[
        {"category": "sanctions", "verdict": "BLOCK", "severity": "critical"},
        {"category": "mixer", "verdict": "CAUTION", "severity": "high"},
        {"category": "ransomware", "verdict": "BLOCK", "severity": "critical"},
        {"category": "darknet", "verdict": "BLOCK", "severity": "critical"},
        {"category": "scam", "verdict": "BLOCK", "severity": "critical"},
        {"category": "fraud", "verdict": "BLOCK", "severity": "critical"},
        {"category": "exchange", "verdict": "CLEAR", "severity": "low"},
        {"category": "defi", "verdict": "CLEAR", "severity": "low"},
    ],
)


def load_policy(path_or_dict: str | Dict[str, Any]) -> Policy:
    """
    Load a policy from a file path (json/yaml) or a dict.

    This is the hook for organizations that want their own rule sets
    while still emitting the standard sonar_consensus_v1 shape.
    """
    if isinstance(path_or_dict, dict):
        return Policy.from_dict(path_or_dict)

    with open(path_or_dict, "r", encoding="utf-8") as f:
        data = json.load(f)
    return Policy.from_dict(data)
