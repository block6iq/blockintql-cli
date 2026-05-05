import asyncio
import sys
from typing import Any, Dict, Optional

from .payments import PaymentConfigurationError, PaymentError, PaymentConfig, get_evm_private_key


def _import_x402_modules():
    if sys.version_info < (3, 10):
        raise PaymentConfigurationError(
            "True x402 client support requires Python 3.10 or newer.",
            details={"runtime": f"{sys.version_info.major}.{sys.version_info.minor}"},
        )
    try:
        from eth_account import Account
        from x402 import x402Client
        from x402.http import x402HTTPClient
        from x402.http.clients import x402HttpxClient
        from x402.mechanisms.evm import EthAccountSigner
        from x402.mechanisms.evm.exact.register import register_exact_evm_client
    except ImportError as exc:
        raise PaymentConfigurationError(
            "True x402 client support requires the official x402 and eth-account packages.",
            details={"missing_dependency": str(exc)},
        ) from exc
    return Account, x402Client, x402HTTPClient, x402HttpxClient, EthAccountSigner, register_exact_evm_client


def request_with_x402(
    method: str,
    url: str,
    *,
    payment_config: PaymentConfig,
    params: Optional[Dict[str, Any]] = None,
    body: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: Optional[float] = None,
) -> Dict[str, Any]:
    Account, x402Client, x402HTTPClient, x402HttpxClient, EthAccountSigner, register_exact_evm_client = _import_x402_modules()
    private_key = get_evm_private_key(payment_config)
    if not private_key:
        raise PaymentConfigurationError(
            "Wallet-backed x402 payments require an EVM private key in the environment.",
            details={"wallet_type": payment_config.wallet_type},
        )

    async def _run() -> Dict[str, Any]:
        client = x402Client()
        account = Account.from_key(private_key)
        register_exact_evm_client(client, EthAccountSigner(account))
        http_client = x402HTTPClient(client)

        client_kwargs = {}
        if timeout is not None:
            client_kwargs["timeout"] = timeout

        async with x402HttpxClient(client, **client_kwargs) as http:
            response = await http.request(
                method,
                url,
                params=params,
                json=body,
                headers=headers or {},
            )
            await response.aread()

            try:
                payload = response.json()
            except Exception:
                payload = {"error": response.text}

            receipt = None
            if response.is_success:
                try:
                    receipt = http_client.get_payment_settle_response(
                        lambda name: response.headers.get(name)
                    )
                except Exception:
                    receipt = None

            return {
                "status_code": response.status_code,
                "payload": payload,
                "receipt": receipt,
                "headers": dict(response.headers),
            }

    try:
        return asyncio.run(_run())
    except PaymentError:
        raise
    except Exception as exc:
        raise PaymentConfigurationError(
            "True x402 request execution failed before a paid response was returned.",
            details={"reason": str(exc)},
        ) from exc
