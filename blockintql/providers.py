"""BlockINTQL Provider Plugin System

Backward-compatible re-exports from the new first-class deterministic core.

New recommended import for agents and power users:
    from blockintql.deterministic import adjudicate, run_sonar_consensus_v1
"""

import httpx
from abc import ABC, abstractmethod
from typing import Iterable

# Re-export the canonical deterministic core so existing code keeps working
from .deterministic.core import (
    adjudicate_provider_result,
    adjudicate,
    CANONICAL_PROVIDER_RULES as _CANONICAL,   # will be populated below
)
from .deterministic.swarm import run_sonar_consensus_v1
from .deterministic.policy import DEFAULT_POLICY

# Keep the old name working
CANONICAL_PROVIDER_RULES = _CANONICAL or [  # populated after import
    {
        "category": "sanctions",
        "recommended_verdict": "BLOCK",
        "severity": "critical",
        "label_tokens": {"sanction", "sanctions", "ofac", "sdn", "blocked"},
    },
    # ... (rest of the original list is kept in deterministic/core for now)
]


def _text_set(values: Iterable) -> set[str]:
    items = set()
    for value in values or []:
        text = str(value or "").strip().lower()
        if text:
            items.add(text)
    return items


def _nested_get(data, path, default=None):
    value = data
    for part in str(path or "").split("."):
        if not part:
            continue
        if isinstance(value, dict):
            value = value.get(part, default)
        elif isinstance(value, (list, tuple)):
            try:
                value = value[int(part)]
            except (TypeError, ValueError, IndexError):
                return default
        else:
            return default
    return value


def _collect_text_tokens(value) -> list[str]:
    tokens = []
    if isinstance(value, dict):
        for nested in value.values():
            tokens.extend(_collect_text_tokens(nested))
    elif isinstance(value, (list, tuple, set)):
        for nested in value:
            tokens.extend(_collect_text_tokens(nested))
    elif value is not None:
        text = str(value).strip()
        if text:
            tokens.append(text)
    return tokens


# The original list is now also defined in deterministic/core.py
# We keep a copy here only for extreme backward compat during the transition.
    {
        "category": "sanctions",
        "recommended_verdict": "BLOCK",
        "severity": "critical",
        "label_tokens": {"sanction", "sanctions", "ofac", "sdn", "blocked"},
    },
    {
        "category": "mixer",
        "recommended_verdict": "CAUTION",
        "severity": "high",
        "label_tokens": {"mixer", "mixing", "tumbler", "coinjoin", "tornado cash"},
    },
    {
        "category": "ransomware",
        "recommended_verdict": "BLOCK",
        "severity": "critical",
        "label_tokens": {"ransomware", "extortion"},
    },
    {
        "category": "darknet",
        "recommended_verdict": "BLOCK",
        "severity": "critical",
        "label_tokens": {"darknet", "dark market", "darknet market"},
    },
    {
        "category": "scam",
        "recommended_verdict": "BLOCK",
        "severity": "critical",
        "label_tokens": {"scam", "fraud", "phishing", "drainer", "hack", "exploit"},
    },
    {
        "category": "gambling",
        "recommended_verdict": "CAUTION",
        "severity": "medium",
        "label_tokens": {"gambling", "casino", "betting"},
    },
    {
        "category": "exchange",
        "recommended_verdict": "CLEAR",
        "severity": "low",
        "label_tokens": {"exchange", "cex"},
    },
    {
        "category": "defi",
        "recommended_verdict": "CLEAR",
        "severity": "low",
        "label_tokens": {"defi", "dex", "amm", "protocol"},
    },
    {
        "category": "bridge",
        "recommended_verdict": "CAUTION",
        "severity": "medium",
        "label_tokens": {"bridge", "cross-chain"},
    },
    {
        "category": "wallet",
        "recommended_verdict": "CLEAR",
        "severity": "low",
        "label_tokens": {"wallet", "eoa", "externally_owned_account"},
    },
]


def adjudicate_provider_result(result: dict) -> dict:
    """
    Convert vendor-native labels into BlockINTQL canonical local policy.

    This is intentionally deterministic and conservative:
    - direct sanctions hits always BLOCK
    - mapped high-risk illicit categories become BLOCK or CAUTION
    - unmapped/high-score vendor data degrades to UNKNOWN or CAUTION
    """
    indicators = _text_set(result.get("risk_indicators"))
    entity_category = str(result.get("entity_category") or "").strip().lower()
    haystack = " ".join(sorted(indicators | ({entity_category} if entity_category else set())))
    reasons = []

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
            return {
                "canonical_category": rule["category"],
                "recommended_verdict": rule["recommended_verdict"],
                "severity": rule["severity"],
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


class AttributionProvider(ABC):
    name: str = "unknown"
    description: str = ""
    def __init__(self, api_key: str):
        self.api_key = api_key
    @abstractmethod
    def get_address_risk(self, address: str, chain: str = "bitcoin") -> dict:
        pass
    def normalize(self, raw: dict) -> dict:
        return {"entity_name": None, "entity_category": None, "risk_score": 0,
                "risk_indicators": [], "sanctions_hit": False, "provider": self.name, "raw": raw,
                "vendor_verdict": None, "vendor_category": None}

    @property
    def requires_api_key(self) -> bool:
        return True


class ChainalysisProvider(AttributionProvider):
    name = "chainalysis"
    description = "Chainalysis KYT — industry standard blockchain analytics"
    def get_address_risk(self, address: str, chain: str = "bitcoin") -> dict:
        asset = {"bitcoin": "BITCOIN", "ethereum": "ETHEREUM"}.get(chain, "BITCOIN")
        try:
            r = httpx.post(f"https://api.chainalysis.com/api/kyt/v2/users/demo_user/transfers",
                headers={"Token": self.api_key, "Content-Type": "application/json"},
                json={"network": asset, "asset": asset, "transferReference": address, "direction": "received"},
                timeout=15)
            if r.status_code not in (200, 201):
                return self.normalize({"error": f"HTTP {r.status_code}"})
            data = r.json()
            risk = data.get("riskScore", "unknown")
            cluster = data.get("cluster", {})
            risk_map = {"low": 10, "medium": 50, "high": 80, "severe": 100}
            result = self.normalize(data)
            result.update({"entity_name": cluster.get("name"), "entity_category": cluster.get("category"),
                "risk_score": risk_map.get(str(risk).lower(), 0),
                "risk_indicators": data.get("exposures", []),
                "sanctions_hit": any(e.get("category") == "sanctions" for e in data.get("exposures", []))})
            return result
        except Exception as e:
            return self.normalize({"error": str(e)})


class TRMProvider(AttributionProvider):
    name = "trm"
    description = "TRM Labs — blockchain risk intelligence"
    def get_address_risk(self, address: str, chain: str = "bitcoin") -> dict:
        blockchain = {"bitcoin": "bitcoin", "ethereum": "ethereum"}.get(chain, "bitcoin")
        try:
            r = httpx.post(f"https://api.trmlabs.com/public/v2/screening/addresses",
                headers={"Authorization": f"Basic {self.api_key}", "Content-Type": "application/json"},
                json=[{"address": address, "chain": blockchain}], timeout=15)
            if r.status_code != 200:
                return self.normalize({"error": f"HTTP {r.status_code}"})
            data = r.json()
            item = data[0] if isinstance(data, list) and data else {}
            risk_details = item.get("addressRiskIndicators", [])
            risk_score = item.get("riskScore", 0)
            result = self.normalize(data)
            result.update({"entity_name": item.get("addressSummary", {}).get("name"),
                "entity_category": item.get("addressSummary", {}).get("type"),
                "risk_score": float(risk_score) * 100 if risk_score <= 1 else float(risk_score),
                "risk_indicators": [r.get("riskType") for r in risk_details if r.get("riskType")],
                "sanctions_hit": any(r.get("riskType") == "SANCTIONS" for r in risk_details)})
            return result
        except Exception as e:
            return self.normalize({"error": str(e)})


class EllipticProvider(AttributionProvider):
    name = "elliptic"
    description = "Elliptic — blockchain analytics and financial crime compliance"
    def get_address_risk(self, address: str, chain: str = "bitcoin") -> dict:
        asset = {"bitcoin": "bitcoin", "ethereum": "ethereum"}.get(chain, "bitcoin")
        try:
            r = httpx.post("https://aml-api.elliptic.co/v2/wallet/synchronous",
                headers={"x-access-key": self.api_key, "Content-Type": "application/json"},
                json={"subject": {"asset": asset, "type": "address", "hash": address}, "type": "wallet_exposure"},
                timeout=20)
            if r.status_code != 200:
                return self.normalize({"error": f"HTTP {r.status_code}"})
            data = r.json()
            risk_score = data.get("risk_score_detail", {}).get("risk_score", 0)
            result = self.normalize(data)
            result.update({"risk_score": float(risk_score) * 100 if risk_score <= 1 else float(risk_score),
                "sanctions_hit": data.get("risk_score_detail", {}).get("rule_triggered_name") == "OFAC SDN"})
            return result
        except Exception as e:
            return self.normalize({"error": str(e)})


class GenericProvider(AttributionProvider):
    """
    Generic provider — point to any REST API that returns risk data.
    
    Usage:
      blockintql screen --address 1ABC... \
        --provider generic \
        --provider-key $API_KEY \
        --provider-url https://api.yourprovider.com/screen/{address} \
        --provider-field risk_score
    """
    name = "generic"
    description = "Generic — any REST API that returns risk data"

    def __init__(self, api_key: str, url_template: str = None,
                 risk_field: str = "risk_score",
                 entity_field: str = "entity",
                 auth_header: str = "Authorization",
                 auth_prefix: str = "Bearer"):
        self.api_key = api_key
        self.url_template = url_template
        self.risk_field = risk_field
        self.entity_field = entity_field
        self.auth_header = auth_header
        self.auth_prefix = auth_prefix

    @property
    def requires_api_key(self) -> bool:
        return False

    def get_address_risk(self, address: str, chain: str = "bitcoin") -> dict:
        if not self.url_template:
            return self.normalize({"error": "No --provider-url specified"})
        try:
            url = self.url_template.replace("{address}", address).replace("{chain}", chain)
            r = httpx.get(url,
                headers={self.auth_header: f"{self.auth_prefix} {self.api_key}".strip()},
                timeout=15)
            if r.status_code != 200:
                return self.normalize({"error": f"HTTP {r.status_code}"})
            data = r.json()
            # Try to extract risk score from nested path e.g. "result.risk.score"
            risk_score = 0
            val = _nested_get(data, self.risk_field, 0)
            try:
                risk_score = float(val)
                if risk_score <= 1:
                    risk_score *= 100
            except Exception:
                pass
            if risk_score == 0:
                alt_risk = (
                    _nested_get(data, "riskScore")
                    or _nested_get(data, "risk_score")
                    or _nested_get(data, "score")
                )
                try:
                    risk_score = float(alt_risk or 0)
                    if risk_score <= 1:
                        risk_score *= 100
                except Exception:
                    pass

            # Extract entity value and common category fields
            entity_val = _nested_get(data, self.entity_field)
            entity_category = (
                _nested_get(data, "entity_category")
                or _nested_get(data, "entityCategory")
                or _nested_get(data, "category")
                or _nested_get(data, "type")
                or _nested_get(data, "classification")
                or _nested_get(data, "entity.type")
            )

            # Collect common risk / labeling signals from custom provider payloads.
            common_signal_fields = [
                "risk_indicators",
                "labels",
                "tags",
                "signals",
                "findings",
                "reasons",
                "reason",
                "category",
                "status",
                "verdict",
                "disposition",
                "classification",
                "entity_category",
                "entityCategory",
                "label",
                "crimeTypes",
                "reports",
                "riskLevel",
                "title",
            ]
            signal_tokens = []
            for field in common_signal_fields:
                signal_tokens.extend(_collect_text_tokens(_nested_get(data, field)))
            if entity_val:
                signal_tokens.append(str(entity_val))
            if entity_category:
                signal_tokens.append(str(entity_category))
            normalized_signals = sorted(_text_set(signal_tokens))

            haystack = " ".join(normalized_signals)
            sanctions_hit = any(token in haystack for token in ("sanction", "ofac", "sdn", "blocked"))

            vendor_verdict = (
                _nested_get(data, "verdict")
                or _nested_get(data, "riskLevel")
                or _nested_get(data, "status")
                or _nested_get(data, "disposition")
                or _nested_get(data, "result")
            )
            vendor_category = (
                entity_category
                or _nested_get(data, "label")
                or _nested_get(data, "classification")
                or _nested_get(data, "crimeTypes.0")
                or _nested_get(data, "reports.0.crimeType")
            )

            # Infer a conservative score when the custom provider gives a label/verdict but not a score.
            if risk_score == 0:
                if any(token in haystack for token in ("exploit", "hack", "drainer", "phishing", "scam", "fraud", "ransomware", "malicious")):
                    risk_score = 95
                elif any(token in haystack for token in ("sanction", "ofac", "sdn", "blocked")):
                    risk_score = 100
                elif any(token in haystack for token in ("warning", "suspicious", "review", "caution", "high_risk", "high risk")):
                    risk_score = 65

            result = self.normalize(data)
            result.update({
                "entity_name": str(entity_val) if entity_val else None,
                "entity_category": str(entity_category) if entity_category else None,
                "risk_score": risk_score,
                "risk_indicators": normalized_signals,
                "sanctions_hit": sanctions_hit,
                "vendor_verdict": str(vendor_verdict) if vendor_verdict else None,
                "vendor_category": str(vendor_category) if vendor_category else None,
            })
            return result
        except Exception as e:
            return self.normalize({"error": str(e)})


class MetaSleuthProvider(GenericProvider):
    name = "metasleuth"
    description = "MetaSleuth — visual fund tracing and entity intelligence"


class CrystalProvider(GenericProvider):
    name = "crystal"
    description = "Crystal — blockchain intelligence and compliance analytics"


class MerkleScienceProvider(GenericProvider):
    name = "merkle_science"
    description = "Merkle Science — transaction monitoring and blockchain forensics"


class NomisProvider(GenericProvider):
    name = "nomis"
    description = "Nomis — wallet reputation and onchain scoring"


# Add generic to registry
PROVIDERS = {
    "chainalysis": ChainalysisProvider,
    "trm": TRMProvider,
    "elliptic": EllipticProvider,
    "metasleuth": MetaSleuthProvider,
    "crystal": CrystalProvider,
    "merkle_science": MerkleScienceProvider,
    "nomis": NomisProvider,
    "generic": GenericProvider,
}

# Optional provider metadata map used by CLI route hints.
# Keep default empty so provider lookup never hard-fails if specs are not bundled.
PROVIDER_SPECS = {}


def get_provider(name: str, api_key: str = "", **kwargs):
    cls = PROVIDERS.get(name.lower())
    return cls(api_key, **kwargs) if cls else None


def list_providers() -> list:
    items = [{"name": k, "description": v.description} for k, v in PROVIDERS.items()]
    return [
        {
            "name": "blockintai",
            "description": "BlockINTAI — local custom screening route with first-class CLI defaults",
        },
        *items,
    ]


def get_provider_spec(name: str):
    if not name:
        return None
    return PROVIDER_SPECS.get(str(name).strip().lower())

# ── PRIVACY GUARANTEE ─────────────────────────────────────────────────────────
#
# Provider API calls are made DIRECTLY from this CLI on the user's machine.
# Provider keys and raw responses NEVER touch BlockINTQL servers.
# BlockINTQL only receives: address, chain, and the final merged verdict.
#
# You can verify this by reading the source code above.
# The BlockINTQL API endpoint called is /v1/verdict or /v1/screen —
# neither endpoint accepts or logs provider keys.
#
# Open source. Verify yourself: github.com/block6iq/blockintql-cli
