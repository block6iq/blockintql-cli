from dataclasses import dataclass
import os
import re
from typing import Any, Dict, Mapping, Optional


class PaymentError(Exception):
    code = "payment_error"

    def __init__(self, message: str, *, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        payload = {"error": self.message, "code": self.code}
        if self.details:
            payload["payment"] = self.details
        return payload


class PaymentConfigurationError(PaymentError):
    code = "payment_configuration_error"


class PaymentPolicyError(PaymentError):
    code = "payment_policy_denied"


class PaymentAuthorizationError(PaymentError):
    code = "payment_authorization_error"


@dataclass
class PaymentConfig:
    wallet_type: str
    auto_pay: bool
    max_payment_usd: float
    cdp_key_id: Optional[str] = None
    private_key_env: str = "BLOCKINTQL_PRIVATE_KEY"


def load_payment_config(config: Optional[Mapping[str, Any]] = None) -> Optional[PaymentConfig]:
    payment = dict((config or {}).get("payment") or {})
    if not payment:
        return None
    wallet_type = str(payment.get("type") or "cdp")
    auto_pay = bool(payment.get("auto_pay"))
    try:
        max_payment_usd = float(payment.get("max_payment_usd", 0))
    except (TypeError, ValueError):
        max_payment_usd = 0.0
    return PaymentConfig(
        wallet_type=wallet_type,
        auto_pay=auto_pay,
        max_payment_usd=max_payment_usd,
        cdp_key_id=payment.get("cdp_key_id"),
        private_key_env=payment.get("private_key_env") or "BLOCKINTQL_PRIVATE_KEY",
    )


def parse_price_to_usd(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)", str(value))
    if not match:
        return None
    return float(match.group(1))


def extract_payment_requirement(challenge: Any) -> Dict[str, Any]:
    if not isinstance(challenge, dict):
        return {}
    accepts = challenge.get("accepts")
    if isinstance(accepts, list) and accepts:
        first = accepts[0]
        if isinstance(first, dict):
            return first
    return {}


def build_payment_details(config: PaymentConfig, challenge: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    requirement = extract_payment_requirement(challenge or {})
    details = {
        "wallet_type": config.wallet_type,
        "auto_pay": config.auto_pay,
        "max_payment_usd": config.max_payment_usd,
    }
    if requirement:
        details["requirement"] = requirement
        price_usd = parse_price_to_usd(requirement.get("price"))
        if price_usd is not None:
            details["price_usd"] = price_usd
    return details


def ensure_wallet_runtime_ready(config: PaymentConfig, environ: Optional[Mapping[str, str]] = None) -> None:
    env = environ or os.environ
    if config.wallet_type == "cdp":
        if not (env.get("BLOCKINTQL_CDP_PRIVATE_KEY") or env.get("BLOCKINTQL_PRIVATE_KEY") or env.get("EVM_PRIVATE_KEY")):
            raise PaymentConfigurationError(
                "CDP wallet private key is not available in the environment.",
                details=build_payment_details(config),
            )
        key_validation = validate_evm_private_key(get_evm_private_key(config, env))
        if not key_validation.get("ok"):
            details = build_payment_details(config)
            details["reason"] = key_validation.get("reason")
            if "length" in key_validation:
                details["length"] = key_validation["length"]
            raise PaymentConfigurationError(
                "CDP wallet key is present but format is invalid.",
                details=details,
            )
        return
    if config.wallet_type == "privatekey":
        if not (env.get(config.private_key_env) or env.get("EVM_PRIVATE_KEY")):
            raise PaymentConfigurationError(
                "Private-key wallet is not fully configured.",
                details=build_payment_details(config),
            )
        key_validation = validate_evm_private_key(get_evm_private_key(config, env))
        if not key_validation.get("ok"):
            details = build_payment_details(config)
            details["reason"] = key_validation.get("reason")
            if "length" in key_validation:
                details["length"] = key_validation["length"]
            raise PaymentConfigurationError(
                "Private-key wallet is configured but key format is invalid.",
                details=details,
            )
        return
    raise PaymentConfigurationError(
        f"Unsupported wallet type: {config.wallet_type}",
        details=build_payment_details(config),
    )


def enforce_payment_policy(config: PaymentConfig, challenge: Dict[str, Any]) -> Dict[str, Any]:
    details = build_payment_details(config, challenge)
    if not config.auto_pay:
        raise PaymentPolicyError(
            "Auto-pay is disabled for wallet-backed payments.",
            details=details,
        )
    price_usd = details.get("price_usd")
    if price_usd is not None and config.max_payment_usd and price_usd > config.max_payment_usd:
        raise PaymentPolicyError(
            "Payment amount exceeds the configured maximum.",
            details=details,
        )
    return details


def get_evm_private_key(config: PaymentConfig, environ: Optional[Mapping[str, str]] = None) -> Optional[str]:
    env = environ or os.environ
    candidates = []
    if config.wallet_type == "privatekey":
        candidates.extend([config.private_key_env, "EVM_PRIVATE_KEY"])
    elif config.wallet_type == "cdp":
        candidates.extend(["BLOCKINTQL_PRIVATE_KEY", "EVM_PRIVATE_KEY", "BLOCKINTQL_CDP_PRIVATE_KEY"])
    else:
        candidates.extend([config.private_key_env, "EVM_PRIVATE_KEY"])
    for name in candidates:
        value = env.get(name)
        if value:
            return value if value.startswith("0x") else f"0x{value}"
    return None


def validate_evm_private_key(value: Optional[str]) -> Dict[str, Any]:
    normalized = str(value or "").strip()
    if not normalized:
        return {"ok": False, "reason": "missing"}
    if not normalized.startswith("0x"):
        normalized = f"0x{normalized}"
    if len(normalized) != 66:
        return {"ok": False, "reason": "invalid_length", "length": len(normalized)}
    if not re.fullmatch(r"0x[0-9a-fA-F]{64}", normalized):
        return {"ok": False, "reason": "non_hex_characters"}
    return {"ok": True, "value": normalized}
