"""
BlockINTQL Deterministic Core

This is the open-source, auditable heart of BlockINTQL-style screening.

Goal: Make high-quality, reproducible, agent-friendly deterministic compliance
reasoning available to everyone, independent of any particular data vendor.

Key exports:
- adjudicate: main entry point (wraps provider results + optional local data)
- sonar_consensus_v1: the 3-agent swarm (Sentinel, Cypher, Nova)
- EvidenceBundle: reproducible signed artifacts
- Policy: custom rule sets that still produce sonar_consensus_v1 shape

All logic here is pure, deterministic, and versioned.
"""

from .core import (
    adjudicate,
    adjudicate_provider_result,
)
from .core import CANONICAL_PROVIDER_RULES  # re-export for convenience
from .swarm import (
    run_sonar_consensus_v1,
    Sentinel,
    Cypher,
    Nova,
)
from .policy import (
    Policy,
    load_policy,
    DEFAULT_POLICY,
)
from .evidence import (
    EvidenceBundle,
    export_evidence_bundle,
    verify_evidence_bundle,
)

__all__ = [
    "adjudicate",
    "adjudicate_provider_result",
    "CANONICAL_PROVIDER_RULES",
    "run_sonar_consensus_v1",
    "Sentinel",
    "Cypher",
    "Nova",
    "Policy",
    "load_policy",
    "DEFAULT_POLICY",
    "EvidenceBundle",
    "export_evidence_bundle",
    "verify_evidence_bundle",
]

__version__ = "0.1.1"  # Standalone blockintql-deterministic version (kept in sync)
