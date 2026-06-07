"""Policy support (lightweight standalone)."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List
import json, hashlib

@dataclass
class Policy:
    version: str = "policy-v1"
    name: str = "default"
    rules: List[Dict[str, Any]] = field(default_factory=list)
    sanctions_override: bool = True
    conservative_unknown: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {"version": self.version, "name": self.name, "rules": self.rules, "sanctions_override": self.sanctions_override, "conservative_unknown": self.conservative_unknown}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Policy":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    @property
    def hash(self) -> str:
        return hashlib.sha256(json.dumps(self.to_dict(), sort_keys=True).encode()).hexdigest()[:16]

DEFAULT_POLICY = Policy(name="blockintql-default-v1", rules=[{"category": "sanctions", "verdict": "BLOCK"}, {"category": "mixer", "verdict": "CAUTION"}])

def load_policy(path_or_dict: str | Dict[str, Any]) -> Policy:
    if isinstance(path_or_dict, dict):
        return Policy.from_dict(path_or_dict)
    with open(path_or_dict, "r", encoding="utf-8") as f:
        return Policy.from_dict(json.load(f))
