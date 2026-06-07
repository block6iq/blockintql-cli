"""
blockintql-deterministic

First-class, versioned, pure-Python deterministic screening core + sonar_consensus_v1
3-agent swarm (Sentinel / Cypher / Nova) for agentic on-chain compliance.

This is the open standard / reusable library part of the blockintql-cli OSS project.
Install independently: pip install blockintql-deterministic

See docs in the main repo for the full open standard guide and how to implement
sonar_consensus_v1 yourself.

Primary API:
    from blockintql_deterministic import adjudicate, run_sonar_consensus_v1, export_evidence_bundle, Policy, load_policy

All logic is deterministic, auditable, and works with zero external services when
you supply your own data (provider results, flow events, graph data, own labels).
"""

from .core import (
    adjudicate,
    adjudicate_provider_result,
    CANONICAL_PROVIDER_RULES,
)
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

__version__ = "0.1.0"
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
