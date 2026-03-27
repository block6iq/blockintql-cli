"""BlockINTQL Provider Plugin System"""

import httpx
from abc import ABC, abstractmethod


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
                "risk_indicators": [], "sanctions_hit": False, "provider": self.name, "raw": raw}


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


class ArkhamProvider(AttributionProvider):
    name = "arkham"
    description = "Arkham Intelligence — entity intelligence platform"
    def get_address_risk(self, address: str, chain: str = "bitcoin") -> dict:
        try:
            r = httpx.get(f"https://api.arkhamintelligence.com/intelligence/address/{address}",
                headers={"API-Key": self.api_key}, timeout=15)
            if r.status_code != 200:
                return self.normalize({"error": f"HTTP {r.status_code}"})
            data = r.json()
            entity = data.get("arkhamEntity", {})
            entity_type = entity.get("type", "")
            risk_map = {"exchange": 10, "defi": 15, "mixer": 90, "sanctions": 100, "scam": 95, "hack": 95, "darknet": 90}
            result = self.normalize(data)
            result.update({"entity_name": entity.get("name"), "entity_category": entity_type,
                "risk_score": risk_map.get(entity_type.lower(), 20),
                "sanctions_hit": entity_type.lower() == "sanctions"})
            return result
        except Exception as e:
            return self.normalize({"error": str(e)})


class MetaMaskRiskProvider(AttributionProvider):
    name = "metamask"
    description = "MetaMask Transaction Insight — free, no API key needed"
    def __init__(self, api_key: str = ""):
        self.api_key = api_key
    def get_address_risk(self, address: str, chain: str = "ethereum") -> dict:
        if chain != "ethereum":
            return self.normalize({"error": "MetaMask only supports Ethereum"})
        try:
            r = httpx.get(f"https://risk-api.metamask.io/v1/chains/1/addresses/{address}", timeout=10)
            if r.status_code != 200:
                return self.normalize({"error": f"HTTP {r.status_code}"})
            data = r.json()
            risk_score = 90 if data.get("result") == "Malicious" else 50 if data.get("result") == "Warning" else 0
            indicators = ["FLAGGED_MALICIOUS"] if risk_score == 90 else ["WARNING"] if risk_score == 50 else []
            result = self.normalize(data)
            result.update({"risk_score": risk_score, "risk_indicators": indicators})
            return result
        except Exception as e:
            return self.normalize({"error": str(e)})


PROVIDERS = {
    "chainalysis": ChainalysisProvider,
    "trm": TRMProvider,
    "elliptic": EllipticProvider,
    "arkham": ArkhamProvider,
    "metamask": MetaMaskRiskProvider,
}

def get_provider(name: str, api_key: str):
    cls = PROVIDERS.get(name.lower())
    return cls(api_key) if cls else None

def list_providers() -> list:
    return [{"name": k, "description": v.description} for k, v in PROVIDERS.items()]


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
            parts = self.risk_field.split(".")
            val = data
            for p in parts:
                val = val.get(p, 0) if isinstance(val, dict) else 0
            try:
                risk_score = float(val)
                if risk_score <= 1:
                    risk_score *= 100
            except:
                pass
            # Extract entity name
            entity_val = data
            for p in self.entity_field.split("."):
                entity_val = entity_val.get(p) if isinstance(entity_val, dict) else None
            result = self.normalize(data)
            result.update({"entity_name": str(entity_val) if entity_val else None,
                "risk_score": risk_score})
            return result
        except Exception as e:
            return self.normalize({"error": str(e)})


# Add generic to registry
PROVIDERS["generic"] = GenericProvider

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
