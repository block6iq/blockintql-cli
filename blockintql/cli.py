#!/usr/bin/env python3
"""
BlockINTQL CLI

PRIVACY ARCHITECTURE:
  BlockINTQL API receives: address + chain ONLY
  Provider API receives: address + your key (direct from your machine)
  BlockINTQL NEVER sees: your provider key or raw provider response

Verify this by reading the source. Open source: github.com/block6iq/blockintql-cli
"""

from __future__ import annotations

import sys, os, json, base64, tempfile, time, shutil, subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urlparse, parse_qsl, urlunparse
import click
import httpx
from rich.console import Console
from rich.table import Table
from rich import box
from rich.panel import Panel
from rich.text import Text
from . import __version__
from .payments import (
    PaymentError,
    ensure_wallet_runtime_ready,
    enforce_payment_policy,
    get_evm_private_key,
    load_payment_config,
    validate_evm_private_key,
)
from .providers import adjudicate_provider_result, get_provider, get_provider_spec, list_providers
from .x402_runtime import request_with_x402
from .graph_shell import (
    compile_graph_shell_prompt,
    shell_spec_summary,
    build_graph_shell_url,
)

# ── BANNER ────────────────────────────────────────────────────────────────────
BLOCKINTQL_BANNER = """
[bold white]██████╗ ██╗      ██████╗  ██████╗██╗  ██╗██╗███╗   ██╗████████╗ ██████╗ ██╗     [/bold white]
[bold white]██╔══██╗██║     ██╔═══██╗██╔════╝██║ ██╔╝██║████╗  ██║╚══██╔══╝██╔═══██╗██║     [/bold white]
[bold white]██████╔╝██║     ██║   ██║██║     █████╔╝ ██║██╔██╗ ██║   ██║   ██║   ██║██║     [/bold white]
[bold white]██╔══██╗██║     ██║   ██║██║     ██╔═██╗ ██║██║╚██╗██║   ██║   ██║▄▄ ██║██║     [/bold white]
[bold white]██████╔╝███████╗╚██████╔╝╚██████╗██║  ██╗██║██║ ╚████║   ██║   ╚██████╔╝███████╗[/bold white]
[bold white]╚═════╝ ╚══════╝ ╚═════╝  ╚═════╝╚═╝  ╚═╝╚═╝╚═╝  ╚═══╝   ╚═╝    ╚══▀▀═╝ ╚══════╝[/bold white]
[dim]  On-Chain Intelligence · blockintql.com[/dim]
"""

DEFAULT_API_BASE = "https://blockintql.com"
DIRECT_API_BASE = "https://btc-index-api-385334043904.us-central1.run.app"
API_BASE = os.environ.get("BLOCKINTQL_API_URL", DEFAULT_API_BASE)
GRAPH_SHELL_BASE = os.environ.get("BLOCKINTQL_GRAPH_SHELL_URL", "")
CONFIG_FILE = os.path.expanduser("~/.blockintql/config.json")
PAYMENT_RESPONSE_HEADER_CANDIDATES = ("PAYMENT-RESPONSE", "payment-response")
CUSTOM_ROUTE_PROVIDERS = {"metasleuth", "crystal", "merkle_science", "nomis", "generic", "blockintai"}
PUBLIC_PROVIDER_CHOICES = [
    "blockintai",
    "chainalysis",
    "trm",
    "elliptic",
    "metasleuth",
    "crystal",
    "merkle_science",
    "nomis",
    "generic",
]
console = Console()
err_console = Console(stderr=True)


class DefaultingGroup(click.Group):
    default_command_name = "balances"

    def parse_args(self, ctx, args):
        commands = set(self.list_commands(ctx))
        if args:
            first = args[0]
            if first in {"--address", "-a"} or (not first.startswith("-") and first not in commands):
                args.insert(0, self.default_command_name)
        return super().parse_args(ctx, args)


class LaunchScopeGroup(click.Group):
    """Render top-level help with explicit V1 launch scope grouping."""

    LIVE_COMMANDS = {
        "auth",
        "buy",
        "capabilities",
        "chart",
        "chat",
        "compensation",
        "graph",
        "history",
        "login",
        "pay",
        "provider",
        "providers",
        "screen",
        "screen-tx",
        "status",
        "verdict",
        "wallet",
    }

    def format_commands(self, ctx, formatter):
        rows_live = []
        rows_coming = []
        for subcommand in self.list_commands(ctx):
            cmd = self.get_command(ctx, subcommand)
            if cmd is None or cmd.hidden:
                continue
            help_text = cmd.get_short_help_str()
            target_rows = rows_live if subcommand in self.LIVE_COMMANDS else rows_coming
            target_rows.append((subcommand, help_text))

        if rows_live:
            with formatter.section("Live Now (V1)"):
                formatter.write_dl(rows_live)

        if rows_coming:
            with formatter.section("Coming Soon (Preview)"):
                formatter.write_dl(rows_coming)
            formatter.write_paragraph()
            formatter.write_text(
                "Preview commands are not part of V1 launch scope. "
                "Enable previews with: export BLOCKINTQL_ENABLE_EXPERIMENTAL=1"
            )


LAUNCH_V1_CAPABILITY_IDS = {
    "verdict",
    "screen",
    "screen_tx",
    "history",
    "chat",
}

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f: return json.load(f)
    return {}

def save_config(config):
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)
    Path(CONFIG_FILE).chmod(0o600)


def save_last_compensation_token(token: str | None):
    token = str(token or "").strip()
    if not token:
        return
    try:
        from datetime import datetime, timezone
        config = load_config()
        config["last_compensation"] = {
            "token": token,
            "captured_at": datetime.now(timezone.utc).isoformat(),
        }
        save_config(config)
    except Exception:
        return


def get_last_compensation_token():
    config = load_config()
    payload = config.get("last_compensation") or {}
    token = str(payload.get("token") or "").strip()
    captured_at = payload.get("captured_at")
    return token, captured_at


def _build_wallet_compensation_claim(token: str):
    config = load_config()
    payment_config = load_payment_config(config)
    if not payment_config:
        return None, "No wallet payment configuration found."
    try:
        ensure_wallet_runtime_ready(payment_config)
    except PaymentError as exc:
        return None, exc.message

    private_key = get_evm_private_key(payment_config)
    if not private_key:
        return None, "Wallet private key is not available for claim signing."

    try:
        from eth_account import Account
        from eth_account.messages import encode_defunct
    except Exception:
        return None, "Wallet signature support requires eth-account."

    issued_at = datetime.now(timezone.utc).isoformat()
    nonce = base64.urlsafe_b64encode(os.urandom(12)).decode("ascii").rstrip("=")
    account = Account.from_key(private_key)
    address = account.address
    message = (
        "BlockINTQL Compensation Claim\n"
        f"token={token}\n"
        f"address={address}\n"
        f"issued_at={issued_at}\n"
        f"nonce={nonce}"
    )
    signed = account.sign_message(encode_defunct(text=message))
    return {
        "version": "biq-wallet-claim-v1",
        "address": address,
        "issued_at": issued_at,
        "nonce": nonce,
        "message": message,
        "signature": signed.signature.hex(),
    }, None

def _wallet_ready_for_requests() -> bool:
    config = load_config()
    payment_config = load_payment_config(config)
    if not payment_config:
        return False
    try:
        ensure_wallet_runtime_ready(payment_config)
    except PaymentError:
        return False
    return bool(payment_config.auto_pay)


def get_api_key():
    env_key = os.environ.get("BLOCKINTQL_API_KEY")
    if env_key:
        return env_key
    saved_key = load_config().get("api_key")
    if not saved_key:
        return None
    # Avoid stale saved API keys shadowing healthy wallet-backed x402 sessions.
    if _wallet_ready_for_requests():
        return None
    return saved_key


def get_admin_key():
    return os.environ.get("BLOCKINTQL_ADMIN_KEY") or load_config().get("admin_api_key")


def get_graph_shell_base():
    """Resolve the base URL for the promptable graph web UI (explorer-v2).

    With a local dev server running the new static mount, a bare local setup
    "just has" the graph UI: if BLOCKINTQL_API_URL points at 127.0.0.1:8000
    (or localhost:8000) we auto-synthesize http://.../explorer-react/ so that
    `blockintql graph` (bare), `graph shell "..." --open`, and chat handoffs
    work without any extra BLOCKINTQL_GRAPH_SHELL_URL.
    """
    env_url = os.environ.get("BLOCKINTQL_GRAPH_SHELL_URL")
    if env_url:
        return env_url
    cfg_url = load_config().get("graph_shell_url")
    if cfg_url:
        return cfg_url
    if GRAPH_SHELL_BASE:
        return GRAPH_SHELL_BASE

    # Auto-discover for local dev server (the mount in the Python server serves the dist here)
    api_url = os.environ.get("BLOCKINTQL_API_URL", "")
    if api_url:
        low = api_url.lower()
        if "127.0.0.1:8000" in low or "localhost:8000" in low or low.startswith("http://127.0.0.1") or low.startswith("http://localhost"):
            base = api_url.rstrip("/")
            return f"{base}/explorer-react/"

    return ""


def provider_route_hint(name: str, provider_url: str | None = None) -> str:
    provider_name = str(name or "").strip().lower()
    spec = get_provider_spec(provider_name)
    if spec and spec.get("route_template") and spec.get("route_template") != "{custom_provider_url}":
        return f"{spec.get('method', 'GET')} {spec['route_template']}"
    routes = {
        "chainalysis": "POST https://api.chainalysis.com/api/kyt/v2/users/demo_user/transfers",
        "trm": "POST https://api.trmlabs.com/public/v2/screening/addresses",
        "elliptic": "POST https://aml-api.elliptic.co/v2/wallet/synchronous",
        "metasleuth": f"GET {provider_url or '<metasleuth-route/{address}>'}",
        "crystal": f"GET {provider_url or '<crystal-route/{address}>'}",
        "merkle_science": f"GET {provider_url or '<merkle-science-route/{address}>'}",
        "nomis": f"GET {provider_url or '<nomis-route/{address}>'}",
        "generic": f"GET {provider_url or '<provider-url>'}",
        "blockintai": f"GET {provider_url or 'https://blockint.ai/api/v1/screen/{address}'}",
    }
    return routes.get(provider_name, provider_url or "Custom provider route")


def get_provider_configured_settings(provider_name=None):
    config = load_config()
    provider_cfg = config.get("provider_connection") or {}
    provider_name = provider_name or provider_cfg.get("provider") or config.get("default_provider")
    provider_key = os.environ.get("BLOCKINTQL_PROVIDER_KEY") or provider_cfg.get("provider_key")
    provider_url = provider_cfg.get("provider_url")
    auth_header = provider_cfg.get("auth_header")
    auth_prefix = provider_cfg.get("auth_prefix")
    risk_field = provider_cfg.get("risk_field")
    entity_field = provider_cfg.get("entity_field")
    raw_provider = str(provider_name or "").strip().lower() or None
    provider_name = raw_provider
    if provider_name == "blockintai":
        provider_name = "generic"
        provider_url = provider_url or "https://blockint.ai/api/v1/screen/{address}"
        auth_header = auth_header or "x-api-key"
        auth_prefix = auth_prefix if auth_prefix is not None else ""
        risk_field = risk_field or "riskScore"
        entity_field = entity_field or "entity"
    return {
        "provider": provider_name,
        "provider_key": provider_key,
        "provider_url": provider_url,
        "auth_header": auth_header,
        "auth_prefix": auth_prefix,
        "risk_field": risk_field,
        "entity_field": entity_field,
        "raw_provider": raw_provider or (config.get("provider_connection") or {}).get("provider") or config.get("default_provider"),
    }


def infer_chain_from_value(value, fallback="bitcoin"):
    text = str(value or "").strip()
    if text.startswith("0x") and len(text) == 42:
        return "ethereum"
    if text.startswith(("bc1", "1", "3")):
        return "bitcoin"
    if text.startswith("T") and len(text) == 34:
        return "tron"
    if text.startswith(("L", "M")):
        return "litecoin"
    return fallback


def coalesce_address(argument_value=None, option_value=None):
    return option_value or argument_value

def get_headers():
    key = get_api_key()
    if not key:
        err_console.print("[red]No API key.[/] Run: blockintql auth --api-key YOUR_KEY")
        sys.exit(1)
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def get_admin_headers():
    key = get_admin_key()
    if not key:
        err_console.print("[red]No admin key.[/] Set BLOCKINTQL_ADMIN_KEY or save admin_api_key in config.")
        sys.exit(1)
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def _validate_api_key(api_key: str, timeout: int = 20) -> tuple[bool, str | None]:
    if not api_key or not str(api_key).strip():
        return False, "API key cannot be empty."
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    last_error = None
    for base in _api_base_candidates():
        url = f"{base}/v1/me"
        try:
            response = httpx.get(url, headers=headers, timeout=timeout)
            payload = {}
            try:
                payload = response.json() if response.content else {}
            except Exception:
                payload = {}
            if response.status_code < 400:
                return True, None
            message = None
            if isinstance(payload, dict):
                message = payload.get("error")
            if response.status_code == 402 and message and "Invalid API key" not in message:
                # Valid key with insufficient credits is still a valid key.
                return True, None
            last_error = message or response.text or f"HTTP {response.status_code}"
        except Exception as exc:
            last_error = str(exc)
    return False, last_error or "Unable to validate API key right now."


def _extract_payment_response(response):
    for header_name in PAYMENT_RESPONSE_HEADER_CANDIDATES:
        header_value = response.headers.get(header_name)
        if not header_value:
            continue
        try:
            return json.loads(base64.b64decode(header_value).decode("utf-8"))
        except Exception:
            try:
                return json.loads(header_value)
            except Exception:
                return {"raw": header_value}
    return None


def _api_base_candidates():
    bases = [API_BASE]
    if API_BASE.rstrip("/") == DEFAULT_API_BASE.rstrip("/") and DIRECT_API_BASE not in bases:
        bases.append(DIRECT_API_BASE)
    return bases


def _should_retry_direct_from_response(response):
    return int(getattr(response, "status_code", 0) or 0) in {500, 502, 503, 504, 520, 522, 524}


def _should_retry_direct_from_exception(exc):
    if isinstance(exc, httpx.ReadTimeout):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return int(exc.response.status_code or 0) in {502, 503, 504, 520, 522, 524}
    return False


def _attach_payment_metadata(payload, metadata):
    if not metadata:
        return payload
    if isinstance(payload, dict):
        enriched = dict(payload)
        enriched["payment"] = metadata
        return enriched
    return {"result": payload, "payment": metadata}


def _response_error_message(response):
    try:
        payload = response.json()
        if isinstance(payload, dict) and payload.get("error"):
            return payload["error"]
    except Exception:
        pass
    return response.text or f"Request failed with status {response.status_code}."


def _build_payment_metadata(payment_config, receipt=None, *, mode="x402-sdk"):
    metadata = {
        "wallet_type": payment_config.wallet_type,
        "auto_pay": payment_config.auto_pay,
        "max_payment_usd": payment_config.max_payment_usd,
        "authorization_mode": mode,
    }
    if receipt is not None:
        metadata["receipt"] = receipt
    return metadata


def _extract_compensation_metadata(headers):
    if not headers:
        return None
    lowered = {str(k).lower(): v for k, v in dict(headers).items()}
    token = str(lowered.get("x-blockintql-compensation-token") or "").strip()
    status = str(lowered.get("x-blockintql-compensation") or "").strip().lower()
    mode = str(lowered.get("x-blockintql-compensation-mode") or "").strip().lower()
    reason = str(lowered.get("x-blockintql-compensation-reason") or "").strip()
    if not (token or status or mode or reason):
        return None
    payload = {
        "status": status or None,
        "mode": mode or None,
        "reason": reason or None,
        "token": token or None,
    }
    return {k: v for k, v in payload.items() if v is not None}


def _extract_payment_challenge(response):
    try:
        payload = response.json()
        if isinstance(payload, dict) and payload.get("accepts"):
            return payload
    except Exception:
        pass
    header = response.headers.get("PAYMENT-REQUIRED")
    if header:
        try:
            return json.loads(base64.b64decode(header).decode("utf-8"))
        except Exception:
            pass
    return {}


def _request_with_optional_payment(method, path, *, params=None, body=None, require_auth=True, timeout=30):
    api_key = get_api_key()
    config = load_config()
    payment_config = load_payment_config(config)
    headers = {"Content-Type": "application/json"}
    if require_auth and api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    last_exception = None
    response = None
    url = None
    for base in _api_base_candidates():
        url = f"{base}{path}"
        try:
            candidate = httpx.request(method, url, headers=headers, params=params, json=body, timeout=timeout)
            if (
                base != _api_base_candidates()[-1]
                and _should_retry_direct_from_response(candidate)
            ):
                response = candidate
                continue
            response = candidate
            break
        except Exception as exc:
            last_exception = exc
            if base != _api_base_candidates()[-1] and _should_retry_direct_from_exception(exc):
                continue
            raise

    if response is None:
        if last_exception:
            raise last_exception
        raise RuntimeError("No API response received.")

    if require_auth and not api_key and response.status_code == 402 and not payment_config:
        raise PaymentError(
            "This endpoint requires either an API key or wallet-backed x402 auto-pay.",
            details={
                "next": [
                    "API key: blockintql auth --api-key biq_sk_live_...",
                    "Wallet: blockintql login --auto-pay --max-payment 0.10",
                    "Check wallet mode: blockintql wallet status --agent",
                ]
            },
        )

    if not (require_auth and not api_key and payment_config and response.status_code == 402):
        response.raise_for_status()
        return response.json()

    challenge = _extract_payment_challenge(response) or {"error": response.text}
    if not response.headers.get("PAYMENT-REQUIRED"):
        raise PaymentError(
            "The server did not return a standard x402 payment challenge.",
            details={"status_code": response.status_code},
        )
    ensure_wallet_runtime_ready(payment_config)
    payment_details = enforce_payment_policy(payment_config, challenge)
    result = request_with_x402(
        method,
        url,
        payment_config=payment_config,
        params=params,
        body=body,
        headers=headers,
        timeout=timeout,
    )
    if result.get("status_code", 0) >= 400:
        # Launch-safety: if wallet-backed x402 fails transiently, retry once with
        # API-key credits (when present) so paid surfaces can still execute.
        fallback_api_key = (
            os.environ.get("BLOCKINTQL_FALLBACK_API_KEY")
            or load_config().get("fallback_api_key")
        )
        if fallback_api_key:
            retry_headers = {"Content-Type": "application/json", "Authorization": f"Bearer {fallback_api_key}"}
            retry_response = httpx.request(
                method,
                url,
                headers=retry_headers,
                params=params,
                json=body,
                timeout=timeout,
            )
            retry_response.raise_for_status()
            payload = retry_response.json()
            if isinstance(payload, dict):
                metadata = {
                    "authorization_mode": "api_key_fallback",
                    "wallet_x402_failed": True,
                }
                return _attach_payment_metadata(payload, metadata)
        failed_details = dict(payment_details)
        failed_details["phase"] = "x402_execute"
        failed_details["status_code"] = result.get("status_code")
        payload = result.get("payload")
        if isinstance(payload, dict):
            failed_details["response_error"] = payload.get("error") or payload.get("detail")
            if payload.get("code"):
                failed_details["response_code"] = payload.get("code")
        elif payload:
            failed_details["response_error"] = str(payload)[:240]
        raise PaymentError(
            "The x402-paid request did not complete successfully.",
            details=failed_details,
        )
    payment_metadata = dict(payment_details)
    payment_metadata.update(_build_payment_metadata(payment_config, result.get("receipt")))
    compensation_metadata = _extract_compensation_metadata(result.get("headers"))
    if compensation_metadata:
        payment_metadata["compensation"] = compensation_metadata
    return _attach_payment_metadata(result.get("payload"), payment_metadata)

def api_get(path, params=None, require_auth=True, timeout=30):
    """Query BlockINTQL API — sends address+chain ONLY, never provider keys."""
    try:
        return _request_with_optional_payment(
            "GET",
            path,
            params=params,
            require_auth=require_auth,
            timeout=timeout,
        )
    except PaymentError as e:
        return e.to_dict()
    except httpx.HTTPStatusError as e:
        try:
            payload = e.response.json()
            if isinstance(payload, dict):
                return payload
        except Exception:
            pass
        return {"error": str(e)}
    except Exception as e:
        return {"error": str(e)}

def api_post(path, body, require_auth=True, timeout=60):
    """Query BlockINTQL API — sends address+chain ONLY, never provider keys."""
    try:
        return _request_with_optional_payment(
            "POST",
            path,
            body=body,
            require_auth=require_auth,
            timeout=timeout,
        )
    except PaymentError as e:
        return e.to_dict()
    except httpx.HTTPStatusError as e:
        try:
            payload = e.response.json()
            if isinstance(payload, dict):
                return payload
        except Exception:
            pass
        return {"error": str(e)}
    except Exception as e:
        return {"error": str(e)}


def api_put(path, body, require_auth=True, timeout=60):
    """Update BlockINTQL API resources with authenticated JSON payloads."""
    try:
        return _request_with_optional_payment(
            "PUT",
            path,
            body=body,
            require_auth=require_auth,
            timeout=timeout,
        )
    except PaymentError as e:
        return e.to_dict()
    except httpx.HTTPStatusError as e:
        try:
            payload = e.response.json()
            if isinstance(payload, dict):
                return payload
        except Exception:
            pass
        return {"error": str(e)}
    except Exception as e:
        return {"error": str(e)}


def admin_api_get(path, params=None, timeout=30):
    try:
        response = httpx.get(f"{API_BASE}{path}", headers=get_admin_headers(), params=params, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": str(e)}

def create_workspace_from_plan(plan_result, quiet=False, agent=False):
    """Create a workspace from a plan payload when the API recommends one."""
    recommended = plan_result.get("recommended_workspace") or {}
    payload = recommended.get("payload") or {}
    if not payload:
        return None
    if not quiet and not agent:
        console.print("[dim]Opening recommended workspace...[/]")
    created = api_post("/v1/workspaces/create", payload, require_auth=True)
    if "error" in created:
        return {
            "execution_error": {
                "detail": created["error"],
                "source": "workspace_create_fallback",
            }
        }
    return {
        "execution_mode": "created_workspace_from_plan",
        "executed_workspace": created,
        "workspace_created_from_plan": True,
    }


def persist_workspace_ask_history(workspace_id, goal, address, chain, plan_result):
    if not workspace_id:
        return None
    brief = plan_result.get("investigation_brief") or {}
    actions = brief.get("recommended_actions") or []
    execution_outcome = None
    if plan_result.get("resume_workspace", {}).get("workspace_id"):
        workspace = plan_result.get("resume_workspace") or {}
        execution_outcome = {
            "type": "resumed_workspace",
            "label": workspace.get("name") or workspace.get("workspace_id") or "workspace",
            "status": workspace.get("status"),
            "detail": workspace.get("reason") or "Continued in the selected workspace.",
        }
    elif plan_result.get("executed_workspace", {}).get("workspace_id"):
        workspace = plan_result.get("executed_workspace") or {}
        execution_outcome = {
            "type": "created_workspace",
            "label": workspace.get("name") or workspace.get("workspace_id") or "workspace",
            "status": workspace.get("status"),
            "detail": "Created a workspace from the plan.",
        }
    elif plan_result.get("execution_error"):
        err = plan_result.get("execution_error") or {}
        execution_outcome = {
            "type": "execution_error",
            "label": err.get("capability_id") or "execution",
            "status": "error",
            "detail": err.get("detail") or "Execution failed.",
        }
    normalized_actions = []
    for action in actions[:3]:
        if isinstance(action, dict):
            normalized_actions.append({
                "id": action.get("id"),
                "title": action.get("title") or action.get("id"),
                "description": action.get("description"),
                "surface": action.get("surface"),
                "target_panel": action.get("target_panel"),
                "target_query_type": action.get("target_query_type"),
                "preferred_focus": action.get("preferred_focus"),
                "auto_chain_safe": action.get("auto_chain_safe"),
            })
        elif action:
            normalized_actions.append({"title": str(action)})
    planner_reply = {
        "summary": plan_result.get("summary"),
        "mode": (plan_result.get("intent") or {}).get("mode"),
        "recommended_surface": plan_result.get("recommended_surface"),
        "recommended_actions": normalized_actions,
        "estimated_total_credits": plan_result.get("estimated_total_credits"),
        "estimated_total_usd": plan_result.get("estimated_total_usd"),
    }
    entry = {
        "asked_at": __import__("datetime").datetime.utcnow().isoformat(),
        "goal": goal,
        "address": address or None,
        "chain": chain,
        "recommended_surface": plan_result.get("recommended_surface"),
        "intent_mode": (plan_result.get("intent") or {}).get("mode"),
        "estimated_total_credits": plan_result.get("estimated_total_credits"),
        "estimated_total_usd": plan_result.get("estimated_total_usd"),
        "execution_mode": plan_result.get("execution_mode"),
        "planner_reply": planner_reply,
        "execution_outcome": execution_outcome,
        "execution_outcomes": [execution_outcome] if execution_outcome else [],
    }
    return api_put(
        f"/v1/workspaces/{workspace_id}/state",
        {"saved_state": {"ask_history": [entry]}},
        require_auth=True,
    )


def run_ask_flow(goal, address=None, workspace_id=None, chain="ethereum", budget_credits=None, budget_usd=None,
                 upto_budget_usd=None, open_workspace=False, mode=None, agent=False, quiet=False):
    body = {
        "goal": goal,
        "chain": chain,
    }
    if address:
        body["address"] = address
    if workspace_id:
        body["workspace_id"] = workspace_id
    if budget_credits is not None:
        body["budget_credits"] = budget_credits
    if budget_usd is not None:
        body["budget_usd"] = budget_usd
    if upto_budget_usd is not None:
        body["upto_budget_usd"] = upto_budget_usd
    if mode:
        body["execution_profile"] = mode
    if open_workspace:
        body["prefer_surface"] = "workspace"
        body["execute_workspace"] = True

    result = api_post("/v1/plan", body, require_auth=bool(open_workspace or workspace_id), timeout=180)

    if workspace_id and "error" not in result:
        workspace = api_get(f"/v1/workspaces/{workspace_id}", require_auth=True, timeout=120)
        if "error" not in workspace:
            result["resume_workspace"] = {
                "workspace_id": workspace.get("workspace_id"),
                "name": workspace.get("name"),
                "status": workspace.get("status"),
                "activity": workspace.get("activity") or {},
                "reason": "Continued inside the selected workspace.",
            }

    elif open_workspace and "error" not in result:
        workspace_surface = result.get("recommended_surface") == "workspace" or bool(result.get("recommended_workspace"))
        if workspace_surface:
            existing = api_get("/v1/workspaces", params={"limit": 10}, require_auth=True, timeout=120)
            workspaces = existing.get("workspaces") if isinstance(existing, dict) else None
            candidate = choose_resume_candidate(workspaces or [], seed_address=address, goal_text=goal)
            if candidate and int((candidate.get("activity") or {}).get("activity_score", 0)) > 0:
                result["resume_workspace"] = {
                    "workspace_id": candidate.get("workspace_id"),
                    "name": candidate.get("name"),
                    "status": candidate.get("status"),
                    "activity": candidate.get("activity") or {},
                    "reason": describe_resume_reason(candidate, seed_address=address, goal_text=goal),
                }

    if (
        open_workspace
        and "error" not in result
        and not result.get("executed_workspace")
        and result.get("recommended_workspace", {}).get("payload")
        and not result.get("resume_workspace")
        and not workspace_id
    ):
        fallback = create_workspace_from_plan(result, quiet=quiet, agent=agent)
        if fallback:
            result.update(fallback)

    target_workspace_id = None
    if workspace_id:
        target_workspace_id = workspace_id
    elif result.get("resume_workspace", {}).get("workspace_id"):
        target_workspace_id = result["resume_workspace"]["workspace_id"]
    elif result.get("executed_workspace", {}).get("workspace_id"):
        target_workspace_id = result["executed_workspace"]["workspace_id"]
    if open_workspace and target_workspace_id and "error" not in result:
        history_result = persist_workspace_ask_history(target_workspace_id, goal, address, chain, result)
        if isinstance(history_result, dict) and "error" in history_result:
            result["ask_history_warning"] = history_result["error"]

    output(result, agent, quiet)

    if open_workspace and not agent and not quiet and sys.stdout.isatty():
        if result.get("resume_workspace", {}).get("workspace_id"):
            target_workspace_id = result["resume_workspace"]["workspace_id"]
            resume_reason = result["resume_workspace"].get("reason")
            resume_activity = result["resume_workspace"].get("activity") or {}
            resume_source = (
                "ask_resume_candidate_graph"
                if resume_activity.get("graph_initialized")
                else "ask_resume_candidate"
            )
        elif result.get("executed_workspace", {}).get("workspace_id"):
            target_workspace_id = result["executed_workspace"]["workspace_id"]
            resume_reason = None
            resume_source = None
        elif workspace_id:
            target_workspace_id = workspace_id
            resume_reason = "Continued inside the selected workspace."
            resume_source = "workspace_chat"
        else:
            target_workspace_id = None
            resume_reason = None
            resume_source = None

        if target_workspace_id:
            open_result = open_workspace_in_browser(
                target_workspace_id,
                resume_reason=resume_reason,
                resume_source=resume_source,
            )
            if open_result is None:
                console.print("[dim]Browser opened to investigation workspace.[/]")
                goal_family = classify_goal_family(goal)
                if goal_family == "compliance":
                    console.print("[dim]Start here in the browser:[/]")
                    console.print("  1. Click Load")
                    console.print("  2. Click the Seed node")
                    console.print("  3. Review the wallet activity in the right-hand panel")
                    console.print("  4. Only run an expansion if you want to grow the graph beyond the seed wallet")
                elif goal_family == "trace":
                    console.print("[dim]Start here in the browser:[/]")
                    console.print("  1. Click Load")
                    console.print("  2. Click the Seed node")
                    console.print("  3. Review the wallet evidence before expanding to counterparties")
                    console.print("  4. Only run an expansion when you want direct node-to-node graph depth")
                else:
                    console.print("[dim]Start here in the browser:[/]")
                    console.print("  1. Click Load")
                    console.print("  2. Run the primary expansion")
                    console.print("  3. Sync artifacts after the expansion completes")
                    console.print("  4. Hydrate the graph to load the evidence surface")
            elif str(open_result).startswith("http"):
                console.print(f"[dim]Open this URL manually:[/] {open_result}")
            else:
                console.print(f"[yellow]{open_result}[/]")

    return result


def _with_query_params(url, params):
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.update({key: value for key, value in params.items() if value not in (None, "")})
    return urlunparse(parsed._replace(query=urlencode(query)))


def open_workspace_in_browser(workspace_id, resume_reason=None, resume_source=None):
    import webbrowser

    data = api_get(f"/v1/workspaces/{workspace_id}/manifest", require_auth=True)
    if "error" in data:
        return data.get("error")
    url = workspace_launch_url(data)
    if not url:
        return "Workspace is not ready to open yet."
    api_key = get_api_key()
    url = _with_query_params(
        url,
        {
            "api_key": api_key,
            "resume": "1" if resume_reason else "",
            "resume_reason": resume_reason,
            "resume_source": resume_source,
        },
    )
    try:
        webbrowser.open(url)
        return None
    except Exception:
        return url

def enrich_with_provider(result, address, chain, provider_name, provider_key, provider_url, auth_header=None, auth_prefix=None, risk_field=None, entity_field=None):
    """
    PRIVACY: Runs entirely on your local machine.
    Calls provider API directly — key never sent to BlockINTQL.
    Only the merged verdict (no raw provider data) is shown to user.
    """
    if not provider_name:
        return result
    requested_provider_name = str(provider_name).strip().lower()
    if str(provider_name).strip().lower() == "blockintai":
        provider_name = "generic"
        auth_header = auth_header or "x-api-key"
        auth_prefix = "" if auth_prefix is None else auth_prefix
    provider = get_provider(
        provider_name,
        provider_key or "",
        url_template=provider_url,
        risk_field=risk_field or ("riskScore" if requested_provider_name == "blockintai" else "risk_score"),
        entity_field=entity_field or "entity",
        auth_header=auth_header or "Authorization",
        auth_prefix="Bearer" if auth_prefix is None else auth_prefix,
    )
    if not provider:
        err_console.print(f"[yellow]Unknown provider: {provider_name}[/]")
        return result
    if provider.requires_api_key and not provider_key:
        err_console.print(f"[yellow]{provider_name} requires --provider-key or BLOCKINTQL_PROVIDER_KEY[/]")
        return result

    # PRIVACY: This call goes directly to provider API from your machine
    pd = provider.get_address_risk(address, chain)

    if "error" in pd.get("raw", {}):
        result["provider_data"] = {
            "provider": requested_provider_name,
            "error": pd.get("raw", {}).get("error"),
            "route": provider_route_hint(requested_provider_name, provider_url),
        }
        result.setdefault("risk_indicators", []).append("PROVIDER_UNAVAILABLE")
        if result.get("verdict") == "CLEAR":
            result["verdict"] = "CAUTION"
            result["safe"] = False
        result["action"] = "review"
        result["narrative"] = (
            f"{requested_provider_name} was requested for local enrichment, but the vendor route returned "
            f"{pd.get('raw', {}).get('error')}. Internal BlockINTQL data may still be shown below, but the vendor decision could not be verified."
        )
        return result

    provider_policy = adjudicate_provider_result(pd)
    canonical_category = provider_policy.get("canonical_category")
    sanctions_override = bool(pd.get("sanctions_hit")) or canonical_category == "sanctions"
    provider_effective_risk = 100.0 if sanctions_override else float(pd.get("risk_score", 0) or 0)

    # Merge — take higher risk score, except sanctions which are always hard-forced to 100.
    result["risk_score"] = max(provider_effective_risk, float(result.get("risk_score", 0) or 0))
    if sanctions_override:
        result["risk_score"] = 100.0
    if pd.get("entity_name") and not result.get("entity"):
        result["entity"] = pd["entity_name"]
    provider_recommended_verdict = provider_policy.get("recommended_verdict")
    if sanctions_override or provider_recommended_verdict == "BLOCK":
        result["verdict"] = "BLOCK"
        result["safe"] = False
        if canonical_category:
            result.setdefault("risk_indicators", []).append(f"PROVIDER_{canonical_category.upper()}")
        if sanctions_override:
            result.setdefault("risk_indicators", []).append("SANCTIONS")
    elif provider_recommended_verdict in {"CAUTION", "UNKNOWN"} and result.get("verdict") == "CLEAR":
        result["verdict"] = "CAUTION"
        result["safe"] = False
        if canonical_category:
            result.setdefault("risk_indicators", []).append(f"PROVIDER_{canonical_category.upper()}")

    risk_indicators = []
    for item in result.get("risk_indicators", []):
        if item not in risk_indicators:
            risk_indicators.append(item)
    result["risk_indicators"] = risk_indicators

    if provider_recommended_verdict in {"CAUTION", "UNKNOWN"}:
        result["action"] = "review"
    if sanctions_override or provider_recommended_verdict == "BLOCK":
        result["action"] = "block"

    # Store an allowlisted summary only. Raw provider responses stay local.
    result["provider_data"] = {
        "provider": requested_provider_name,
        "entity_name": pd.get("entity_name"),
        "entity_category": pd.get("entity_category"),
        "risk_score": provider_effective_risk,
        "risk_indicators": pd.get("risk_indicators", []),
        "sanctions_hit": sanctions_override,
        "vendor_verdict": pd.get("vendor_verdict"),
        "vendor_category": pd.get("vendor_category"),
        "canonical_category": canonical_category,
        "recommended_verdict": provider_recommended_verdict,
        "severity": provider_policy.get("severity"),
        "confidence": provider_policy.get("confidence"),
        "reasons": provider_policy.get("reasons", []),
        "decision_source": "local_provider_merge",
        "raw_vendor_data_seen_locally": True,
        "raw_vendor_data_sent_to_blockintql": False,
        "mapping_rule": (
            f"{pd.get('vendor_category')} -> {provider_recommended_verdict}"
            if pd.get("vendor_category") and provider_recommended_verdict
            else None
        ),
    }
    # Final safety clamp: any sanctions evidence must resolve to 100/100 BLOCK.
    sanctions_evidence = bool(result.get("provider_data", {}).get("sanctions_hit")) or any(
        "SANCTION" in str(flag).upper() for flag in (result.get("risk_indicators") or [])
    )
    if sanctions_evidence:
        result["risk_score"] = 100.0
        result["verdict"] = "BLOCK"
        result["safe"] = False
        result["action"] = "block"
        sanction_reason = None
        reasons = result.get("provider_data", {}).get("reasons") or []
        if reasons:
            sanction_reason = str(reasons[0]).strip()
        if not sanction_reason:
            sanction_reason = "Provider reported a direct sanctions hit."
        entity_name = (result.get("provider_data", {}).get("entity_name") or result.get("entity") or "").strip()
        entity_part = f" ({entity_name})" if entity_name else ""
        result["narrative"] = (
            f"Sanctions evidence was confirmed for {address}{entity_part}. "
            f"{sanction_reason} Final decision: BLOCK (100/100)."
        )

    # Preserve server-side Sonar consensus when present.
    # If unavailable, expose a clearly marked local adjudication consensus shape.
    existing_consensus = result.get("consensus")
    if isinstance(existing_consensus, dict) and existing_consensus:
        provider_mapping = (
            {str(pd.get("vendor_category")): canonical_category}
            if pd.get("vendor_category") and canonical_category
            else {}
        )
        existing_consensus["provider_adjudication"] = {
            "source": "local_provider_merge",
            "recommended_verdict": provider_recommended_verdict,
            "confidence": provider_policy.get("confidence") or "low",
            "reasons": provider_policy.get("reasons", []),
            "vendor_to_canonical": provider_mapping,
        }
        # Launch policy: exploit/scam/ransomware/sanctions evidence must resolve to BLOCK.
        hard_block_categories = {"sanctions", "scam", "ransomware", "darknet", "mixer"}
        if (
            provider_recommended_verdict == "BLOCK"
            and str(canonical_category or "").lower() in hard_block_categories
        ):
            existing_consensus["decision"] = "BLOCK"
            existing_consensus["confidence"] = "high"
            reasons = list(existing_consensus.get("reasons") or [])
            reasons.append("Exploit/sanctions policy override applied from provider adjudication.")
            existing_consensus["reasons"] = reasons
            policy_mapping = dict(existing_consensus.get("policy_mapping") or {})
            block_basis = list(policy_mapping.get("block_basis") or [])
            if "provider_exploit_policy_override" not in block_basis:
                block_basis.append("provider_exploit_policy_override")
            policy_mapping["block_basis"] = block_basis
            existing_consensus["policy_mapping"] = policy_mapping
        result["consensus"] = existing_consensus
    else:
        result["consensus"] = {
            "enabled": True,
            "mode": "address_screening",
            "model": "local_provider_consensus_v1",
            "consensus_reached": True,
            "decision": provider_recommended_verdict or result.get("verdict"),
            "confidence": provider_policy.get("confidence") or "low",
            "synthesized": True,
            "reasons": provider_policy.get("reasons", []),
            "policy_mapping": {
                "vendor_to_canonical": (
                    {str(pd.get("vendor_category")): canonical_category}
                    if pd.get("vendor_category") and canonical_category
                    else {}
                ),
                "block_basis": (
                    ["sanctions_hit", "provider_policy"]
                    if pd.get("sanctions_hit")
                    else (
                        ["provider_category_match", "provider_policy"]
                        if provider_recommended_verdict == "BLOCK"
                        else ["provider_policy"]
                    )
                ),
            },
        }
    return result

def verdict_color(v):
    return {"CLEAR": "green", "CAUTION": "yellow", "BLOCK": "red"}.get(str(v).upper(), "white")


def _as_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _short_addr(value, width=12):
    text = str(value or "")
    if len(text) <= width:
        return text
    keep = max(4, (width - 3) // 2)
    return f"{text[:keep]}...{text[-keep:]}"


def _sparkline(values):
    ticks = "▁▂▃▄▅▆▇█"
    nums = [_as_float(v) for v in values]
    if not nums or max(nums) <= 0:
        return "·" * max(1, len(nums))
    peak = max(nums)
    chars = []
    for value in nums:
        idx = int(round((value / peak) * (len(ticks) - 1)))
        chars.append(ticks[max(0, min(idx, len(ticks) - 1))])
    return "".join(chars)


def _bar(value, peak, width=24):
    if peak <= 0:
        return ""
    filled = int(round((_as_float(value) / peak) * width))
    return "█" * max(0, min(filled, width))


def render_stablecoin_flow_chart(result, *, hours=24, interval="hour", token=None):
    data = (result or {}).get("data") or {}
    rows = data.get("series") or []
    window_hours_used = int(data.get("window_hours_used") or hours or 0)
    source = (result or {}).get("source") or "unknown"
    if not rows:
        console.print("[yellow]No stablecoin flow data available for that window.[/]")
        if window_hours_used and window_hours_used != hours:
            console.print(f"[dim]Tried widening from {hours}h to {window_hours_used}h via {source}.[/]")
        else:
            has_token_filter = bool(token)
            using_day_interval = str(interval or "").lower() == "day"
            if has_token_filter and using_day_interval:
                console.print("[dim]No indexed rows matched this token/window yet. Try `blockintql stablecoins history <address> --days 30` or `blockintql stablecoins counterparties <address>` for wallet-level evidence.[/]")
            elif hours >= 168:
                console.print("[dim]Try focusing a token with `--token USDC` or `--token USDT`, or reduce granularity with `--interval day`.[/]")
            elif hours >= 72:
                console.print("[dim]Try a wider window like `--hours 168`, or focus a token with `--token USDC` / `--token USDT`.[/]")
            else:
                console.print("[dim]Try a wider window like `--hours 72` or `--hours 168`, or focus a token with `--token USDC` / `--token USDT`.[/]")
        return False

    grouped = {}
    for row in rows:
        symbol = row.get("token_symbol") or "UNKNOWN"
        grouped.setdefault(symbol, []).append(row)

    summary = data.get("summary") or {}
    peak_summary_volume = max(
        (_as_float((details or {}).get("total_volume")) for details in summary.values()),
        default=0.0,
    )
    console.print()
    console.print("[bold cyan]Stablecoin Flow Chart[/bold cyan]")
    header_bits = [f"{hours}h requested", f"{window_hours_used}h scanned", f"interval={interval}", f"token={token or 'all'}", f"source={source}"]
    console.print(f"[dim]{' · '.join(header_bits)}[/dim]")
    console.print(f"[dim]{'─' * 76}[/dim]")
    if summary:
        console.print("[bold]Market Summary[/bold]")
        for symbol, details in sorted(
            summary.items(),
            key=lambda item: _as_float((item[1] or {}).get("total_volume")),
            reverse=True,
        ):
            total_volume = _as_float((details or {}).get("total_volume"))
            transfer_count = int((details or {}).get("transfer_count") or 0)
            bar = _bar(total_volume, peak_summary_volume, width=20)
            console.print(
                f"[bold]{symbol:<5}[/bold] {bar:<20} "
                f"[dim]vol[/dim] ${total_volume:,.0f}  [dim]tx[/dim] {transfer_count}"
            )
        console.print(f"[dim]{'─' * 76}[/dim]")
    for symbol, series in sorted(grouped.items()):
        ordered = sorted(series, key=lambda item: str(item.get("bucket") or ""))
        values = [_as_float(item.get("total_volume")) for item in ordered]
        transfer_count = sum(int(item.get("transfer_count") or 0) for item in ordered)
        largest_transfer = max((_as_float(item.get("largest_transfer")) for item in ordered), default=0.0)
        unique_senders = max((int(item.get("unique_senders") or 0) for item in ordered), default=0)
        unique_receivers = max((int(item.get("unique_receivers") or 0) for item in ordered), default=0)
        console.print(
            f"[bold]{symbol:>5}[/bold]  {_sparkline(values)}  "
            f"[dim]vol[/dim] ${sum(values):,.0f}  [dim]tx[/dim] {transfer_count}"
        )
        console.print(
            f"      [dim]peak transfer[/dim] ${largest_transfer:,.0f}  "
            f"[dim]senders[/dim] {unique_senders}  [dim]receivers[/dim] {unique_receivers}"
        )
    console.print(f"[dim]{'─' * 76}[/dim]")
    console.print("[dim]BlockINTQL · terminal chart[/dim]")
    console.print()
    return True


def _guided_wallet_flow_pivot(*, token=None):
    if not sys.stdout.isatty():
        return
    try:
        should_pivot = click.confirm("Pivot to wallet-level stablecoin analysis now?", default=True)
    except Exception:
        return
    if not should_pivot:
        return
    address = click.prompt("Enter wallet address", type=str).strip()
    if not address:
        return
    console.print(f"[dim]Loading stablecoin history for {address[:20]}...[/]")
    history_result = api_get(
        f"/v1/eth/address/{address}/stablecoin-history",
        {"days": 30, "interval": "day", **({"token": token} if token else {})},
        timeout=90,
    )
    if "error" in history_result:
        output(history_result, agent=False, quiet=False)
    else:
        render_stablecoin_history_report(history_result)
    console.print(f"[dim]Loading stablecoin counterparties for {address[:20]}...[/]")
    cp_result = api_get(
        f"/v1/eth/address/{address}/stablecoin-counterparties",
        {"days": 30, "direction": "both", "limit": 25, **({"token": token} if token else {})},
        timeout=90,
    )
    if "error" in cp_result:
        output(cp_result, agent=False, quiet=False)
    else:
        render_stablecoin_counterparties_report(cp_result)


def render_wallet_stablecoin_chart(result, *, address, days=30, token=None):
    data = (result or {}).get("data") or {}
    rows = data.get("rows") or []
    if not rows:
        console.print("[yellow]No wallet stablecoin history found for that window.[/]")
        return

    grouped = {}
    for row in rows:
        symbol = row.get("token_symbol") or "UNKNOWN"
        grouped.setdefault(symbol, []).append(row)

    console.print()
    console.print("[bold cyan]Wallet Stablecoin Chart[/bold cyan]")
    console.print(f"[dim]{_short_addr(address, 18)} · {days}d · token={token or 'all'}[/dim]")
    console.print(f"[dim]{'─' * 76}[/dim]")
    for symbol, series in sorted(grouped.items()):
        ordered = sorted(series, key=lambda item: str(item.get("bucket") or ""))
        incoming = sum(_as_float(item.get("incoming_amount")) for item in ordered)
        outgoing = sum(_as_float(item.get("outgoing_amount")) for item in ordered)
        peak = max(
            max((_as_float(item.get("incoming_amount")) for item in ordered), default=0.0),
            max((_as_float(item.get("outgoing_amount")) for item in ordered), default=0.0),
            1.0,
        )
        console.print(
            f"[bold]{symbol:>5}[/bold]  [dim]in[/dim] {incoming:,.2f}  "
            f"[dim]out[/dim] {outgoing:,.2f}  [dim]net[/dim] {incoming - outgoing:,.2f}"
        )
        for row in ordered[-8:]:
            bucket = str(row.get("bucket") or "")[:10]
            in_amount = _as_float(row.get("incoming_amount"))
            out_amount = _as_float(row.get("outgoing_amount"))
            in_bar = _bar(in_amount, peak, width=12)
            out_bar = _bar(out_amount, peak, width=12)
            console.print(
                f"      [dim]{bucket}[/dim]  "
                f"[green]{in_bar:<12}[/green] [dim]{in_amount:>10,.2f}[/dim]  "
                f"[red]{out_bar:<12}[/red] [dim]{out_amount:>10,.2f}[/dim]"
            )
    console.print(f"[dim]{'─' * 76}[/dim]")
    console.print("[dim]green=inbound · red=outbound[/dim]")
    console.print("[dim]BlockINTQL · terminal chart[/dim]")
    console.print()


def render_wallet_stablecoin_balances_chart(result, *, address):
    data = (result or {}).get("data") or {}
    balances = (data.get("stablecoin_balances") or {})
    rows = []
    for symbol, details in balances.items():
        amount = _as_float((details or {}).get("balance"))
        rows.append((symbol, amount))

    if not rows or max((amount for _, amount in rows), default=0.0) <= 0:
        console.print("[yellow]No major stablecoin balances detected for that wallet.[/]")
        return

    peak = max(amount for _, amount in rows)
    total = _as_float(data.get("wallet_total_usd"))
    console.print()
    console.print("[bold cyan]Wallet Stablecoin Balances[/bold cyan]")
    console.print(f"[dim]{_short_addr(address, 18)} · current holdings[/dim]")
    console.print(f"[dim]{'─' * 76}[/dim]")
    for symbol, amount in sorted(rows, key=lambda item: item[1], reverse=True):
        bar = _bar(amount, peak)
        console.print(
            f"[bold]{symbol:<5}[/bold] {bar:<24} "
            f"[dim]balance[/dim] {amount:,.2f}"
        )
    console.print(f"[dim]{'─' * 76}[/dim]")
    console.print(f"[dim]tracked total[/dim] ${total:,.2f}")
    console.print("[dim]BlockINTQL · terminal chart[/dim]")
    console.print()


def render_counterparty_chart(result, *, address, token=None):
    data = (result or {}).get("data") or {}
    rows = data.get("rows") or []
    if not rows:
        console.print("[yellow]No stablecoin counterparties found for that wallet.[/]")
        return

    top_rows = rows[:10]
    peak = max((_as_float(row.get("total_amount")) for row in top_rows), default=0.0)
    console.print()
    console.print("[bold cyan]Counterparty Chart[/bold cyan]")
    console.print(f"[dim]{_short_addr(address, 18)} · token={token or 'all'}[/dim]")
    console.print(f"[dim]{'─' * 76}[/dim]")
    for row in top_rows:
        amount = _as_float(row.get("total_amount"))
        label = _short_addr(row.get("counterparty"), 18)
        direction = row.get("direction") or "both"
        symbol = row.get("token_symbol") or "UNKNOWN"
        bar = _bar(amount, peak)
        console.print(
            f"[bold]{label:<18}[/bold] {bar:<24} "
            f"[dim]{symbol} {direction}[/dim] ${amount:,.0f} [dim]tx[/dim] {int(row.get('tx_count') or 0)}"
        )
    console.print(f"[dim]{'─' * 76}[/dim]")
    console.print("[dim]BlockINTQL · terminal chart[/dim]")
    console.print()


def describe_data_source(source):
    labels = {
        "read_model_postgres": "warmed indexed summary",
        "postgres": "indexed postgres",
        "cache": "cached result",
        "node": "live node read",
        "node_fallback": "live node fallback",
        "postgres_unavailable": "indexed history temporarily unavailable",
        "postgres_stale": "indexed history catching up",
    }
    return labels.get(str(source or "").strip(), str(source or "unknown"))


def describe_warning(source, warning, result=None):
    text = str(warning or "").strip()
    if not text:
        return ""
    hot_wallet = bool((result or {}).get("hot_wallet"))
    history_mode = str((result or {}).get("history_mode") or "").strip().lower()
    if source in {"postgres_unavailable", "postgres_stale"} and hot_wallet and history_mode == "recent_window":
        return (
            "This wallet is too active for a full CLI ledger view. "
            "Use stats, stablecoin history, and counterparties for the strongest investigation path."
        )
    return text


def print_provenance(result):
    source = (result or {}).get("source") or "unknown"
    warning = describe_warning(source, (result or {}).get("warning"), result=result)
    console.print(f"  [dim]source   [/dim] {describe_data_source(source)}")
    if warning:
        console.print(f"  [yellow]warning  [/yellow] {warning}")


def print_next_steps(*commands):
    items = [item for item in commands if item]
    if not items:
        return
    console.print("  [dim]next     [/dim]")
    for command in items:
        console.print(f"    [cyan]$[/cyan] {command}")


def render_wallet_history_report(result):
    rows = list((result or {}).get("data") or [])
    address = (result or {}).get("address") or ""
    total = int((result or {}).get("count") or len(rows))
    window_days = int((result or {}).get("window_days") or 0)
    hot_wallet = bool((result or {}).get("hot_wallet"))
    hot_wallet_source = str((result or {}).get("hot_wallet_source") or "").strip()
    hot_wallet_entity = str((result or {}).get("hot_wallet_entity") or "").strip()
    hot_wallet_category = str((result or {}).get("hot_wallet_category") or "").strip()
    history_note = str((result or {}).get("history_note") or "").strip()
    hot_wallet_slice = (result or {}).get("hot_wallet_slice") or {}
    native_rows = [row for row in rows if row.get("type") == "native"]
    token_rows = [row for row in rows if row.get("type") == "token"]
    token_symbols = sorted({str(row.get("token_symbol") or "UNKNOWN") for row in token_rows})
    latest_block_time = str(rows[0].get("block_time") or "") if rows else ""

    console.print()
    console.print("  [bold cyan]WALLET HISTORY[/bold cyan]")
    console.print(f"  [dim]{'─' * 52}[/dim]")
    if rows:
        summary_bits = [
            f"{total} recent ledger events loaded",
            f"{len(native_rows)} native ETH" if native_rows else None,
            f"{len(token_rows)} token transfers" if token_rows else None,
            f"{len(token_symbols)} token symbols" if token_symbols else None,
        ]
        console.print(f"  [dim]summary  [/dim] {' · '.join(bit for bit in summary_bits if bit)}")
        if window_days > 0:
            console.print(f"  [dim]window   [/dim] recent {window_days}-day investigative slice")
        if hot_wallet:
            if hot_wallet_category:
                console.print(f"  [dim]profile  [/dim] [yellow]{hot_wallet_category.upper()} HOT WALLET[/yellow]")
            else:
                console.print("  [dim]profile  [/dim] [yellow]HOT WALLET[/yellow]")
            if hot_wallet_entity:
                console.print(f"  [dim]entity   [/dim] {hot_wallet_entity}")
            if hot_wallet_source:
                console.print(f"  [dim]badge    [/dim] {hot_wallet_source.replace('_', ' ')}")
        if history_note:
            console.print(f"  [dim]note     [/dim] {history_note}")
        if latest_block_time:
            console.print(f"  [dim]latest   [/dim] {latest_block_time}")
        if address:
            console.print(f"  [dim]wallet   [/dim] {address}")
    else:
        console.print("  [yellow]No recent Ethereum history is available for this wallet right now.[/yellow]")
        if window_days > 0:
            console.print(f"  [dim]window   [/dim] recent {window_days}-day investigative slice")
        if hot_wallet:
            if hot_wallet_category:
                console.print(f"  [dim]profile  [/dim] [yellow]{hot_wallet_category.upper()} HOT WALLET[/yellow]")
            else:
                console.print("  [dim]profile  [/dim] [yellow]HOT WALLET[/yellow]")
            if hot_wallet_entity:
                console.print(f"  [dim]entity   [/dim] {hot_wallet_entity}")
            if hot_wallet_source:
                console.print(f"  [dim]badge    [/dim] {hot_wallet_source.replace('_', ' ')}")
        if history_note:
            console.print(f"  [dim]note     [/dim] {history_note}")
        if address:
            console.print(f"  [dim]wallet   [/dim] {address}")
    print_provenance(result)

    if rows:
        table = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold cyan")
        table.add_column("When", style="dim", no_wrap=True)
        table.add_column("Type", no_wrap=True)
        table.add_column("Asset", no_wrap=True)
        table.add_column("Amount", justify="right")
        table.add_column("Route", overflow="fold")
        for row in rows[:8]:
            when = str(row.get("block_time") or "")[:16].replace("T", " ")
            entry_type = "token" if row.get("type") == "token" else "native"
            asset = str(row.get("token_symbol") or "ETH")
            amount = _as_float(row.get("amount"))
            route = f"{_short_addr(row.get('from_address'), 15)} → {_short_addr(row.get('to_address'), 15)}"
            table.add_row(when or "unknown", entry_type, asset, f"{amount:,.6f}", route)
        console.print(f"  [dim]{'─' * 52}[/dim]")
        console.print(table)
    elif hot_wallet_slice:
        stats = hot_wallet_slice.get("stats") or {}
        stablecoin_history = hot_wallet_slice.get("stablecoin_history") or {}
        counterparties = list((hot_wallet_slice.get("counterparties") or [])[:5])
        stats_data = (stats.get("data") or {}) if isinstance(stats, dict) else {}
        raw_stablecoin_rows = list((((stablecoin_history.get("data") or {}) if isinstance(stablecoin_history, dict) else {}).get("rows") or []))
        tx_total = int((((stats_data.get("transactions") or {}).get("total")) or 0))
        stablecoin_in = _as_float(((stats_data.get("volume") or {}).get("total_stablecoin_received_usd")))
        stablecoin_out = _as_float(((stats_data.get("volume") or {}).get("total_stablecoin_sent_usd")))
        stablecoin_by_token = {}
        for row in raw_stablecoin_rows:
            symbol = str(row.get("token_symbol") or "UNKNOWN")
            bucket = stablecoin_by_token.setdefault(symbol, {"incoming_amount": 0.0, "outgoing_amount": 0.0, "net_amount": 0.0})
            bucket["incoming_amount"] += _as_float(row.get("incoming_amount"))
            bucket["outgoing_amount"] += _as_float(row.get("outgoing_amount"))
            bucket["net_amount"] += _as_float(row.get("net_amount"))
        stablecoin_rows = [
            {
                "token_symbol": symbol,
                "incoming_amount": values["incoming_amount"],
                "outgoing_amount": values["outgoing_amount"],
                "net_amount": values["net_amount"],
            }
            for symbol, values in stablecoin_by_token.items()
        ]
        stablecoin_rows.sort(key=lambda row: abs(_as_float(row.get("net_amount"))) + _as_float(row.get("incoming_amount")) + _as_float(row.get("outgoing_amount")), reverse=True)
        if tx_total or stablecoin_rows or counterparties:
            console.print(f"  [dim]{'─' * 52}[/dim]")
            console.print("  [bold cyan]SERVICE-WALLET TRIAGE[/bold cyan]")
            if tx_total:
                console.print(
                    f"  [dim]triage   [/dim] {tx_total} wallet events in the current stats window · "
                    f"${stablecoin_in:,.2f} stablecoins in vs ${stablecoin_out:,.2f} out"
                )
            if stablecoin_rows:
                flow_table = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold cyan")
                flow_table.add_column("Token", no_wrap=True)
                flow_table.add_column("Inbound", justify="right")
                flow_table.add_column("Outbound", justify="right")
                flow_table.add_column("Net", justify="right")
                for row in stablecoin_rows[:4]:
                    flow_table.add_row(
                        str(row.get("token_symbol") or "UNKNOWN"),
                        f"{_as_float(row.get('incoming_amount')):,.2f}",
                        f"{_as_float(row.get('outgoing_amount')):,.2f}",
                        f"{_as_float(row.get('net_amount')):,.2f}",
                    )
                console.print(flow_table)
            if counterparties:
                cp = counterparties[0]
                console.print(
                    f"  [dim]lead cp  [/dim] {_short_addr(cp.get('counterparty'), 18)} · "
                    f"{cp.get('token_symbol') or 'UNKNOWN'} · ${_as_float(cp.get('total_amount')):,.2f}"
                )

    console.print(f"  [dim]{'─' * 52}[/dim]")
    next_one = f"blockintql history {address} --days 1" if address and hot_wallet else (f"blockintql stablecoins balances {address}" if address else None)
    next_two = f"blockintql stablecoins counterparties {address}" if address and hot_wallet else (f"blockintql screen {address}" if address else None)
    if token_symbols and any(symbol in {"USDC", "USDT", "DAI", "BUSD"} for symbol in token_symbols):
        next_one = f"blockintql stablecoins counterparties {address}" if address else next_one
    print_next_steps(next_one, next_two)
    console.print("  [dim]BlockINTQL · recent activity story, not just raw transfers[/dim]")
    console.print()


def render_stablecoin_balances_report(result):
    data = (result or {}).get("data") or {}
    address = data.get("address") or (result or {}).get("address") or ""
    balances = data.get("stablecoin_balances") or {}
    total = _as_float(data.get("wallet_total_usd"))
    rows = []
    for symbol, details in balances.items():
        amount = _as_float((details or {}).get("balance"))
        if amount > 0:
            rows.append((symbol, amount, details or {}))
    rows.sort(key=lambda item: item[1], reverse=True)

    console.print()
    console.print("  [bold cyan]STABLECOIN BALANCES[/bold cyan]")
    console.print(f"  [dim]{'─' * 52}[/dim]")
    if rows:
        top_symbol, top_amount, _ = rows[0]
        concentration = (top_amount / sum(amount for _, amount, _ in rows)) if rows else 0.0
        summary = f"Tracked stablecoin exposure is about ${total:,.2f}."
        if len(rows) == 1:
            summary += f" The wallet is concentrated in {top_symbol}."
        elif concentration >= 0.7:
            summary += f" {top_symbol} dominates the balance mix."
        else:
            summary += f" Exposure is spread across {len(rows)} tracked stablecoins."
        console.print(f"  [dim]summary  [/dim] {summary}")
        if address:
            console.print(f"  [dim]wallet   [/dim] {address}")
    else:
        console.print("  [yellow]No major stablecoin balances are currently detected for this wallet.[/yellow]")
        if address:
            console.print(f"  [dim]wallet   [/dim] {address}")
    print_provenance(result)

    coverage = (data.get("coverage") or {}).get("coverage_note")
    if coverage:
        console.print(f"  [dim]coverage [/dim] {coverage}")

    if rows:
        table = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold cyan")
        table.add_column("Token", no_wrap=True)
        table.add_column("Balance", justify="right")
        table.add_column("Share", justify="right")
        table.add_column("Contract", overflow="fold")
        total_units = sum(amount for _, amount, _ in rows) or 1.0
        for symbol, amount, details in rows[:8]:
            share = (amount / total_units) * 100.0
            table.add_row(symbol, f"{amount:,.2f}", f"{share:,.1f}%", _short_addr(details.get("contract"), 18))
        console.print(f"  [dim]{'─' * 52}[/dim]")
        console.print(table)

    console.print(f"  [dim]{'─' * 52}[/dim]")
    print_next_steps(
        f"blockintql stablecoins history {address} --days 30" if address else None,
        f"blockintql stablecoins counterparties {address}" if address else None,
    )
    console.print("  [dim]BlockINTQL · wallet holdings framed for triage[/dim]")
    console.print()


def render_stablecoin_history_report(result):
    data = (result or {}).get("data") or {}
    address = data.get("address") or (result or {}).get("address") or ""
    rows = list(data.get("rows") or [])
    grouped = {}
    for row in rows:
        symbol = str(row.get("token_symbol") or "UNKNOWN")
        grouped.setdefault(symbol, []).append(row)

    console.print()
    console.print("  [bold cyan]STABLECOIN HISTORY[/bold cyan]")
    console.print(f"  [dim]{'─' * 52}[/dim]")
    if rows:
        token_count = len(grouped)
        total_in = sum(_as_float(row.get("incoming_amount")) for row in rows)
        total_out = sum(_as_float(row.get("outgoing_amount")) for row in rows)
        summary = (
            f"Loaded {len(rows)} {data.get('interval', 'bucket')} buckets across {token_count} token lane(s). "
            f"Inbound {total_in:,.2f} vs outbound {total_out:,.2f}."
        )
        console.print(f"  [dim]summary  [/dim] {summary}")
        if address:
            console.print(f"  [dim]wallet   [/dim] {address}")
        console.print(f"  [dim]window   [/dim] {data.get('days', '?')}d · token={data.get('token') or 'all'}")
    else:
        console.print("  [yellow]No stablecoin time-series rows are available for this window.[/yellow]")
        if address:
            console.print(f"  [dim]wallet   [/dim] {address}")
    print_provenance(result)

    if rows:
        ranked = []
        for symbol, series in grouped.items():
            inbound = sum(_as_float(item.get("incoming_amount")) for item in series)
            outbound = sum(_as_float(item.get("outgoing_amount")) for item in series)
            ranked.append((symbol, inbound, outbound, inbound - outbound, len(series)))
        ranked.sort(key=lambda item: abs(item[3]), reverse=True)

        table = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold cyan")
        table.add_column("Token", no_wrap=True)
        table.add_column("Inbound", justify="right")
        table.add_column("Outbound", justify="right")
        table.add_column("Net", justify="right")
        table.add_column("Buckets", justify="right")
        for symbol, inbound, outbound, net, bucket_count in ranked[:8]:
            net_style = "green" if net >= 0 else "red"
            table.add_row(symbol, f"{inbound:,.2f}", f"{outbound:,.2f}", f"[{net_style}]{net:,.2f}[/{net_style}]", str(bucket_count))
        console.print(f"  [dim]{'─' * 52}[/dim]")
        console.print(table)

    console.print(f"  [dim]{'─' * 52}[/dim]")
    print_next_steps(
        f"blockintql chart wallet-stablecoins {address} --days {data.get('days', 30)}" if address else None,
        f"blockintql stablecoins counterparties {address}" if address else None,
    )
    console.print("  [dim]BlockINTQL · stablecoin movement summarized for investigation[/dim]")
    console.print()


def render_stablecoin_counterparties_report(result):
    data = (result or {}).get("data") or {}
    address = data.get("address") or (result or {}).get("address") or ""
    rows = list(data.get("rows") or data.get("counterparties") or [])
    inbound_rows = [row for row in rows if str(row.get("direction") or "").lower() == "inbound"]
    outbound_rows = [row for row in rows if str(row.get("direction") or "").lower() == "outbound"]

    console.print()
    console.print("  [bold cyan]STABLECOIN COUNTERPARTIES[/bold cyan]")
    console.print(f"  [dim]{'─' * 52}[/dim]")
    if rows:
        top_row = max(rows, key=lambda item: _as_float(item.get("total_amount")))
        summary = (
            f"Loaded {len(rows)} counterparty lanes over {data.get('days', '?')}d. "
            f"{len(inbound_rows)} inbound and {len(outbound_rows)} outbound relationships surfaced."
        )
        console.print(f"  [dim]summary  [/dim] {summary}")
        console.print(
            f"  [dim]leader   [/dim] {_short_addr(top_row.get('counterparty'), 18)} · "
            f"{top_row.get('token_symbol') or 'UNKNOWN'} · ${_as_float(top_row.get('total_amount')):,.2f}"
        )
        if address:
            console.print(f"  [dim]wallet   [/dim] {address}")
    else:
        console.print("  [yellow]No stablecoin counterparties are available for this wallet and filter set.[/yellow]")
        if address:
            console.print(f"  [dim]wallet   [/dim] {address}")
    print_provenance(result)

    if rows:
        table = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold cyan")
        table.add_column("Counterparty", overflow="fold")
        table.add_column("Dir", no_wrap=True)
        table.add_column("Token", no_wrap=True)
        table.add_column("Amount", justify="right")
        table.add_column("Tx", justify="right")
        for row in rows[:8]:
            direction = str(row.get("direction") or "both")
            direction_style = "green" if direction == "inbound" else "red" if direction == "outbound" else "white"
            table.add_row(
                _short_addr(row.get("counterparty"), 18),
                f"[{direction_style}]{direction}[/{direction_style}]",
                str(row.get("token_symbol") or "UNKNOWN"),
                f"{_as_float(row.get('total_amount')):,.2f}",
                str(int(row.get("tx_count") or 0)),
            )
        console.print(f"  [dim]{'─' * 52}[/dim]")
        console.print(table)

    console.print(f"  [dim]{'─' * 52}[/dim]")
    print_next_steps(
        f"blockintql chart counterparties {address}" if address else None,
        f"blockintql screen {address}" if address else None,
    )
    console.print("  [dim]BlockINTQL · counterparties prioritized for follow-up[/dim]")
    console.print()


def render_wallet_stats_report(result):
    data = (result or {}).get("data") or {}
    address = data.get("address") or (result or {}).get("address") or ""
    transactions = data.get("transactions") or {}
    volume = data.get("volume") or {}
    activity = data.get("activity") or {}
    total_txs = int(transactions.get("total") or 0)
    sent_txs = int(transactions.get("sent") or 0)
    received_txs = int(transactions.get("received") or 0)
    total_sent_eth = _as_float(volume.get("total_sent_eth"))
    total_received_eth = _as_float(volume.get("total_received_eth"))
    stablecoin_received = _as_float(volume.get("total_stablecoin_received_usd"))
    stablecoin_sent = _as_float(volume.get("total_stablecoin_sent_usd"))
    window_days = int(data.get("summary_window_days") or 0)

    console.print()
    console.print("  [bold cyan]WALLET STATS[/bold cyan]")
    console.print(f"  [dim]{'─' * 52}[/dim]")
    if total_txs > 0:
        summary = (
            f"Loaded {total_txs} transactions with {sent_txs} outbound and {received_txs} inbound events. "
            f"Native flow is {total_received_eth:,.4f} ETH in vs {total_sent_eth:,.4f} ETH out."
        )
        if stablecoin_received > 0 or stablecoin_sent > 0:
            summary += f" Stablecoins show ${stablecoin_received:,.2f} received vs ${stablecoin_sent:,.2f} sent."
        console.print(f"  [dim]summary  [/dim] {summary}")
    else:
        console.print("  [yellow]No wallet stats are available for this address right now.[/yellow]")
    if address:
        console.print(f"  [dim]wallet   [/dim] {address}")
    if window_days > 0:
        console.print(f"  [dim]window   [/dim] rolling {window_days}-day summary for fast triage")
    print_provenance(result)

    first_tx = activity.get("first_transaction")
    last_tx = activity.get("last_transaction")
    if first_tx or last_tx:
        console.print(
            f"  [dim]activity [/dim] first={first_tx or 'unknown'} · last={last_tx or 'unknown'}"
        )

    table = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold cyan")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("Contract interactions", str(int(transactions.get("contract_interactions") or 0)))
    table.add_row("Unique recipients", str(int(activity.get("unique_counterparties_sent") or 0)))
    table.add_row("Unique senders", str(int(activity.get("unique_counterparties_received") or 0)))
    table.add_row("Token transfers", str(int(activity.get("total_token_transfers") or 0)))
    table.add_row("Tokens used", str(int(activity.get("unique_tokens_used") or 0)))
    table.add_row("Gas spent (ETH)", f"{_as_float(volume.get('total_gas_spent_eth')):,.6f}")
    console.print(f"  [dim]{'─' * 52}[/dim]")
    console.print(table)

    console.print(f"  [dim]{'─' * 52}[/dim]")
    print_next_steps(
        f"blockintql history {address}" if address else None,
        f"blockintql stablecoins counterparties {address}" if address else None,
    )
    console.print("  [dim]BlockINTQL · wallet summary framed for triage and follow-up[/dim]")
    console.print()


def workspace_launch_url(manifest):
    workspace = manifest.get("workspace", manifest) if isinstance(manifest, dict) else {}
    runtime = manifest.get("runtime", {}) if isinstance(manifest, dict) else {}
    entrypoints = runtime.get("entrypoints", {}) if isinstance(runtime, dict) else {}
    capabilities = manifest.get("capabilities", {}) if isinstance(manifest, dict) else {}
    return (
        entrypoints.get("explorer_url")
        if capabilities.get("graph_explorer")
        else None
    ) or entrypoints.get("graph_url") or workspace.get("graph_url") or workspace.get("access_url")


def rank_workspaces(workspaces):
    items = list(workspaces or [])
    active = [item for item in items if item.get("status") not in {"destroyed", "failed"}]
    return sorted(
        active or items,
        key=lambda item: (
            int((item.get("activity") or {}).get("activity_score", 0)),
            str((item.get("activity") or {}).get("last_meaningful_at") or ""),
            str(item.get("state_updated_at") or item.get("updated_at") or ""),
        ),
        reverse=True,
    )


def classify_goal_family(goal_text=""):
    text = (goal_text or "").strip().lower()
    if not text:
        return "general"
    if any(term in text for term in ["chart", "plot", "line chart", "bar chart", "time series", "trend"]):
        return "chart"
    if any(term in text for term in ["trace", "follow funds", "follow the money", "node-to-node", "node to node", "hop", "hops", "network map", "counterparty graph"]):
        return "trace"
    if any(term in text for term in ["prediction market", "prediction markets", "polymarket", "event market", "betting market"]):
        return "prediction"
    if any(term in text for term in ["compliance", "screening", "screen", "sanctions", "ofac", "aml", "risk", "counterparty"]):
        return "compliance"
    if any(term in text for term in ["stablecoin", "usdc", "usdt", "dai", "busd", "flows", "counterparties", "wallet history"]):
        return "stablecoins"
    return "general"


def choose_resume_candidate(workspaces, seed_address=None, goal_text=""):
    ranked = rank_workspaces(workspaces)
    if not ranked:
        return None
    normalized_goal = (goal_text or "").strip().lower()
    requested_family = classify_goal_family(normalized_goal)
    for item in ranked:
        context = item.get("workspace_context") or {}
        existing_seed = (context.get("seed_address") or "").strip().lower()
        existing_goal = (context.get("goal") or "").strip().lower()
        existing_family = classify_goal_family(existing_goal)
        family_matches = requested_family in {"", "general"} or existing_family == requested_family
        if seed_address and existing_seed == seed_address.strip().lower() and family_matches:
            return item
        if normalized_goal and existing_goal and normalized_goal in existing_goal and family_matches:
            return item
    if not seed_address and not normalized_goal:
        return ranked[0]
    return None


def describe_resume_reason(workspace, seed_address=None, goal_text=""):
    context = workspace.get("workspace_context") or {}
    activity = workspace.get("activity") or {}
    existing_seed = (context.get("seed_address") or "").strip().lower()
    requested_seed = (seed_address or "").strip().lower()
    existing_goal = (context.get("goal") or "").strip().lower()
    requested_goal = (goal_text or "").strip().lower()
    if requested_seed and existing_seed and requested_seed == existing_seed:
        return "Resumed because this workspace already tracks the same seed address."
    if requested_goal and existing_goal and requested_goal in existing_goal:
        return "Resumed because this workspace already matches the current investigation goal."
    if int(activity.get("activity_score", 0)) > 0:
        return "Resumed because it has the strongest saved investigation activity for this API key."
    return "Resumed because it is the best available workspace for this API key."


def recommended_workspace_payload(workspace):
    activity = workspace.get("activity") or {}
    return {
        "workspace_id": workspace.get("workspace_id"),
        "name": workspace.get("name"),
        "status": workspace.get("status"),
        "activity": activity,
        "reason": workspace.get("reason"),
        "workspace_context": workspace.get("workspace_context") or {},
    }


def _resolve_workspace_id_or_exit(workspace_id, *, agent=False, quiet=False):
    resolved = str(workspace_id or "").strip()
    if resolved:
        return resolved
    data = api_get("/v1/workspaces", params={"limit": 10}, require_auth=True)
    workspaces = data.get("workspaces") if isinstance(data, dict) else None
    if not workspaces:
        raise click.UsageError(
            "No workspace_id was provided and no saved workspaces were found.\n"
            "Start here:\n"
            "  blockintql workspace create \"My first case\" --chain ethereum\n"
            "Or list existing:\n"
            "  blockintql workspace list"
        )
    candidate = choose_resume_candidate(workspaces)
    candidate_id = (candidate or {}).get("workspace_id")
    if not candidate_id:
        raise click.UsageError(
            "Unable to auto-select a workspace.\n"
            "Run one of:\n"
            "  blockintql workspace list\n"
            "  blockintql workspace recommended"
        )
    if not quiet and not agent:
        console.print(f"[dim]No workspace_id provided; using {candidate_id} (recommended).[/]")
    return candidate_id


def summarize_plan_steps(steps):
    items = []
    for idx, step in enumerate(steps or [], start=1):
        title = step.get("title") or step.get("capability_id") or f"step-{idx}"
        surface = step.get("surface") or "unknown"
        optional = " optional" if step.get("optional") else ""
        reason = step.get("reason") or ""
        items.append(
            {
                "idx": idx,
                "title": title,
                "surface": surface,
                "optional": optional,
                "reason": reason,
            }
        )
    return items


def materialize_cli_command(command, *, address="", execution_profile=None):
    cmd = (command or "").strip()
    if not cmd:
        return None

    def _strip_default_chain_arg(value):
        text = str(value or "")
        text = text.replace(" --chain ethereum", "")
        text = text.replace(" --chain auto", "")
        return text

    cmd = _strip_default_chain_arg(cmd)
    if address:
        if "<address>" in cmd:
            if cmd.startswith("blockintql verdict"):
                cmd = cmd.replace("<address>", f"--address {address}")
            elif cmd.startswith("blockintql screen"):
                cmd = cmd.replace("<address>", f"--address {address}")
            elif cmd.startswith("blockintql history"):
                cmd = cmd.replace("<address>", f"--address {address}")
            else:
                cmd = cmd.replace("<address>", address)
        elif cmd.startswith("blockintql verdict") and "--address" not in cmd:
            cmd = f"{cmd} --address {address}"
        elif cmd.startswith("blockintql screen") and "--address" not in cmd:
            cmd = f"{cmd} --address {address}"
        elif cmd.startswith("blockintql history") and "--address" not in cmd:
            cmd = f"{cmd} --address {address}"
        elif cmd.startswith("blockintql analyze") and "--address" not in cmd:
            cmd = f"{cmd} --address {address}"
    cmd = _strip_default_chain_arg(cmd)
    if execution_profile and "--mode" not in cmd:
        if cmd.startswith("blockintql prediction market analysis"):
            cmd = f"{cmd} --mode {execution_profile}"
        elif cmd.startswith("blockintql ask "):
            cmd = f"{cmd} --mode {execution_profile}"
    return cmd


def continue_plan_instructions(data):
    brief = data.get("investigation_brief") or {}
    selected_profile = data.get("selected_execution_profile") or {}
    execution_profile = selected_profile.get("id")
    address = (brief.get("seed_address") or data.get("address") or "").strip()
    goal_text = brief.get("goal") or ""
    goal_family = classify_goal_family(goal_text)
    command_steps = []
    seen_commands = set()
    workspace_needed = False

    for step in data.get("steps") or []:
        capability_id = step.get("capability_id")
        surface = step.get("surface")
        execution = step.get("execution")
        if capability_id in {"workspace_create", "graph_build"} or surface == "workspace" or execution == "interactive":
            workspace_needed = True
            continue
        command = materialize_cli_command(
            step.get("cli_command"),
            address=address,
            execution_profile=execution_profile,
        )
        if command and command not in seen_commands:
            command_steps.append({
                "title": step.get("title") or capability_id or "Step",
                "command": command,
                "optional": bool(step.get("optional")),
                "surface": surface,
            })
            seen_commands.add(command)

    if (
        data.get("recommended_surface") == "workspace"
        or data.get("executed_workspace")
        or data.get("resume_workspace")
        or data.get("recommended_workspace")
    ):
        workspace_needed = True

    workspace_actions = []
    if workspace_needed:
        if goal_family == "compliance":
            workspace_actions = [
                "Click Load to open the workspace shell for this case",
                "Click the seed node to inspect the wallet in the right-hand evidence panel",
                "Use the expansion button only when you want to grow the graph beyond the seed wallet",
                "Use Sync Artifacts and Hydrate Graph only after a completed expansion finishes",
            ]
        elif goal_family == "trace":
            workspace_actions = [
                "Click Load to open the seeded graph for this case",
                "Click the seed node to inspect wallet evidence before expanding the graph",
                "Run an expansion only when you want direct counterparties or traced node-to-node relationships",
                "Use Sync Artifacts and Hydrate Graph only after a completed expansion finishes",
            ]
        else:
            workspace_actions = [
                "Click Load to open the workspace shell for this case",
                "Run the suggested expansion",
                "Sync artifacts after a completed result is available",
                "Hydrate the graph to load the evidence surface",
            ]

    return command_steps, workspace_actions


def format_money(value):
    if value is None:
        return None
    try:
        return f"${float(value):.2f}"
    except Exception:
        return str(value)

def output(data, agent, quiet):
    if agent or not sys.stdout.isatty():
        click.echo(json.dumps(data, indent=2, default=str))
        return
    if "error" in data:
        err_console.print(f"  [red]✗[/red] {data['error']}")
        return
    payment_info = data.get("payment") if isinstance(data, dict) else None
    compensation = payment_info.get("compensation") if isinstance(payment_info, dict) else None
    if compensation and not quiet:
        token = compensation.get("token")
        mode = compensation.get("mode", "claim_token")
        reason = compensation.get("reason", "degraded_result")
        status = compensation.get("status", "granted")
        if token:
            save_last_compensation_token(token)
            console.print()
            console.print("  [bold yellow]COMPENSATION[/bold yellow]")
            console.print(f"  [dim]{'─' * 52}[/dim]")
            console.print(f"  [dim]status   [/dim] {status}")
            console.print(f"  [dim]mode     [/dim] {mode}")
            console.print(f"  [dim]reason   [/dim] {reason}")
            console.print(f"  [dim]token    [/dim] {token}")
            console.print(f"  [dim]claim    [/dim] blockintql compensation claim --token {token}")
            console.print(f"  [dim]{'─' * 52}[/dim]")

    if isinstance(data, dict) and data.get("narrative") and isinstance(data.get("blockintql"), dict):
        _render_grounded_chat_box(data)
        return

    if data.get("surface") == "graph_shell" and data.get("shell_spec"):
        console.print()
        console.print("  [bold cyan]GRAPH SHELL[/bold cyan]")
        console.print(f"  [dim]{'─' * 52}[/dim]")
        if data.get("prompt"):
            console.print(f"  [dim]prompt   [/dim] {data.get('prompt')}")
        if data.get("seed"):
            console.print(f"  [dim]seed     [/dim] {data.get('seed')}")
        console.print(f"  [dim]spec     [/dim] {shell_spec_summary(data.get('shell_spec') or {})}")
        matched_rules = data.get("matched_rules") or []
        if matched_rules:
            console.print(f"  [dim]matched  [/dim] {', '.join(matched_rules)}")
        if data.get("explorer_url"):
            console.print(f"  [dim]explorer [/dim] {data.get('explorer_url')}")
        console.print("  [dim]next     [/dim] blockintql graph shell refine \"Make the drawer wider\"")
        console.print(f"  [dim]{'─' * 52}[/dim]")
        console.print("  [dim]Deterministic shell spec · no arbitrary generated UI[/dim]")
        console.print()
        return

    if "reply" in data and "session_id" in data:
        console.print()
        console.print("  [bold cyan]BLOCKINTQL CHAT[/bold cyan]")
        console.print(f"  [dim]{'─' * 52}[/dim]")
        console.print(f"  [dim]session  [/dim] {data.get('session_id')}")
        console.print(f"  [dim]credits  [/dim] {data.get('credits_charged', 0)}")
        if (data.get("session") or {}).get("seed_address"):
            console.print(f"  [dim]seed     [/dim] {(data.get('session') or {}).get('seed_address')}")
        console.print(f"  [dim]scope    [/dim] {data.get('scope', 'unknown')}")
        console.print(f"  [dim]{'─' * 52}[/dim]")
        console.print(f"  {data.get('reply')}")
        methodology = data.get("methodology") or {}
        risk = methodology.get("risk_assessment") or {}
        patterns = methodology.get("laundering_patterns") or []
        if risk.get("band") or patterns:
            console.print(f"  [dim]{'─' * 52}[/dim]")
            if risk.get("band"):
                console.print(f"  [dim]method   [/dim] {risk.get('band')} · score {risk.get('score')}")
            if patterns:
                console.print(f"  [dim]patterns [/dim] {', '.join(item.get('label') or item.get('id') for item in patterns[:4])}")
        session = data.get("session") or {}
        seed = session.get("seed_address")
        if seed:
            console.print(f"  [dim]{'─' * 52}[/dim]")
            console.print("  [bold]quick actions[/bold]")
            console.print(f"    $ blockintql stablecoins counterparties {seed} --days 30")
            console.print(f"    $ blockintql chart counterparties {seed} --days 30")
            console.print(f"    $ blockintql chart wallet-stablecoins {seed} --days 30")
            console.print(f"    $ blockintql workspace chat --goal \"Go deeper on top counterparties for {seed}\"")
        console.print(f"  [dim]{'─' * 52}[/dim]")
        console.print("  [dim]BlockINTQL · compliance + blockchain forensics only[/dim]")
        console.print()
        return

    if "provider" in data and data.get("provider") == "openai_images":
        def _save_image_from_b64(image_b64: str):
            try:
                raw = base64.b64decode(image_b64)
                out_path = os.path.join(tempfile.gettempdir(), f"blockintql-image-{int(time.time())}.png")
                with open(out_path, "wb") as f:
                    f.write(raw)
                return out_path
            except Exception:
                return None

        def _render_inline_image(image_b64: str):
            try:
                term_program = str(os.environ.get("TERM_PROGRAM", "")).lower()
                if "iterm" in term_program:
                    click.echo(f"\033]1337;File=inline=1;width=auto;height=auto;preserveAspectRatio=1:{image_b64}\a")
                    return True
            except Exception:
                return False
            return False

        def _inline_render_hint():
            term_program = str(os.environ.get("TERM_PROGRAM", "")).lower()
            term = str(os.environ.get("TERM", "")).lower()
            if "iterm" in term_program:
                return "iTerm inline protocol detected."
            if "xterm-kitty" in term:
                return "Kitty inline protocol available."
            if "wezterm" in term_program:
                return "WezTerm inline protocol available."
            return "No native inline image protocol detected in this terminal."

        console.print()
        console.print("  [bold cyan]IMAGE GENERATED[/bold cyan]")
        console.print(f"  [dim]{'─' * 52}[/dim]")
        console.print(f"  [dim]model    [/dim] {data.get('model')}")
        console.print(f"  [dim]size     [/dim] {data.get('size')}")
        console.print(f"  [dim]quality  [/dim] {data.get('quality')}")
        console.print(f"  [dim]style    [/dim] {data.get('style')}")
        console.print(f"  [dim]credits  [/dim] {data.get('credits_charged', 0)}")
        if data.get("revised_prompt"):
            console.print(f"  [dim]prompt   [/dim] {data.get('revised_prompt')}")
        else:
            console.print(f"  [dim]prompt   [/dim] {data.get('prompt')}")
        console.print(f"  [dim]{'─' * 52}[/dim]")
        image_b64 = data.get("image_base64")
        saved_path = _save_image_from_b64(image_b64) if image_b64 else None
        rendered_inline = _render_inline_image(image_b64) if image_b64 else False
        rendered_mode = "iterm-inline" if rendered_inline else None
        if not rendered_inline and saved_path:
            term_program = str(os.environ.get("TERM_PROGRAM", "")).lower()
            term = str(os.environ.get("TERM", "")).lower()
            try:
                if "xterm-kitty" in term and shutil.which("kitty"):
                    subprocess.run(
                        ["kitty", "+kitten", "icat", "--stdin", "no", saved_path],
                        check=False,
                        stdout=sys.stdout,
                        stderr=subprocess.DEVNULL,
                    )
                    rendered_inline = True
                    rendered_mode = "kitty-icat"
                elif "wezterm" in term_program and shutil.which("wezterm"):
                    subprocess.run(
                        ["wezterm", "imgcat", saved_path],
                        check=False,
                        stdout=sys.stdout,
                        stderr=subprocess.DEVNULL,
                    )
                    rendered_inline = True
                    rendered_mode = "wezterm-imgcat"
                elif os.environ.get("BLOCKINTQL_IMAGE_ASCII_PREVIEW", "").strip().lower() in {"1", "true", "yes", "on"} and shutil.which("chafa"):
                    subprocess.run(
                        ["chafa", saved_path, "--size", "80x32"],
                        check=False,
                        stdout=sys.stdout,
                        stderr=subprocess.DEVNULL,
                    )
                    rendered_inline = True
                    rendered_mode = "chafa-preview"
            except Exception:
                pass
        if data.get("image_url"):
            console.print(f"  [dim]image    [/dim] {data.get('image_url')}")
        elif saved_path:
            console.print(f"  [dim]image    [/dim] {saved_path}")
        elif data.get("image_data_uri"):
            preview = str(data.get("image_data_uri"))
            console.print(f"  [dim]image    [/dim] {preview[:140]}...")
        else:
            console.print("  [yellow]No image payload returned by provider.[/yellow]")
        if rendered_inline:
            console.print(f"  [dim]inline   [/dim] rendered in terminal ({rendered_mode or 'inline'})")
        elif saved_path:
            console.print(f"  [dim]saved    [/dim] {saved_path}")
        console.print(f"  [dim]{'─' * 52}[/dim]")
        console.print(f"  [dim]display  [/dim] {_inline_render_hint()}")
        console.print("  [dim]tip      [/dim] For crisp inline previews, use iTerm2/Kitty/WezTerm native image support.")
        console.print("  [dim]tip      [/dim] ASCII preview is optional: set BLOCKINTQL_IMAGE_ASCII_PREVIEW=true")
        console.print("  [dim]tip      [/dim] File path output is always a lossless fallback.")
        console.print()
        return

    # ── VERDICT ────────────────────────────────────────────────────────────────
    if "verdict" in data and "risk_score" in data:
        v = data["verdict"]
        color = verdict_color(v)
        risk = int(data.get("risk_score", 0))
        safe = data.get("safe", False)

        console.print()
        console.print(f"  [bold {color}]{v}[/bold {color}]  [dim]·[/dim]  [{color}]{risk}/100 risk[/{color}]  [dim]·[/dim]  [dim]{'SAFE' if safe else 'DO NOT TRANSACT'}[/dim]")
        console.print(f"  [dim]{'─' * 52}[/dim]")

        if not quiet:
            addr = data.get('address') or data.get('subject','')
            console.print(f"  [dim]address [/dim] {addr}")
            console.print(f"  [dim]chain   [/dim] {data.get('chain','')}")
            console.print(f"  [dim]entity  [/dim] {data.get('entity') or 'Unknown'}")
            if data.get("risk_indicators"):
                console.print(f"  [dim]flags   [/dim] [{color}]{', '.join(data['risk_indicators'])}[/{color}]")
            if data.get("action"):
                console.print(f"  [dim]action  [/dim] {data['action']}")
            if data.get("provider_data"):
                pd = data["provider_data"]
                console.print(f"  [dim]{'─' * 52}[/dim]")
                console.print(f"  [dim]{pd.get('provider','').upper()} · local · key never sent to BlockINTQL[/dim]")
                if pd.get("decision_source"):
                    console.print(f"  [dim]source  [/dim] {pd.get('decision_source')}")
                if pd.get("raw_vendor_data_seen_locally") is True:
                    console.print(f"  [dim]privacy [/dim] raw vendor response seen locally only")
                if pd.get("raw_vendor_data_sent_to_blockintql") is False:
                    console.print(f"  [dim]sharing [/dim] raw vendor response not sent to BlockINTQL")
                if pd.get("error"):
                    console.print(f"  [red]vendor  [/red] {pd.get('error')}")
                if pd.get("vendor_verdict"):
                    console.print(f"  [dim]vendor  [/dim] {pd.get('vendor_verdict')}")
                if pd.get("vendor_category"):
                    console.print(f"  [dim]label   [/dim] {pd.get('vendor_category')}")
                if pd.get("entity_name"):
                    console.print(f"  [dim]entity  [/dim] {pd['entity_name']}")
                if pd.get("canonical_category"):
                    console.print(f"  [dim]class   [/dim] {pd.get('canonical_category')}")
                console.print(f"  [dim]risk    [/dim] {pd.get('risk_score',0)}/100")
                if pd.get("recommended_verdict"):
                    console.print(f"  [dim]policy  [/dim] {pd.get('recommended_verdict')} · {pd.get('confidence','unknown')} confidence")
                if pd.get("mapping_rule"):
                    console.print(f"  [dim]mapping [/dim] {pd.get('mapping_rule')}")
                if pd.get("sanctions_hit"):
                    console.print(f"  [red]  ⚠  SANCTIONS HIT[/red]")
                elif pd.get("reasons"):
                    console.print(f"  [dim]why     [/dim] {pd.get('reasons')[0]}")
            if data.get("consensus"):
                cs = data.get("consensus") or {}
                vote_split = cs.get("vote_split") or {}
                console.print(f"  [dim]{'─' * 52}[/dim]")
                console.print("  [dim]SONAR CONSENSUS · public-safe contract[/dim]")
                if cs.get("mode"):
                    console.print(f"  [dim]mode    [/dim] {cs.get('mode')}")
                if cs.get("decision"):
                    console.print(f"  [dim]decision[/dim] {cs.get('decision')}")
                if cs.get("confidence"):
                    console.print(f"  [dim]conf    [/dim] {cs.get('confidence')}")
                if vote_split:
                    console.print(
                        f"  [dim]votes   [/dim] block={vote_split.get('block', 0)} "
                        f"review={vote_split.get('review', 0)} clear={vote_split.get('clear', 0)}"
                    )
                vote_rows = cs.get("votes") or []
                if isinstance(vote_rows, list) and vote_rows:
                    for row in vote_rows[:3]:
                        agent = str(row.get("agent") or row.get("codename") or "agent")
                        vote = str(row.get("vote") or "").upper()
                        role = str(row.get("role") or "")
                        if role:
                            console.print(f"  [dim]agent   [/dim] {agent} · {vote} · {role}")
                        else:
                            console.print(f"  [dim]agent   [/dim] {agent} · {vote}")
                policy_mapping = cs.get("policy_mapping") or {}
                vendor_map = policy_mapping.get("vendor_to_canonical") or {}
                if vendor_map:
                    mapped = ", ".join([f"{k}->{v}" for k, v in vendor_map.items()])
                    console.print(f"  [dim]mapping [/dim] {mapped}")
                basis = policy_mapping.get("block_basis") or []
                if basis:
                    console.print(f"  [dim]basis   [/dim] {', '.join([str(item) for item in basis])}")
                reasons = cs.get("reasons") or []
                if reasons:
                    console.print(f"  [dim]why     [/dim] {reasons[0]}")
            if data.get("narrative"):
                console.print(f"  [dim]{'─' * 52}[/dim]")
                console.print(f"  [dim]{data['narrative'][:300]}[/dim]")

        console.print(f"  [dim]{'─' * 52}[/dim]")
        console.print(f"  [dim]BlockINTQL · blockintql.com[/dim]")
        console.print()
        return

    if "verdict" in data and "findings" in data:
        color = verdict_color(data.get("verdict"))
        findings = data.get("findings") or {}
        methodology = data.get("methodology") or {}
        risk = methodology.get("risk_assessment") or {}
        console.print()
        console.print(f"  [bold {color}]{data.get('verdict')}[/bold {color}]  [dim]·[/dim]  [{color}]{findings.get('max_risk_score', 0)}/100 risk[/{color}]")
        console.print(f"  [dim]{'─' * 52}[/dim]")
        console.print(f"  [dim]chain    [/dim] {data.get('chain', '')}")
        console.print(f"  [dim]subjects [/dim] {data.get('addresses_analyzed', 0)} address(es)")
        plan = data.get("execution_plan") or {}
        if plan.get("mode"):
            console.print(f"  [dim]mode     [/dim] {plan.get('mode')}")
        if data.get("narrative"):
            console.print(f"  [dim]summary  [/dim] {data.get('narrative')}")
        if risk.get("band"):
            console.print(f"  [dim]method   [/dim] {risk.get('band')} · score {risk.get('score')}")
        patterns = methodology.get("laundering_patterns") or []
        if patterns:
            console.print(f"  [dim]patterns [/dim] {', '.join(item.get('label') or item.get('id') for item in patterns[:4])}")
        if findings.get("sanctions_hits"):
            console.print(f"  [dim]sanctions[/dim] {len(findings.get('sanctions_hits') or [])} hit(s)")
        if findings.get("aml_flags"):
            console.print(f"  [dim]aml      [/dim] {', '.join(str(flag) for flag in (findings.get('aml_flags') or [])[:4])}")
        console.print(f"  [dim]{'─' * 52}[/dim]")
        console.print("  [dim]BlockINTQL · methodology-grounded analysis[/dim]")
        console.print()
        return

    if isinstance(data.get("data"), list) and "count" in data and "source" in data:
        render_wallet_history_report(data)
        return

    stablecoin_data = data.get("data") if isinstance(data.get("data"), dict) else None
    if stablecoin_data and {"transactions", "volume", "activity"}.issubset(stablecoin_data.keys()):
        render_wallet_stats_report(data)
        return
    if stablecoin_data and "stablecoin_balances" in stablecoin_data:
        render_stablecoin_balances_report(data)
        return
    if stablecoin_data and {"days", "interval", "rows"}.issubset(stablecoin_data.keys()):
        render_stablecoin_history_report(data)
        return
    if stablecoin_data and (
        {"direction", "limit", "rows"}.issubset(stablecoin_data.keys())
        or {"direction", "days", "counterparties"}.issubset(stablecoin_data.keys())
    ):
        render_stablecoin_counterparties_report(data)
        return

    # ── PROFILE ────────────────────────────────────────────────────────────────
    if "profile" in data:
        found = data.get("found", False)
        console.print()
        status = "[bold green]█ FOUND[/bold green]" if found else "[dim]█ NOT FOUND[/dim]"
        console.print(f"  {status}")
        console.print(f"  [dim]{'─' * 52}[/dim]")
        console.print(f"  [dim]identifier[/dim] {data['identifier']} ({data.get('identifier_type','')})")
        if found:
            p = data.get("profile", {})
            if p.get("entity_name"):
                console.print(f"  [dim]entity    [/dim] {p['entity_name']}")
            console.print(f"  [dim]risk      [/dim] {p.get('risk_score',0)}/100")
            for addr in p.get("linked_bitcoin_addresses", [])[:5]:
                console.print(f"  [dim]btc       [/dim] {addr}")
            for l in p.get("linked_identifiers", [])[:5]:
                console.print(f"  [dim]linked    [/dim] {l['identifier']} ({l['type']})")
        console.print(f"  [dim]{'─' * 52}[/dim]")
        console.print(f"  [dim]BlockINTQL · OP_RETURN identity graph · blockintql.com[/dim]")
        console.print()
        return

    # ── ACCOUNT / STATUS ──────────────────────────────────────────────────────
    if "credits" in data and ("tier" in data or "key_prefix" in data):
        console.print()
        console.print("  [bold green]ACCOUNT OK[/bold green]")
        console.print(f"  [dim]{'─' * 52}[/dim]")
        console.print(f"  [dim]key      [/dim] {data.get('key_prefix', 'Unknown')}")
        console.print(f"  [dim]email    [/dim] {data.get('email') or 'Unknown'}")
        console.print(f"  [dim]org      [/dim] {data.get('org') or 'Unknown'}")
        console.print(f"  [dim]tier     [/dim] {data.get('tier') or 'Unknown'}")
        console.print(f"  [dim]credits  [/dim] {data.get('credits', 0)}")
        if data.get("display_name"):
            console.print(f"  [dim]name     [/dim] {data['display_name']}")
        if data.get("created_at"):
            console.print(f"  [dim]created  [/dim] {data['created_at']}")
        console.print(f"  [dim]{'─' * 52}[/dim]")
        console.print(f"  [dim]BlockINTQL · blockintql.com[/dim]")
        console.print()
        return

    # ── PLAN / WORKSPACE ──────────────────────────────────────────────────────
    if "recommended_surface" in data and "steps" in data:
        console.print()
        execution_mode = data.get("execution_mode", "plan_only")
        mode_label = {
            "plan_only": "PLAN READY",
            "created_workspace_from_plan": "WORKSPACE CREATED",
        }.get(execution_mode, execution_mode.upper())
        console.print(f"  [bold cyan]{mode_label}[/bold cyan]")
        console.print(f"  [dim]{'─' * 52}[/dim]")
        brief = data.get("investigation_brief") or {}
        budget = data.get("budget") or {}
        intent = data.get("intent") or {}
        console.print(f"  [dim]surface  [/dim] {data.get('recommended_surface', 'unknown')}")
        if intent.get("label"):
            console.print(f"  [dim]mode     [/dim] {intent.get('label')}")
        console.print(f"  [dim]credits  [/dim] {data.get('estimated_total_credits', 0)}")
        if data.get("estimated_total_usd") is not None:
            console.print(f"  [dim]usd      [/dim] {format_money(data.get('estimated_total_usd'))}")
        if budget.get("credits") is not None or budget.get("usd") is not None:
            budget_bits = []
            if budget.get("credits") is not None:
                budget_bits.append(f"{budget.get('credits')} credits")
            if budget.get("usd") is not None:
                budget_bits.append(format_money(budget.get("usd")))
            console.print(f"  [dim]budget   [/dim] {' · '.join(bit for bit in budget_bits if bit)}")
        if brief.get("goal"):
            console.print(f"  [dim]you asked[/dim] {brief['goal']}")
        if brief.get("seed_address"):
            console.print(f"  [dim]seed     [/dim] {brief['seed_address']}")
        elif data.get("address"):
            console.print(f"  [dim]seed     [/dim] {data.get('address')}")
        if data.get("workspace_context_applied"):
            context = data.get("workspace_context_summary") or {}
            console.print(f"  [dim]case     [/dim] {context.get('workspace_name') or context.get('workspace_id') or 'workspace'}")
            if context.get("last_meaningful_detail"):
                console.print(f"  [dim]context  [/dim] {context.get('last_meaningful_detail')}")
            recent_goals = context.get("recent_goals") or []
            if recent_goals:
                console.print(f"  [dim]memory   [/dim] {recent_goals[0]}")
        if data.get("summary"):
            console.print(f"  [dim]summary  [/dim] {data['summary']}")
        if data.get("executed_workspace"):
            workspace = data["executed_workspace"]
            console.print(f"  [dim]workspace[/dim] {workspace.get('workspace_id', 'queued')}")
            console.print(f"  [dim]status   [/dim] {workspace.get('status', 'unknown')}")
            if workspace.get("poll_url"):
                console.print(f"  [dim]poll     [/dim] {workspace['poll_url']}")
        elif data.get("resume_workspace"):
            workspace = data["resume_workspace"]
            console.print(f"  [dim]resume   [/dim] {workspace.get('name') or workspace.get('workspace_id')}")
            console.print(f"  [dim]status   [/dim] {workspace.get('status', 'unknown')}")
            activity = workspace.get("activity") or {}
            console.print(
                f"  [dim]activity [/dim] score={activity.get('activity_score', 0)} · "
                f"asks={activity.get('ask_count', 0)} · "
                f"notes={activity.get('notes_count', 0)} · "
                f"pins={activity.get('pin_count', 0)} · "
                f"artifacts={activity.get('artifact_count', 0)}"
            )
            if activity.get("last_meaningful_at"):
                detail = activity.get("last_meaningful_detail") or activity.get("last_meaningful_source") or "workspace_activity"
                console.print(f"  [dim]last     [/dim] {activity.get('last_meaningful_at')} ({detail})")
            if workspace.get("reason"):
                console.print(f"  [dim]reason   [/dim] {workspace.get('reason')}")
        elif data.get("recommended_workspace"):
            workspace = data["recommended_workspace"]
            console.print(f"  [dim]workspace[/dim] {workspace.get('name', 'recommended')}")
            console.print(f"  [dim]modules  [/dim] {', '.join(workspace.get('modules', []))}")
            if workspace.get("graph_step_capability_id"):
                console.print(f"  [dim]graph    [/dim] {workspace.get('graph_step_capability_id')}")
            payload = workspace.get("payload") or {}
            if payload.get("goal"):
                console.print(f"  [dim]brief    [/dim] {payload.get('goal')}")
            if payload.get("seed_address"):
                console.print(f"  [dim]seed     [/dim] {payload.get('seed_address')}")
        steps = summarize_plan_steps(data.get("steps") or [])
        if steps:
            console.print("  [dim]copilot plan[/dim]")
            for step in steps[:6]:
                console.print(f"    {step['idx']}. {step['title']} [dim]({step['surface']}{step['optional']})[/dim]")
                if step["reason"]:
                    console.print(f"       [dim]{step['reason']}[/dim]")
        selected_profile = data.get("selected_execution_profile") or {}
        if selected_profile.get("label"):
            line = f"  [dim]selected [/dim] {selected_profile.get('label')}"
            if selected_profile.get("id"):
                line += f" [dim]({selected_profile.get('id')})[/dim]"
            console.print(line)
            if selected_profile.get("description"):
                console.print(f"  [dim]profile  [/dim] {selected_profile.get('description')}")
        profiles = data.get("execution_profiles") or []
        if profiles:
            console.print("  [dim]execution modes[/dim]")
            for profile in profiles[:3]:
                label = profile.get("label") or profile.get("id") or "mode"
                line = f"    • {label}: {profile.get('estimated_credits', 0)} credits"
                if profile.get("estimated_usd") is not None:
                    line += f" / {format_money(profile.get('estimated_usd'))}"
                console.print(line)
                if profile.get("description"):
                    console.print(f"      [dim]{profile.get('description')}[/dim]")
                if profile.get("step_titles"):
                    console.print(f"      [dim]{' → '.join(profile.get('step_titles')[:4])}[/dim]")
        if data.get("execution_skipped"):
            console.print(f"  [dim]next     [/dim] {data['execution_skipped'].get('next', '')}")
        recommended_actions = brief.get("recommended_actions") or []
        if recommended_actions:
            console.print("  [dim]recommended next actions[/dim]")
            for action in recommended_actions[:3]:
                if isinstance(action, dict):
                    title = action.get("title") or action.get("id") or "action"
                    surface = action.get("surface")
                    line = f"    • {title}"
                    if surface:
                        line += f" [dim]({surface})[/dim]"
                    console.print(line)
                    if action.get("description"):
                        console.print(f"      [dim]{action.get('description')}[/dim]")
                else:
                    console.print(f"    • {action}")
        continue_steps, workspace_actions = continue_plan_instructions(data)
        if continue_steps or workspace_actions:
            console.print("  [dim]how to continue[/dim]")
            if continue_steps:
                primary = continue_steps[0]
                console.print(f"    [bold]Run next[/bold]")
                console.print(f"      [cyan]$[/cyan] {primary['command']}")
                if primary.get("title"):
                    console.print(f"      [dim]{primary.get('title')}[/dim]")
                follow_ons = continue_steps[1:]
                required_follow_ons = [step for step in follow_ons if not step.get("optional")]
                optional_follow_ons = [step for step in follow_ons if step.get("optional")]
                if required_follow_ons:
                    console.print("    [bold]Then run[/bold]")
                    for step in required_follow_ons[:4]:
                        console.print(f"      [cyan]$[/cyan] {step['command']}")
                        if step.get("title"):
                            console.print(f"      [dim]{step.get('title')}[/dim]")
                if optional_follow_ons:
                    console.print("    [bold]Optional deeper step[/bold]")
                    for step in optional_follow_ons[:3]:
                        console.print(f"      [cyan]$[/cyan] {step['command']}")
                        if step.get("title"):
                            console.print(f"      [dim]{step.get('title')}[/dim]")
            if workspace_actions:
                console.print("    [bold]If the workspace opens[/bold]")
                for idx, action in enumerate(workspace_actions, start=1):
                    console.print(f"      {idx}. {action}")
        guardrails = data.get("cost_guardrails") or {}
        if guardrails.get("message"):
            console.print(f"  [dim]guardrail[/dim] {guardrails.get('message')}")
        if data.get("execution_error"):
            err = data["execution_error"]
            console.print(f"  [red]error    [/red] {err.get('detail', err)}")
        if data.get("ask_history_warning"):
            console.print(f"  [yellow]history  [/yellow] {data.get('ask_history_warning')}")
        console.print(f"  [dim]{'─' * 52}[/dim]")
        console.print(f"  [dim]BlockINTQL · blockintql.com[/dim]")
        console.print()
        return

    if "workspaces" in data and isinstance(data.get("workspaces"), list):
        console.print()
        console.print("  [bold cyan]WORKSPACES[/bold cyan]")
        console.print(f"  [dim]{'─' * 52}[/dim]")
        for workspace in data.get("workspaces") or []:
            summary = (workspace.get("workspace_context") or {}).get("goal") or "No investigation brief yet"
            activity = workspace.get("activity") or {}
            notes_count = activity.get("notes_count", 0)
            pin_count = activity.get("pin_count", 0)
            ask_count = activity.get("ask_count", 0)
            artifact_count = activity.get("artifact_count", 0)
            score = activity.get("activity_score", 0)
            last_meaningful_at = activity.get("last_meaningful_at")
            last_meaningful_source = activity.get("last_meaningful_source")
            resume_badge = " [green](best resume)[/green]" if workspace.get("_resume_candidate") else ""
            console.print(f"  [bold]{workspace.get('name') or workspace.get('workspace_id')}[/bold]{resume_badge}")
            console.print(f"  [dim]id       [/dim] {workspace.get('workspace_id')}")
            console.print(f"  [dim]status   [/dim] {workspace.get('status') or 'unknown'}")
            console.print(f"  [dim]modules  [/dim] {', '.join(workspace.get('modules') or []) or 'none'}")
            console.print(f"  [dim]brief    [/dim] {summary}")
            console.print(f"  [dim]state    [/dim] asks={ask_count} · notes={notes_count} · pins={pin_count} · artifacts={artifact_count} · score={score}")
            if last_meaningful_at:
                detail = activity.get("last_meaningful_detail") or last_meaningful_source or "workspace_activity"
                console.print(f"  [dim]last     [/dim] {last_meaningful_at} ({detail})")
            if workspace.get("reason"):
                console.print(f"  [dim]reason   [/dim] {workspace.get('reason')}")
            console.print(f"  [dim]{'─' * 52}[/dim]")
        return

    if "summary" in data and "workspace_active" in data and "recent_refunds" in data:
        console.print()
        console.print("  [bold cyan]VM AUDIT[/bold cyan]")
        console.print(f"  [dim]{'─' * 52}[/dim]")
        summary = data.get("summary") or {}
        console.print(f"  [dim]workspace active [/dim] {summary.get('workspace_active', 0)}")
        console.print(f"  [dim]warehouse active [/dim] {summary.get('warehouse_active', 0)}")
        console.print(f"  [dim]destroyed recent [/dim] {summary.get('workspace_destroyed_recent', 0)}")
        console.print(f"  [dim]refunds recent   [/dim] {summary.get('warehouse_refunds_recent', 0)}")
        policy = data.get("cleanup_policy") or {}
        console.print(f"  [dim]ttl policy       [/dim] workspace idle {policy.get('workspace_idle_ttl_hours')}h · max {policy.get('workspace_max_ttl_hours')}h · warehouse {policy.get('warehouse_grace_minutes')}m")
        if data.get("warehouse_active"):
            console.print("  [dim]active warehouse[/dim]")
            for row in (data.get("warehouse_active") or [])[:5]:
                console.print(f"    • {row.get('query_id')} · {row.get('status')} · {row.get('vm_name') or 'no-vm'}")
        if data.get("recent_refunds"):
            console.print("  [dim]recent refunds[/dim]")
            for row in (data.get("recent_refunds") or [])[:5]:
                console.print(f"    • {row.get('query_id')} · +{row.get('refunded_credits', 0)} credits · {row.get('cleanup_reason') or row.get('status')}")
        console.print(f"  [dim]{'─' * 52}[/dim]")
        console.print("  [dim]BlockINTQL admin audit[/dim]")
        console.print()
        return

    if "workspace_id" in data and "status" in data and "poll_url" in data:
        console.print()
        console.print("  [bold cyan]WORKSPACE[/bold cyan]")
        console.print(f"  [dim]{'─' * 52}[/dim]")
        console.print(f"  [dim]id       [/dim] {data.get('workspace_id')}")
        console.print(f"  [dim]name     [/dim] {data.get('name') or 'Unknown'}")
        console.print(f"  [dim]chain    [/dim] {data.get('chain') or 'Unknown'}")
        console.print(f"  [dim]status   [/dim] {data.get('status') or 'Unknown'}")
        console.print(f"  [dim]provider [/dim] {data.get('provider') or 'Unknown'}")
        if data.get("modules"):
            console.print(f"  [dim]modules  [/dim] {', '.join(data.get('modules') or [])}")
        context = data.get("workspace_context") or {}
        if context.get("goal"):
            console.print(f"  [dim]brief    [/dim] {context.get('goal')}")
        if context.get("seed_address"):
            console.print(f"  [dim]seed     [/dim] {context.get('seed_address')}")
        if data.get("access_url"):
            console.print(f"  [dim]access   [/dim] {data['access_url']}")
        if data.get("graph_url"):
            console.print(f"  [dim]graph    [/dim] {data['graph_url']}")
        if data.get("search_url"):
            console.print(f"  [dim]search   [/dim] {data['search_url']}")
        if data.get("ssh"):
            console.print(f"  [dim]ssh      [/dim] {data['ssh']}")
        if data.get("poll_url"):
            console.print(f"  [dim]poll     [/dim] {data['poll_url']}")
        if data.get("destroy_url"):
            console.print(f"  [dim]destroy  [/dim] {data['destroy_url']}")
        if data.get("error_message"):
            console.print(f"  [red]error    [/red] {data['error_message']}")
        for note in data.get("notes") or []:
            console.print(f"  [dim]note     [/dim] {note}")
        console.print(f"  [dim]{'─' * 52}[/dim]")
        console.print(f"  [dim]BlockINTQL · blockintql.com[/dim]")
        console.print()
        return

    if not quiet:
        console.print_json(json.dumps(data, default=str))


provider_opts = [
    click.option("--provider", "-p", default=None,
                 type=click.Choice(PUBLIC_PROVIDER_CHOICES),
                 help="Attribution provider (key stays on your machine)"),
    click.option("--provider-key", default=None, envvar="BLOCKINTQL_PROVIDER_KEY",
                 help="Provider API key — never sent to BlockINTQL"),
    click.option("--provider-url", default=None,
                 help="Custom provider URL template with {address} placeholder"),
]

def with_provider(f):
    for opt in reversed(provider_opts): f = opt(f)
    return f


def _experimental_enabled() -> bool:
    return str(os.getenv("BLOCKINTQL_ENABLE_EXPERIMENTAL", "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _coming_soon(feature: str, next_steps: list[str] | None = None):
    command_path = click.get_current_context().command_path
    lines = [f"{command_path} is coming soon for the V1 launch scope ({feature})."]
    if next_steps:
        lines.append("Available now:")
        for step in next_steps:
            lines.append(f"  - {step}")
    lines.append("Enable preview commands with: export BLOCKINTQL_ENABLE_EXPERIMENTAL=1")
    raise click.ClickException("\n".join(lines))


def _require_experimental(feature: str, next_steps: list[str] | None = None):
    if _experimental_enabled():
        return
    _coming_soon(feature, next_steps=next_steps)

@click.group(cls=LaunchScopeGroup, invoke_without_command=True)
@click.version_option(__version__, prog_name="blockintql")
@click.pass_context
def cli(ctx):
    """BlockINTQL — On-Chain Intelligence CLI

    Your provider key never leaves your machine.
    BlockINTQL only receives the address being screened.
    """
    if ctx.invoked_subcommand is None:
        console.print(BLOCKINTQL_BANNER)
        console.print()
        console.print("[dim]Defaulting to interactive BlockINTQL Chat (grounded).[/dim]")
        console.print("[dim]Requires an API key (or wallet via `login`). Set BLOCKINTQL_API_KEY or run `blockintql auth`.[/dim]")
        console.print("[dim]Other commands: screen, verdict, history, status, providers, chart, graph, ... (see --help).[/dim]")
        console.print()
        console.print("[bold]Try this first prompt:[/bold]")
        console.print("  Screen 0x742d35Cc6634C0532925a3b844Bc9e7595f6EEd0 and create a chart for the last 30 days.")
        console.print()
        _run_chat_repl(grounded=True)
        return

@cli.command()
@click.option("--api-key", required=True)
@click.option("--provider", default=None)
def auth(api_key, provider):
    """Save API key and optional default provider name."""
    is_valid, validation_error = _validate_api_key(api_key)
    if not is_valid:
        raise click.ClickException(
            "API key validation failed. The key was not saved.\n"
            f"Reason: {validation_error or 'unknown error'}\n"
            "Next: confirm the full key value, then retry `blockintql auth --api-key biq_sk_live_...`"
        )
    config = load_config()
    config["api_key"] = api_key
    if provider:
        config["default_provider"] = provider
    save_config(config)
    console.print("[green]Saved API configuration.[/]")
    console.print("[dim]Keep provider keys in environment variables instead of config files.[/]")

@cli.command()
@click.argument("address_arg", required=False)
@click.option("--address", "-a", required=False)
@click.option("--chain", "-c", default="auto", type=click.Choice(["auto","bitcoin","ethereum"]))
@click.option("--context", default="")
@with_provider
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def verdict(address_arg, address, chain, context, provider, provider_key, provider_url, agent, quiet):
    """Get a CLEAR/CAUTION/BLOCK verdict.

    \b
    Privacy: BlockINTQL receives address+chain only.
    Provider key stays on your machine.

    \b
    Examples:
      blockintql verdict --address 1A1zP1e...
      blockintql verdict --address 0x123... --provider chainalysis --provider-key $KEY
    """
    address = coalesce_address(address_arg, address)
    if not address:
        raise click.UsageError("Provide an address as an argument or with --address")
    chain = infer_chain_from_value(address, fallback="bitcoin") if chain == "auto" else chain
    provider_settings = get_provider_configured_settings(provider)
    provider = provider or provider_settings.get("provider")
    provider_key = provider_key or provider_settings.get("provider_key")
    provider_url = provider_url or provider_settings.get("provider_url")
    auth_header = provider_settings.get("auth_header")
    auth_prefix = provider_settings.get("auth_prefix")
    risk_field = provider_settings.get("risk_field")
    entity_field = provider_settings.get("entity_field")
    if not quiet and not agent:
        p_info = f" + {provider} (local)" if provider else ""
        console.print(f"[dim]Screening {address[:20]}...{p_info}[/]")

    # STEP 1: Prefer the open-source deterministic core when we have no (or only local) provider
    # This is the key to making the OSS repo a real foundation, not just a client.
    if not provider:
        from .deterministic import adjudicate
        result = adjudicate(address, chain=chain)
        output(result, agent, quiet)
        return

    # Otherwise fall back to the (optional) BlockINTQL API + local provider enrichment
    result = api_post("/v1/verdict", {"address": address, "chain": chain, "context": context})

    # STEP 2: Provider called directly from YOUR machine — key never sent to BlockINTQL
    if provider and "error" not in result:
        result = enrich_with_provider(
            result, address, chain, provider, provider_key, provider_url,
            auth_header=auth_header, auth_prefix=auth_prefix,
            risk_field=risk_field, entity_field=entity_field,
        )

    output(result, agent, quiet)

@cli.command()
@click.argument("address_arg", required=False)
@click.option("--address", "-a", required=False)
@click.option("--chain", "-c", default="auto", type=click.Choice(["auto","bitcoin","ethereum"]))
@with_provider
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def screen(address_arg, address, chain, provider, provider_key, provider_url, agent, quiet):
    """Screen a counterparty before transacting.

    \b
    Privacy: Your provider key never touches BlockINTQL servers.
    Provider is called directly from your machine.

    \b
    Examples:
      blockintql screen --address 1A1zP1e...
      blockintql screen --address 0x123... --provider trm --provider-key $KEY
    """
    address = coalesce_address(address_arg, address)
    if not address:
        raise click.UsageError("Provide an address as an argument or with --address")
    chain = infer_chain_from_value(address, fallback="bitcoin") if chain == "auto" else chain
    provider_settings = get_provider_configured_settings(provider)
    provider = provider or provider_settings.get("provider")
    provider_key = provider_key or provider_settings.get("provider_key")
    provider_url = provider_url or provider_settings.get("provider_url")
    auth_header = provider_settings.get("auth_header")
    auth_prefix = provider_settings.get("auth_prefix")
    risk_field = provider_settings.get("risk_field")
    entity_field = provider_settings.get("entity_field")
    if not quiet and not agent:
        p_info = f" + {provider} (local)" if provider else ""
        console.print(f"[dim]Screening {address[:20]}...{p_info}[/]")

    # STEP 1: Prefer the open deterministic core for pure local / bring-your-own-data use cases
    if not provider:
        from .deterministic import adjudicate
        result = adjudicate(address, chain=chain)
        output(result, agent, quiet)
        return

    result = api_post("/v1/screen", {"address": address, "chain": chain})

    # STEP 2: Provider called directly from YOUR machine — key never sent to BlockINTQL
    if provider and "error" not in result:
        result = enrich_with_provider(
            result, address, chain, provider, provider_key, provider_url,
            auth_header=auth_header, auth_prefix=auth_prefix,
            risk_field=risk_field, entity_field=entity_field,
        )

    output(result, agent, quiet)


def _verdict_payload_for_address(
    *,
    address: str,
    chain: str,
    context: str,
    provider: str | None,
    provider_key: str | None,
    provider_url: str | None,
    auth_header: str | None,
    auth_prefix: str | None,
    risk_field: str | None,
    entity_field: str | None,
):
    payload = api_post("/v1/verdict", {"address": address, "chain": chain, "context": context})
    if provider and "error" not in payload:
        payload = enrich_with_provider(
            payload,
            address,
            chain,
            provider,
            provider_key,
            provider_url,
            auth_header=auth_header,
            auth_prefix=auth_prefix,
            risk_field=risk_field,
            entity_field=entity_field,
        )
    return payload


@cli.command("screen-tx")
@click.option("--txid", "-t", required=True)
@click.option("--chain", "-c", default="ethereum", type=click.Choice(["ethereum"]))
@with_provider
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def screen_tx(txid, chain, provider, provider_key, provider_url, agent, quiet):
    """Screen a transaction anchor and return one transaction-level decision."""
    if not str(txid).startswith("0x") or len(str(txid)) != 66:
        raise click.UsageError("Ethereum transaction hashes must be passed as 0x-prefixed 66-character values.")

    if not quiet and not agent:
        p_info = f" + {provider} (local)" if provider else ""
        console.print(f"[dim]Screening transaction {txid[:20]}...{p_info}[/]")

    tx_result = api_get(f"/v1/eth/tx/{txid}/verbose")
    if "error" in tx_result:
        output(tx_result, agent, quiet)
        return

    tx_data = (tx_result or {}).get("data") or {}
    from_address = tx_data.get("from")
    to_address = tx_data.get("to")
    if not from_address or not to_address:
        output(
            {
                "error": "Transaction payload is missing from/to addresses.",
                "txid": txid,
                "source": tx_result.get("source"),
            },
            agent,
            quiet,
        )
        return

    provider_settings = get_provider_configured_settings(provider)
    provider = provider or provider_settings.get("provider")
    provider_key = provider_key or provider_settings.get("provider_key")
    provider_url = provider_url or provider_settings.get("provider_url")
    auth_header = provider_settings.get("auth_header")
    auth_prefix = provider_settings.get("auth_prefix")
    risk_field = provider_settings.get("risk_field")
    entity_field = provider_settings.get("entity_field")

    context = f"transaction_anchor:{txid}"
    from_verdict = _verdict_payload_for_address(
        address=from_address,
        chain=chain,
        context=context,
        provider=provider,
        provider_key=provider_key,
        provider_url=provider_url,
        auth_header=auth_header,
        auth_prefix=auth_prefix,
        risk_field=risk_field,
        entity_field=entity_field,
    )
    to_verdict = _verdict_payload_for_address(
        address=to_address,
        chain=chain,
        context=context,
        provider=provider,
        provider_key=provider_key,
        provider_url=provider_url,
        auth_header=auth_header,
        auth_prefix=auth_prefix,
        risk_field=risk_field,
        entity_field=entity_field,
    )

    if "error" in from_verdict or "error" in to_verdict:
        output(
            {
                "error": "Unable to compute transaction-level decision because one or more counterparty verdicts failed.",
                "txid": txid,
                "tx_source": tx_result.get("source"),
                "from_verdict_error": from_verdict.get("error"),
                "to_verdict_error": to_verdict.get("error"),
            },
            agent,
            quiet,
        )
        return

    from_decision = str(from_verdict.get("verdict") or "CAUTION").upper()
    to_decision = str(to_verdict.get("verdict") or "CAUTION").upper()
    decisions = {from_decision, to_decision}
    if "BLOCK" in decisions:
        tx_decision = "BLOCK"
    elif "CAUTION" in decisions:
        tx_decision = "CAUTION"
    else:
        tx_decision = "CLEAR"

    tx_risk_score = max(
        _as_float(from_verdict.get("risk_score"), 0.0),
        _as_float(to_verdict.get("risk_score"), 0.0),
    )

    result = {
        "subject": txid,
        "subject_type": "transaction",
        "chain": chain,
        "verdict": tx_decision,
        "safe": tx_decision == "CLEAR",
        "risk_score": tx_risk_score,
        "action": "block" if tx_decision == "BLOCK" else ("review" if tx_decision == "CAUTION" else "allow"),
        "tx": {
            "txid": txid,
            "source": tx_result.get("source"),
            "from": from_address,
            "to": to_address,
            "value_eth": tx_data.get("value_eth"),
            "block_number": tx_data.get("block_number"),
            "status": tx_data.get("status"),
        },
        "counterparty_verdicts": {
            "from": from_verdict,
            "to": to_verdict,
        },
        "consensus": {
            "mode": "transaction_anchor_screening",
            "anchor": txid,
            "decision_rule": "max_risk_across_counterparties",
            "counterparty_decisions": {
                "from": from_decision,
                "to": to_decision,
            },
            "reasons": [
                f"from={from_decision} risk={_as_float(from_verdict.get('risk_score'), 0.0)}",
                f"to={to_decision} risk={_as_float(to_verdict.get('risk_score'), 0.0)}",
            ],
        },
    }
    output(result, agent, quiet)


@cli.command()
@click.argument("address_arg", required=False)
@click.option("--address", "-a", required=False)
@click.option("--chain", "-c", default="ethereum", type=click.Choice(["ethereum"]))
@click.option("--days", default=30, show_default=True, type=int)
@click.option("--limit", default=50, show_default=True, type=int)
@click.option(
    "--allow-network-read/--indexed-only",
    default=True,
    show_default=True,
    help="Use live network read when primary indexed history is unavailable.",
)
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def history(address_arg, address, chain, days, limit, allow_network_read, agent, quiet):
    """Fetch unified Ethereum wallet history (native + token transfers)."""
    address = coalesce_address(address_arg, address)
    if not address:
        raise click.UsageError("Provide an address as an argument or with --address")
    if not quiet and not agent:
        console.print(f"[dim]Loading {chain} history for {address[:20]}...[/]")
    result = api_get(
        f"/v1/eth/address/{address}/history",
        {"limit": limit, "days": days, "allow_network_read": allow_network_read},
        timeout=120,
    )
    if isinstance(result, dict):
        result.setdefault("address", address)
        if int(result.get("count") or 0) == 0 and result.get("hot_wallet"):
            slice_window = max(1, min(int(days or 30), 30))
            hot_wallet_slice = {}
            try:
                stats_result = api_get(f"/v1/eth/address/{address}/stats", timeout=60)
                if isinstance(stats_result, dict):
                    hot_wallet_slice["stats"] = stats_result
            except Exception:
                pass
            try:
                stablecoin_history_result = api_get(
                    f"/v1/eth/address/{address}/stablecoin-history",
                    {"days": slice_window, "interval": "day"},
                    timeout=60,
                )
                if isinstance(stablecoin_history_result, dict):
                    hot_wallet_slice["stablecoin_history"] = stablecoin_history_result
            except Exception:
                pass
            try:
                counterparties_result = api_get(
                    f"/v1/eth/address/{address}/stablecoin-counterparties",
                    {"days": slice_window, "direction": "both", "limit": 5},
                    timeout=60,
                )
                if isinstance(counterparties_result, dict):
                    cp_data = counterparties_result.get("data") or {}
                    hot_wallet_slice["counterparties"] = cp_data.get("counterparties") or cp_data.get("rows") or []
            except Exception:
                pass
            if hot_wallet_slice:
                result["hot_wallet_slice"] = hot_wallet_slice
    if isinstance(result, dict) and result.get("network_read_available") and not allow_network_read:
        result.setdefault("next", f"blockintql history {address} --days {days} --limit {limit} --allow-network-read")
    output(result, agent, quiet)


@cli.command()
@click.argument("address_arg", required=False)
@click.option("--address", "-a", required=False)
@click.option("--chain", "-c", default="ethereum", type=click.Choice(["ethereum"]))
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def stats(address_arg, address, chain, agent, quiet):
    """Fetch wallet stats for an Ethereum address."""
    _require_experimental(
        "wallet stats",
        next_steps=[
            "blockintql history <address>",
            "blockintql screen <address>",
            "blockintql verdict <address>",
        ],
    )
    address = coalesce_address(address_arg, address)
    if not address:
        raise click.UsageError("Provide an address as an argument or with --address")
    if not quiet and not agent:
        console.print(f"[dim]Loading {chain} stats for {address[:20]}...[/]")
    result = api_get(f"/v1/eth/address/{address}/stats", timeout=120)
    if isinstance(result, dict):
        result.setdefault("address", address)
    output(result, agent, quiet)


@cli.command("tx")
@click.option("--txid", "-t", required=True)
@click.option("--chain", "-c", default="ethereum", type=click.Choice(["ethereum"]))
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def tx_lookup(txid, chain, agent, quiet):
    """Fetch verbose Ethereum transaction details."""
    if not str(txid).startswith("0x") or len(str(txid)) != 66:
        raise click.UsageError("Ethereum transaction hashes must be passed as 0x-prefixed 66-character values.")
    if not quiet and not agent:
        console.print(f"[dim]Loading {chain} transaction {txid[:20]}...[/]")
    result = api_get(f"/v1/eth/tx/{txid}/verbose")
    output(result, agent, quiet)


@cli.group(cls=DefaultingGroup, invoke_without_command=True)
@click.pass_context
def stablecoins(ctx):
    """Ethereum stablecoin analytics commands.

    Examples:
      blockintql stablecoins 0xabc...
      blockintql stablecoins --address 0xabc...
      blockintql stablecoins history 0xabc... --days 30
      blockintql stablecoins counterparties 0xabc... --days 30
      blockintql stablecoins flows --hours 24
      blockintql stablecoins large-transfers --hours 24 --min-amount 1000000
    """
    if ctx.invoked_subcommand:
        return
    examples = [
        "blockintql stablecoins 0xabc...",
        "blockintql stablecoins --address 0xabc...",
        "blockintql stablecoins balances 0xabc...",
        "blockintql stablecoins history 0xabc... --days 30",
        "blockintql stablecoins counterparties 0xabc... --days 30",
        "blockintql stablecoins flows --hours 24",
        "blockintql stablecoins large-transfers --hours 24 --min-amount 1000000",
    ]
    if not sys.stdout.isatty():
        click.echo(json.dumps({
            "group": "stablecoins",
            "description": "Ethereum stablecoin analytics commands.",
            "examples": examples,
        }, indent=2))
        return

    console.print("[yellow]Choose a stablecoin command or pass an address to default to balances.[/]")
    console.print("[dim]Examples:[/]")
    for example in examples:
        console.print(f"[dim]  {example}[/]")


@cli.group()
def chart():
    """Render terminal-native charts for supported analytics endpoints."""


@cli.group(invoke_without_command=True)
@click.pass_context
def graph(ctx):
    """Promptable graph shell and explorer commands."""
    if ctx.invoked_subcommand is None:
        _run_graph_prompt_repl()
        return


# ──────────────────────────────────────────────────────────────────────────────
# NEW: First-class deterministic core (the heart of the open source foundation)
# ──────────────────────────────────────────────────────────────────────────────
@cli.group()
def deterministic():
    """
    Direct access to the open-source deterministic core.

    This is the auditable, versioned, agent-native reasoning layer.
    Use it standalone or as the control plane on top of any data sources.
    """


@deterministic.command("adjudicate")
@click.argument("address")
@click.option("--chain", default="ethereum")
@click.option("--json", "json_output", is_flag=True, help="Output raw JSON.")
@click.option("--labels", default=None, help="Path to JSON own_labels file for bring-your-own-labels (local Sentinel boost).")
def deterministic_adjudicate(address, chain, json_output, labels):
    """Run the full deterministic + swarm adjudication locally (no API key required when using DEV_NO_AUTH or local data)."""
    from .deterministic import adjudicate
    own_labels = None
    if labels:
        with open(labels) as f:
            own_labels = json.load(f)
    result = adjudicate(address, chain=chain, own_labels=own_labels)
    if json_output:
        click.echo(json.dumps(result, indent=2, default=str))
    else:
        output(result)


@deterministic.command("export-evidence")
@click.argument("address")
@click.option("--chain", default="ethereum")
@click.option("--out", "outfile", default=None, help="Write bundle to file (json).")
@click.option("--include-raw", is_flag=True, help="Include raw provider payloads (if any) in the bundle.")
def deterministic_export_evidence(address, chain, outfile, include_raw):
    """Export a signed, hashable, reproducible evidence bundle (the artifact regulators actually want)."""
    from .deterministic import adjudicate, export_evidence_bundle, Policy
    result = adjudicate(address, chain=chain)
    prov = result.get("provider_result") or {}
    if not include_raw:
        prov = {k: v for k, v in prov.items() if k != "raw"}

    bundle = export_evidence_bundle(
        subject=address,
        chain=chain,
        policy=Policy(),
        provider_result=prov,
        consensus=result.get("consensus", {}),
        final_verdict=result,
    )
    data = bundle.to_dict()
    if outfile:
        with open(outfile, "w") as f:
            json.dump(data, f, indent=2, default=str)
        console.print(f"[green]Evidence bundle written → {outfile}[/green]")
        console.print(f"bundle_hash: {bundle.bundle_hash}")
        console.print(f"reproducibility_hash: {result.get('_reproducibility_hash')}")
    else:
        click.echo(json.dumps(data, indent=2, default=str))


@deterministic.command("eval")
@click.option("--suite", default="synthetic", help="Which suite to run (synthetic for now).")
@click.option("--ablate", is_flag=True, help="Run provider ablation examples too.")
def deterministic_eval(suite, ablate):
    """Run the open evaluation harness against the current deterministic core."""
    from .eval import run_suite, provider_ablation
    report = run_suite()
    console.print(f"[bold]Deterministic eval suite[/bold] — passed {report['passed']}/{report['total']} ({report['accuracy']:.0%})")
    for r in report["results"]:
        mark = "✓" if r["match"] else "✗"
        console.print(f"  {mark} {r['name']}: got {r['verdict']} (expected {r['expected']})")
    if ablate:
        ab = provider_ablation(["0xmixer", "0xhighrisk"], [
            {"entity_category": "mixer"},
            {"risk_score": 90, "entity_category": "unknown"}
        ])
        console.print("[bold]Provider ablation samples:[/bold]")
        for a in ab["ablations"][:4]:
            console.print(f"  {a}")


@graph.command("shell")
@click.option("--seed", default=None, help="Seed wallet or address (comma-separated for multiple uploaded addresses) for the shell session.")
@click.option("--open/--no-open", "open_browser", default=False, show_default=True, help="Open the configured explorer URL with the compiled shell spec.")
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON.")
@click.argument("prompt")
def graph_shell(prompt, seed, open_browser, json_output):
    """Compile or launch a deterministic graph shell from a natural-language prompt."""
    compiled = compile_graph_shell_prompt(prompt)
    payload = {
        "surface": "graph_shell",
        "prompt": prompt,
        "seed": seed,
        "shell_spec": compiled.get("spec") or {},
        "matched_rules": compiled.get("matched_rules") or [],
        "open_requested": bool(open_browser),
    }

    explorer_base = get_graph_shell_base()
    if explorer_base:
        payload["explorer_url"] = build_graph_shell_url(
            explorer_base,
            prompt=prompt,
            spec=payload["shell_spec"],
            seed=seed,
        )
    if open_browser:
        if not payload.get("explorer_url"):
            payload["warning"] = "No graph explorer URL. Start your local blockintql server (it now auto-mounts /explorer-react/) or set BLOCKINTQL_GRAPH_SHELL_URL / save graph_shell_url."
        else:
            import webbrowser

            try:
                webbrowser.open(payload["explorer_url"])
                payload["opened"] = True
            except Exception:
                payload["opened"] = False

    if json_output:
        click.echo(json.dumps(payload, indent=2, default=str))
        return
    output(payload, agent=False, quiet=False)


@graph.command("compile")
@click.argument("prompt")
@click.option("--seed", default=None, help="Optional seed wallet or address.")
@click.option("--json", "json_output", is_flag=True, default=True, show_default=True, help="Print structured JSON.")
def graph_compile(prompt, seed, json_output):
    """Compile a graph shell prompt into a deterministic shell spec."""
    compiled = compile_graph_shell_prompt(prompt)
    payload = {
        "surface": "graph_shell",
        "prompt": prompt,
        "seed": seed,
        "shell_spec": compiled.get("spec") or {},
        "matched_rules": compiled.get("matched_rules") or [],
    }
    if json_output:
        click.echo(json.dumps(payload, indent=2, default=str))
        return
    output(payload, agent=False, quiet=False)


@graph.command("refine")
@click.argument("prompt")
@click.option("--seed", default=None, help="Optional seed wallet or address.")
@click.option("--open/--no-open", "open_browser", default=False, show_default=True, help="Open the configured explorer URL with the refined shell spec.")
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON.")
def graph_refine(prompt, seed, open_browser, json_output):
    """Refine the graph shell with a new deterministic prompt."""
    compiled = compile_graph_shell_prompt(prompt)
    payload = {
        "surface": "graph_shell",
        "prompt": prompt,
        "seed": seed,
        "shell_spec": compiled.get("spec") or {},
        "matched_rules": compiled.get("matched_rules") or [],
        "refined": True,
        "open_requested": bool(open_browser),
    }
    explorer_base = get_graph_shell_base()
    if explorer_base:
        payload["explorer_url"] = build_graph_shell_url(
            explorer_base,
            prompt=prompt,
            spec=payload["shell_spec"],
            seed=seed,
        )
    if open_browser and payload.get("explorer_url"):
        import webbrowser

        try:
            webbrowser.open(payload["explorer_url"])
            payload["opened"] = True
        except Exception:
            payload["opened"] = False
    elif open_browser and not payload.get("explorer_url"):
        payload["warning"] = "No graph explorer URL. Start your local blockintql server (it now auto-mounts /explorer-react/) or set BLOCKINTQL_GRAPH_SHELL_URL / save graph_shell_url."

    if json_output:
        click.echo(json.dumps(payload, indent=2, default=str))
        return
    output(payload, agent=False, quiet=False)


@chart.command("stablecoin-flows")
@click.option("--hours", default=24, show_default=True, type=int)
@click.option("--interval", default="hour", show_default=True, type=click.Choice(["hour", "day"]))
@click.option("--token", default=None)
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def chart_stablecoin_flows(hours, interval, token, agent, quiet):
    """Render a terminal chart for network stablecoin flow series."""
    if not quiet and not agent:
        console.print("[dim]Rendering stablecoin flow chart...[/]")
    params = {"hours": hours, "interval": interval}
    if token:
        params["token"] = token
    result = api_get("/v1/eth/stablecoins/flows", params, timeout=180)
    if agent or not sys.stdout.isatty() or "error" in result:
        output(result, agent, quiet)
        return
    has_data = render_stablecoin_flow_chart(result, hours=hours, interval=interval, token=token)
    if has_data is False and not quiet and not agent:
        _guided_wallet_flow_pivot(token=token)


@chart.command("wallet-stablecoins")
@click.argument("address")
@click.option("--days", default=30, show_default=True, type=int)
@click.option("--interval", default="day", show_default=True, type=click.Choice(["hour", "day"]))
@click.option("--token", default=None)
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def chart_wallet_stablecoins(address, days, interval, token, agent, quiet):
    """Render a terminal chart for wallet stablecoin history."""
    if not quiet and not agent:
        console.print(f"[dim]Rendering wallet stablecoin chart for {address[:20]}...[/]")
    params = {"days": days, "interval": interval}
    if token:
        params["token"] = token
    result = api_get(f"/v1/eth/address/{address}/stablecoin-history", params, timeout=90)
    if agent or not sys.stdout.isatty() or "error" in result:
        output(result, agent, quiet)
        return
    render_wallet_stablecoin_chart(result, address=address, days=days, token=token)


@chart.command("wallet-stablecoin-balances")
@click.argument("address")
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def chart_wallet_stablecoin_balances(address, agent, quiet):
    """Render a terminal chart for current wallet stablecoin balances."""
    if not quiet and not agent:
        console.print(f"[dim]Rendering wallet stablecoin balances chart for {address[:20]}...[/]")
    result = api_get(f"/v1/eth/address/{address}/stablecoins", timeout=90)
    if agent or not sys.stdout.isatty() or "error" in result:
        output(result, agent, quiet)
        return
    render_wallet_stablecoin_balances_chart(result, address=address)


@chart.command("counterparties")
@click.argument("address")
@click.option("--token", default=None)
@click.option("--direction", default="both", show_default=True, type=click.Choice(["inbound", "outbound", "both"]))
@click.option("--days", default=30, show_default=True, type=int)
@click.option("--limit", default=25, show_default=True, type=int)
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def chart_counterparties(address, token, direction, days, limit, agent, quiet):
    """Render a terminal chart for stablecoin counterparties."""
    if not quiet and not agent:
        console.print(f"[dim]Rendering counterparty chart for {address[:20]}...[/]")
    params = {"direction": direction, "days": days, "limit": limit}
    if token:
        params["token"] = token
    result = api_get(f"/v1/eth/address/{address}/stablecoin-counterparties", params, timeout=90)
    if agent or not sys.stdout.isatty() or "error" in result:
        output(result, agent, quiet)
        return
    render_counterparty_chart(result, address=address, token=token)


@stablecoins.command("balances")
@click.argument("address_arg", required=False)
@click.option("--address", "-a", required=False)
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def stablecoins_balances(address_arg, address, agent, quiet):
    """Fetch major stablecoin balances for an Ethereum wallet."""
    address = coalesce_address(address_arg, address)
    if not address:
        raise click.UsageError("Provide an address as an argument or with --address")
    if not quiet and not agent:
        console.print(f"[dim]Loading stablecoin balances for {address[:20]}...[/]")
    result = api_get(f"/v1/eth/address/{address}/stablecoins")
    if isinstance(result, dict):
        result.setdefault("address", address)
    output(result, agent, quiet)


@stablecoins.command("history")
@click.argument("address_arg", required=False)
@click.option("--address", "-a", required=False)
@click.option("--days", default=30, show_default=True, type=int)
@click.option("--interval", default="day", show_default=True, type=click.Choice(["hour", "day"]))
@click.option("--token", default=None)
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def stablecoins_history(address_arg, address, days, interval, token, agent, quiet):
    """Fetch time-bucketed stablecoin history for an Ethereum wallet."""
    address = coalesce_address(address_arg, address)
    if not address:
        raise click.UsageError("Provide an address as an argument or with --address")
    if not quiet and not agent:
        console.print(f"[dim]Loading stablecoin history for {address[:20]}...[/]")
    params = {"days": days, "interval": interval}
    if token:
        params["token"] = token
    result = api_get(f"/v1/eth/address/{address}/stablecoin-history", params, timeout=180)
    if isinstance(result, dict):
        result.setdefault("address", address)
    output(result, agent, quiet)


@stablecoins.command("counterparties")
@click.argument("address_arg", required=False)
@click.option("--address", "-a", required=False)
@click.option("--token", default=None)
@click.option("--direction", default="both", show_default=True, type=click.Choice(["inbound", "outbound", "both"]))
@click.option("--days", default=30, show_default=True, type=int)
@click.option("--limit", default=25, show_default=True, type=int)
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def stablecoins_counterparties(address_arg, address, token, direction, days, limit, agent, quiet):
    """Fetch top stablecoin counterparties for an Ethereum wallet."""
    address = coalesce_address(address_arg, address)
    if not address:
        raise click.UsageError("Provide an address as an argument or with --address")
    if not quiet and not agent:
        console.print(f"[dim]Loading stablecoin counterparties for {address[:20]}...[/]")
    params = {"direction": direction, "days": days, "limit": limit}
    if token:
        params["token"] = token
    result = api_get(f"/v1/eth/address/{address}/stablecoin-counterparties", params)
    if isinstance(result, dict):
        result.setdefault("address", address)
    output(result, agent, quiet)


@stablecoins.command("flows")
@click.option("--hours", default=24, show_default=True, type=int)
@click.option("--interval", default="hour", show_default=True, type=click.Choice(["hour", "day"]))
@click.option("--token", default=None)
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def stablecoins_flows(hours, interval, token, agent, quiet):
    """Fetch network-level Ethereum stablecoin flow series."""
    if not quiet and not agent:
        console.print("[dim]Loading stablecoin flow series...[/]")
    params = {"hours": hours, "interval": interval}
    if token:
        params["token"] = token
    result = api_get("/v1/eth/stablecoins/flows", params, timeout=180)
    output(result, agent, quiet)


@stablecoins.command("large-transfers")
@click.option("--min-amount", default=100000, show_default=True, type=float)
@click.option("--hours", default=24, show_default=True, type=int)
@click.option("--token", default=None)
@click.option("--limit", default=100, show_default=True, type=int)
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def stablecoins_large_transfers(min_amount, hours, token, limit, agent, quiet):
    """Fetch large Ethereum stablecoin transfers."""
    if not quiet and not agent:
        console.print("[dim]Loading large stablecoin transfers...[/]")
    params = {"min_amount": min_amount, "hours": hours, "limit": limit}
    if token:
        params["token"] = token
    result = api_get("/v1/eth/stablecoins/large-transfers", params)
    output(result, agent, quiet)


@cli.group()
def eth():
    """Ethereum-first command namespace."""


@eth.command("history")
@click.argument("address")
@click.option("--days", default=30, show_default=True, type=int)
@click.option("--limit", default=25, show_default=True, type=int)
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def eth_history(address, days, limit, agent, quiet):
    """Fetch unified Ethereum wallet history."""
    result = api_get(f"/v1/eth/address/{address}/history", {"limit": limit, "days": days})
    if isinstance(result, dict):
        result.setdefault("address", address)
    output(result, agent, quiet)


@eth.command("stats")
@click.argument("address")
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def eth_stats(address, agent, quiet):
    """Fetch wallet stats for an Ethereum address."""
    _require_experimental(
        "wallet stats",
        next_steps=[
            "blockintql history <address>",
            "blockintql screen <address>",
            "blockintql verdict <address>",
        ],
    )
    result = api_get(f"/v1/eth/address/{address}/stats")
    if isinstance(result, dict):
        result.setdefault("address", address)
    output(result, agent, quiet)


@eth.command("tx")
@click.argument("txid")
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def eth_tx(txid, agent, quiet):
    """Fetch verbose Ethereum transaction details."""
    _require_experimental(
        "transaction verbose lookup",
        next_steps=[
            "blockintql history <address>",
            "blockintql screen <address>",
        ],
    )
    result = api_get(f"/v1/eth/tx/{txid}/verbose")
    output(result, agent, quiet)


@eth.command("verdict")
@click.argument("address")
@click.option("--context", default="")
@with_provider
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def eth_verdict(address, context, provider, provider_key, provider_url, agent, quiet):
    """Get a verdict for an Ethereum address."""
    result = api_post("/v1/verdict", {"address": address, "chain": "ethereum", "context": context})
    if provider and "error" not in result:
        result = enrich_with_provider(result, address, "ethereum", provider, provider_key, provider_url)
    output(result, agent, quiet)


@eth.command("screen")
@click.argument("address")
@with_provider
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def eth_screen(address, provider, provider_key, provider_url, agent, quiet):
    """Screen an Ethereum address."""
    result = api_post("/v1/screen", {"address": address, "chain": "ethereum"})
    if provider and "error" not in result:
        result = enrich_with_provider(result, address, "ethereum", provider, provider_key, provider_url)
    output(result, agent, quiet)


@eth.group("stablecoins")
def eth_stablecoins():
    """Ethereum stablecoin analytics namespace."""
    _require_experimental(
        "stablecoin analytics",
        next_steps=[
            "blockintql history <address>",
            "blockintql screen <address>",
            "blockintql chat --interactive",
        ],
    )


@eth_stablecoins.command("balances")
@click.argument("address")
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def eth_stablecoins_balances(address, agent, quiet):
    result = api_get(f"/v1/eth/address/{address}/stablecoins")
    output(result, agent, quiet)


@eth_stablecoins.command("history")
@click.argument("address")
@click.option("--days", default=30, show_default=True, type=int)
@click.option("--interval", default="day", show_default=True, type=click.Choice(["hour", "day"]))
@click.option("--token", default=None)
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def eth_stablecoins_history(address, days, interval, token, agent, quiet):
    params = {"days": days, "interval": interval}
    if token:
        params["token"] = token
    result = api_get(f"/v1/eth/address/{address}/stablecoin-history", params)
    output(result, agent, quiet)


@eth_stablecoins.command("counterparties")
@click.argument("address")
@click.option("--token", default=None)
@click.option("--direction", default="both", show_default=True, type=click.Choice(["inbound", "outbound", "both"]))
@click.option("--days", default=30, show_default=True, type=int)
@click.option("--limit", default=25, show_default=True, type=int)
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def eth_stablecoins_counterparties(address, token, direction, days, limit, agent, quiet):
    params = {"direction": direction, "days": days, "limit": limit}
    if token:
        params["token"] = token
    result = api_get(f"/v1/eth/address/{address}/stablecoin-counterparties", params)
    output(result, agent, quiet)


@cli.command()
@click.option("--surface", default="cli", type=click.Choice(["api", "cli", "mcp"]))
@click.option("--category", default=None)
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def capabilities(surface, category, agent, quiet):
    """List discoverable capabilities and their CLI examples."""
    params = {"surface": surface}
    if category:
        params["category"] = category
    result = api_get("/v1/capabilities", params, require_auth=False)
    if isinstance(result, dict):
        capabilities_list = result.get("capabilities")
        if isinstance(capabilities_list, list):
            filtered = []
            for item in capabilities_list:
                if not isinstance(item, dict):
                    continue
                capability_id = item.get("id")
                if capability_id in LAUNCH_V1_CAPABILITY_IDS:
                    filtered.append(item)
            result["capabilities"] = filtered
        # Launch-tight output: hide preview metadata from default capabilities output.
        result.pop("coming_soon", None)
        if isinstance(result.get("notes"), list):
            result["notes"] = [
                "Public V1 scope shows launch-ready capabilities only.",
                "Enable preview commands in CLI with: export BLOCKINTQL_ENABLE_EXPERIMENTAL=1",
            ]
    output(result, agent, quiet)

@cli.command()
@click.argument("query", nargs=-1)
@click.option("--address", "-a", multiple=True)
@click.option("--chain", "-c", default="ethereum", type=click.Choice(["bitcoin","ethereum","both"]))
@click.option("--format", "fmt", default="full", type=click.Choice(["full","graph","narrative"]))
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def analyze(query, address, chain, fmt, agent, quiet):
    """Run autonomous multi-agent analysis."""
    _require_experimental(
        "autonomous multi-agent analysis",
        next_steps=[
            "blockintql chat --interactive",
            "blockintql screen <address>",
            "blockintql verdict <address>",
        ],
    )
    query_text = " ".join(query).strip()
    if not query_text and not address:
        raise click.UsageError("Provide a QUERY or --address")
    if not quiet and not agent:
        console.print("[dim]Running autonomous analysis...[/]")
    result = api_post("/v1/analyze", {"query": query_text, "addresses": list(address),
                                       "chain": chain, "output_format": fmt}, timeout=180)
    output(result, agent, quiet)

@cli.command()
@click.option("--identifier", "-i", required=True)
@click.option("--type", "id_type", default="auto",
              type=click.Choice(["auto","email","telegram","twitter","phone",
                                  "btc_address","eth_address","pgp_fingerprint"]))
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def profile(identifier, id_type, agent, quiet):
    """Search OP_RETURN identity graph — unique on-chain data."""
    _require_experimental(
        "identity profile graph",
        next_steps=[
            "blockintql screen <address>",
            "blockintql verdict <address>",
        ],
    )
    if not quiet and not agent:
        console.print(f"[dim]Searching identity graph...[/]")
    result = api_get("/v1/profile/search", {"identifier": identifier, "type": id_type})
    output(result, agent, quiet)

@cli.command()
@click.argument("txid_arg", required=False)
@click.option("--txid", "-t", required=False)
@click.option("--hops", default=5)
@click.option("--method", default="fifo", type=click.Choice(["fifo","lifo"]))
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def trace(txid_arg, txid, hops, method, agent, quiet):
    """Trace funds with FIFO/LIFO accounting."""
    _require_experimental(
        "fund tracing",
        next_steps=[
            "blockintql history <address>",
            "blockintql chat --interactive",
        ],
    )
    txid = coalesce_address(txid_arg, txid)
    if not txid:
        raise click.UsageError(
            "Provide a transaction id as an argument or with --txid. Example: blockintql trace 0xabc... --hops 5"
        )
    if not quiet and not agent:
        console.print(f"[dim]Tracing {txid[:20]}... ({hops} hops)[/]")
    result = api_post("/v1/trace", {"txid": txid, "hops": hops, "method": method})
    output(result, agent, quiet)

@cli.command()
@click.argument("query", nargs=-1, required=True)
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def query(query, agent, quiet):
    """Natural language blockchain intelligence."""
    _require_experimental(
        "natural-language query",
        next_steps=[
            "blockintql chat --interactive",
            "blockintql history <address>",
        ],
    )
    query_text = " ".join(query).strip()
    if not quiet and not agent: console.print("[dim]Processing...[/]")
    result = api_post("/v1/intelligence/search", {"query": query_text})
    output(result, agent, quiet)


def _run_chat_repl(*, session_id=None, address=None, chain="ethereum", agent=False, quiet=False, grounded=True):
    active_session_id = (session_id or "").strip() or None
    if not quiet and not agent:
        console.print(Panel("BLOCKINTQL", title="BlockINTQL Chat", border_style="cyan", width=70))
        if not get_api_key() and not _wallet_ready_for_requests():
            console.print("[dim]No API key configured. Set BLOCKINTQL_API_KEY or run `blockintql auth --api-key ...`[/dim]")
            console.print("[dim]For local dev testing (free, no credits): export BLOCKINTQL_API_URL=http://127.0.0.1:8000 + the admin key[/dim]")
            console.print("[dim]Wallet mode: blockintql login --auto-pay[/dim]")
            console.print()
    while True:
        try:
            raw = console.input("[bold cyan]>[/bold cyan] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            console.print("  [dim]ended[/dim]")
            return
        if not raw:
            continue
        lowered = raw.lower()
        # Helpful hint if user types shell-like commands inside the chat REPL
        if any(lowered.startswith(p) for p in ("export ", "cd ", "cat ", "ls ", "~/", "./")):
            console.print("  [yellow]You're inside the BlockINTQL Chat REPL.[/yellow]")
            console.print("  [dim]Type /exit (or Ctrl+D) to return to your normal shell prompt.[/dim]")
            console.print("  [dim]Shell commands (export, cat, etc.) are sent as chat messages to the API.[/dim]")
            continue
        if lowered in {"/exit", "exit", "quit", "/quit"}:
            console.print("  [dim]ended[/dim]")
            return
        if lowered in {"/new", "new"}:
            active_session_id = None
            console.print("  [dim]new[/dim]")
            continue
        if lowered in {"/session", "session"}:
            console.print(f"  [dim]session:[/dim] {active_session_id or 'none'}")
            continue
        payload = {"message": raw, "chain": chain, "grounded": grounded}
        if active_session_id:
            payload["session_id"] = active_session_id
        if address:
            payload["address"] = address

        # Full local REPL default: prefer the OSS deterministic core for grounded when no key or local/dev mode
        # This makes bare `blockintql` fully usable locally without server/key for the core compliance layer.
        api_key = get_api_key()
        api_url = os.environ.get("BLOCKINTQL_API_URL", DEFAULT_API_BASE)
        is_local_dev = bool(os.environ.get("BLOCKINTQL_DEV_NO_AUTH")) or "127.0.0.1" in api_url or "localhost" in api_url
        use_local = grounded and (not api_key or is_local_dev)

        if use_local and address:
            try:
                from .deterministic import adjudicate, export_evidence_bundle, Policy
                local_res = adjudicate(address, chain=chain)
                bundle = export_evidence_bundle(
                    subject=address,
                    chain=chain,
                    policy=Policy(),
                    provider_result={},
                    consensus=local_res.get("consensus", {}),
                    final_verdict=local_res,
                )
                # Build full grounded response locally (narrative stub + deterministic)
                narrative = f"[GROUNDED] Screened {address} on {chain}. Verdict {local_res.get('verdict')} (risk {local_res.get('risk_score')}/100) from 3-agent swarm. Using local deterministic core (no server roundtrip in this mode)."
                result = {
                    "narrative": narrative,
                    "blockintql": {
                        "verdict": local_res.get("verdict"),
                        "safe": local_res.get("safe"),
                        "risk_score": local_res.get("risk_score"),
                        "risk_indicators": local_res.get("risk_indicators", []),
                        "entity": local_res.get("entity"),
                    },
                    "consensus": local_res.get("consensus"),
                    "local_evidence_bundle": bundle.to_dict(),
                    "citations": ["Sentinel: sanctions and label intelligence (local)", "Cypher: FIFO source-of-funds (local)", "Nova: patterns/hops (local)"],
                    "cost": {"credits_charged": 0, "model": "local-deterministic"},
                    "session_id": active_session_id or "local-only",
                }
                _render_grounded_chat_box(result)
                continue  # handled locally, no API call
            except Exception as e:
                err_console.print(f"  [yellow]Local deterministic fallback failed ({e}), trying server...[/yellow]")

        # Fallback to server path (existing)
        endpoint = "/v1/blockintql-ask" if grounded else "/v1/chat"
        result = api_post(endpoint, payload, require_auth=True, timeout=120)
        if isinstance(result, dict) and result.get("session_id"):
            active_session_id = result.get("session_id")
        err_text = str((result or {}).get("error") or "") if isinstance(result, dict) else ""
        if "Invalid API key" in err_text or "API key required" in err_text:
            err_console.print("  [red]✗ Invalid API key[/red]")
            err_console.print("  Quick fixes:")
            err_console.print("    export BLOCKINTQL_API_KEY=biq_sk_live_...")
            err_console.print("    blockintql auth --api-key biq_sk_live_...")
            err_console.print("  Local dev bypass (if you have a dev key configured):")
            err_console.print("    export BLOCKINTQL_API_URL=http://127.0.0.1:8000")
            err_console.print("    export BLOCKINTQL_API_KEY=biq_sk_live_... (your dev key)")
            err_console.print("    (start the local server with admin bypass first)")
            err_console.print("  Or wallet: blockintql login --auto-pay --max-payment 0.10")
            continue
        if grounded and isinstance(result, dict) and result.get("narrative") and isinstance(result.get("blockintql"), dict):
            _render_grounded_chat_box(result)
            # One-click evidence export hint for the deterministic layer
            if result.get("local_evidence_bundle"):
                console.print("  [dim]One-click evidence: run 'blockintql deterministic export-evidence " + (address or "ADDRESS") + " --out evidence.json' or copy the bundle from result[/dim]")
        else:
            output(result, agent, quiet)


@cli.command()
@click.argument("message", nargs=-1, required=False, metavar="[MESSAGE]")
@click.option("--session-id", default=None, help="Continue an existing BlockINTQL chat session.")
@click.option("--address", "-a", default=None, help="Optional address to anchor the chat turn.")
@click.option("--chain", "-c", default="ethereum", type=click.Choice(["bitcoin", "ethereum"]))
@click.option("--interactive", "-i", is_flag=True, help="Start multi-turn interactive chat mode.")
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
@click.option("--grounded/--no-grounded", default=True, help="BlockINTQL grounded mode")
def chat(message, session_id, address, chain, interactive, agent, quiet, grounded):
    """BlockINTQL Chat.

    Run bare (no MESSAGE) or with --interactive to start the REPL.
    Provide MESSAGE for a single grounded turn.
    """
    message_text = " ".join(message).strip()
    if interactive or not message_text:
        _run_chat_repl(
            session_id=session_id,
            address=address,
            chain=chain,
            agent=agent,
            quiet=quiet,
            grounded=grounded,
        )
        return
    if not quiet and not agent:
        console.print("[dim]Chatting with BlockINTQL...[/]")
    payload = {"message": message_text, "chain": chain, "grounded": grounded}
    if session_id:
        payload["session_id"] = session_id
    if address:
        payload["address"] = address
    endpoint = "/v1/blockintql-ask" if grounded else "/v1/chat"
    result = api_post(endpoint, payload, require_auth=True, timeout=120)
    output(result, agent, quiet)


def _render_grounded_chat_box(data):
    block = data.get("blockintql") or {}
    narrative = data.get("narrative") or ""
    citations = data.get("citations") or []
    cost = data.get("cost") or {}
    v = block.get("verdict", "UNKNOWN")
    risk = block.get("risk_score", 0)
    safe = block.get("safe", True)
    color = "green" if v == "CLEAR" else ("yellow" if v == "CAUTION" else "red")
    console.print()
    console.print(Panel(f"[bold {color}]{v}[/bold {color}]  risk {risk}/100  {'SAFE' if safe else 'BLOCK'}", title="BLOCKINTQL", border_style=color, width=70))
    if narrative:
        console.print(Panel(narrative, title="Response", border_style="dim", width=70))
    if citations:
        console.print("  [dim]citations:[/dim] " + ", ".join(citations))
    if cost:
        ch = cost.get("credits_charged", 0)
        console.print(f"  [dim]cost:[/dim] {ch} credits")
    # Support compound chat responses that include chart data (e.g. "screen X and create a chart")
    chart = data.get("chart") or {}
    if chart:
        tok = chart.get("token", "USDC")
        days = chart.get("days", 30)
        ina = float(chart.get("in", 0))
        outa = float(chart.get("out", 0))
        net = float(chart.get("net", ina - outa))
        # simple bar using existing helper
        peak = max(ina, outa, 1.0)
        in_bar = _bar(ina, peak, width=14)
        out_bar = _bar(outa, peak, width=14)
        console.print(f"  [dim]{days}d {tok} chart[/dim]  in {ina:,.0f} {in_bar}  out {outa:,.0f} {out_bar}  net {net:+,.0f}")
    # Render per-agent votes when the server returns proper sonar_consensus_v1 (so agents are visibly voting on real work, not just labels)
    cs = data.get("consensus") or {}
    if cs.get("model") == "sonar_consensus_v1" or cs.get("votes"):
        vote_split = cs.get("vote_split") or {}
        console.print(f"  [dim]─[/dim]")
        console.print("  [dim]SONAR CONSENSUS (3 agents voted)[/dim]")
        if vote_split:
            console.print(
                f"  [dim]split   [/dim] block={vote_split.get('block', 0)} review={vote_split.get('review', 0)} clear={vote_split.get('clear', 0)}"
            )
        for row in (cs.get("votes") or [])[:3]:
            agent = str(row.get("agent") or row.get("codename") or "agent")
            vote = str(row.get("vote") or "").upper()
            role = str(row.get("role") or "")
            reason = str(row.get("reason") or "")[:80]
            line = f"  [dim]  {agent} · {vote}"
            if role:
                line += f" · {role}"
            if reason:
                line += f" — {reason}"
            console.print(line)
    console.print()


def _run_graph_prompt_repl():
    console.print(Panel("BlockINTQL Graph Shell", border_style="cyan", width=70))
    console.print("[dim]Type a prompt to compile a deterministic shell spec. /exit to quit.[/dim]")
    while True:
        try:
            raw = console.input("[bold cyan]graph>[/bold cyan] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            console.print("  [dim]ended[/dim]")
            return
        if not raw:
            continue
        lowered = raw.lower()
        if lowered in {"/exit", "exit", "quit", "/quit"}:
            console.print("  [dim]ended[/dim]")
            return
        if lowered in {"/help", "help", "?"}:
            console.print("  [dim]Enter natural language (e.g. \"executive summary, graph first, wide drawer for mixer flows\").[/dim]")
            continue
        compiled = compile_graph_shell_prompt(raw)
        payload = {
            "surface": "graph_shell",
            "prompt": raw,
            "shell_spec": compiled.get("spec") or {},
            "matched_rules": compiled.get("matched_rules") or [],
        }
        explorer_base = get_graph_shell_base()
        if explorer_base:
            payload["explorer_url"] = build_graph_shell_url(
                explorer_base,
                prompt=raw,
                spec=payload["shell_spec"],
                seed=None,
            )
        output(payload, agent=False, quiet=False)
        console.print("[dim]refine with another prompt or /exit[/dim]")


@cli.group()
def create():
    """Create generated assets from natural-language prompts."""


@create.command("image")
@click.argument("prompt", nargs=-1, required=True)
@click.option("--model", default="gpt-image-1")
@click.option("--size", default="1024x1024", type=click.Choice(["1024x1024", "1536x1024", "1024x1536"]))
@click.option("--quality", default="high", type=click.Choice(["low", "medium", "high"]))
@click.option("--style", default="natural", type=click.Choice(["natural", "vivid"]))
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def create_image(prompt, model, size, quality, style, agent, quiet):
    """Generate an image from a prompt."""
    prompt_text = " ".join(prompt).strip()
    if not quiet and not agent:
        console.print("[dim]Generating image...[/]")
    payload = {
        "prompt": prompt_text,
        "model": model,
        "size": size,
        "quality": quality,
        "style": style,
    }
    result = api_post("/v1/images/generate", payload, require_auth=True, timeout=120)
    output(result, agent, quiet)

@cli.command()
@click.argument("goal", nargs=-1, required=False)
@click.option("--address", "-a", default=None)
@click.option("--workspace-id", default=None, help="Continue an existing workspace instead of starting fresh.")
@click.option("--chain", "-c", default="ethereum", type=click.Choice(["bitcoin","ethereum"]))
@click.option("--budget-credits", type=int, default=None)
@click.option("--budget-usd", type=float, default=None)
@click.option("--upto-budget-usd", type=float, default=None)
@click.option("--mode", "execution_mode", type=click.Choice(["cheap", "standard", "deep"]), default=None, help="Choose which execution profile to plan around.")
@click.option("--open-workspace", is_flag=True, help="Prefer workspace execution and open a workspace when possible.")
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def ask(goal, address, workspace_id, chain, budget_credits, budget_usd, upto_budget_usd, execution_mode, open_workspace, agent, quiet):
    """Plan an investigation and optionally open a workspace."""
    _require_experimental(
        "investigation planner",
        next_steps=[
            "blockintql chat --interactive",
            "blockintql history <address>",
        ],
    )
    goal_text = " ".join(goal).strip()
    if not goal_text:
        raise click.UsageError(
            "Provide an investigation goal. Example: blockintql ask \"Plan a compliance screening workflow for 0x...\""
        )
    if not quiet and not agent:
        console.print("[dim]Planning investigation...[/]")
    run_ask_flow(
        goal_text,
        address=address,
        workspace_id=workspace_id,
        chain=chain,
        budget_credits=budget_credits,
        budget_usd=budget_usd,
        upto_budget_usd=upto_budget_usd,
        open_workspace=open_workspace,
        mode=execution_mode,
        agent=agent,
        quiet=quiet,
    )


@cli.group(cls=DefaultingGroup, invoke_without_command=True)
def prediction():
    """Prediction-market investigation commands."""
    _require_experimental(
        "prediction market investigations",
        next_steps=[
            "blockintql chat --interactive",
            "blockintql screen <address>",
        ],
    )


prediction.default_command_name = "analysis"


@prediction.group(hidden=True)
def market():
    """Prediction-market workflows for Ethereum investigations."""
    _require_experimental(
        "prediction market investigations",
        next_steps=[
            "blockintql chat --interactive",
            "blockintql screen <address>",
        ],
    )


def _run_prediction_market_analysis(address_arg, address, workspace_id, chain, budget_credits, budget_usd, upto_budget_usd, execution_mode, open_workspace, agent, quiet):
    address = coalesce_address(address_arg, address)
    if not address:
        raise click.UsageError(
            "Provide an address as an argument or with --address. Example: blockintql prediction 0x123..."
        )
    if not quiet and not agent:
        console.print("[dim]Planning prediction-market investigation...[/]")
    goal = "Investigate prediction market exposure, counterparties, venue interactions, and event-driven flows"
    run_ask_flow(
        goal,
        address=address,
        workspace_id=workspace_id,
        chain=chain,
        budget_credits=budget_credits,
        budget_usd=budget_usd,
        upto_budget_usd=upto_budget_usd,
        open_workspace=open_workspace,
        mode=execution_mode,
        agent=agent,
        quiet=quiet,
    )


@prediction.command("analysis")
@click.argument("address_arg", required=False)
@click.option("--address", "-a", required=False)
@click.option("--workspace-id", default=None, help="Continue an existing workspace instead of starting fresh.")
@click.option("--chain", "-c", default="ethereum", type=click.Choice(["ethereum"]))
@click.option("--budget-credits", type=int, default=None)
@click.option("--budget-usd", type=float, default=None)
@click.option("--upto-budget-usd", type=float, default=None)
@click.option("--mode", "execution_mode", type=click.Choice(["cheap", "standard", "deep"]), default=None, help="Choose which execution profile to plan around.")
@click.option("--open-workspace/--plan-only", default=True, show_default=True, help="Open the recommended workspace for deeper prediction-market analysis.")
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def prediction_market_analysis(address_arg, address, workspace_id, chain, budget_credits, budget_usd, upto_budget_usd, execution_mode, open_workspace, agent, quiet):
    """Plan or open a prediction-market investigation workflow."""
    _run_prediction_market_analysis(
        address_arg, address, workspace_id, chain, budget_credits, budget_usd,
        upto_budget_usd, execution_mode, open_workspace, agent, quiet,
    )


@market.command("analysis")
@click.argument("address_arg", required=False)
@click.option("--address", "-a", required=False)
@click.option("--workspace-id", default=None, help="Continue an existing workspace instead of starting fresh.")
@click.option("--chain", "-c", default="ethereum", type=click.Choice(["ethereum"]))
@click.option("--budget-credits", type=int, default=None)
@click.option("--budget-usd", type=float, default=None)
@click.option("--upto-budget-usd", type=float, default=None)
@click.option("--mode", "execution_mode", type=click.Choice(["cheap", "standard", "deep"]), default=None, help="Choose which execution profile to plan around.")
@click.option("--open-workspace/--plan-only", default=True, show_default=True, help="Open the recommended workspace for deeper prediction-market analysis.")
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def prediction_market_analysis_legacy(address_arg, address, workspace_id, chain, budget_credits, budget_usd, upto_budget_usd, execution_mode, open_workspace, agent, quiet):
    """Backward-compatible alias for prediction analysis."""
    _run_prediction_market_analysis(
        address_arg, address, workspace_id, chain, budget_credits, budget_usd,
        upto_budget_usd, execution_mode, open_workspace, agent, quiet,
    )

@cli.command()
@click.option("--agent", is_flag=True)
def providers(agent):
    """List attribution providers — all called locally, keys never leave your machine."""
    data = list_providers()
    if agent or not sys.stdout.isatty():
        click.echo(json.dumps(data, indent=2))
        return
    t = Table(title="Attribution Providers (all local — keys never sent to BlockINTQL)",
              box=box.ROUNDED, border_style="blue")
    t.add_column("Provider", style="bold yellow")
    t.add_column("Description")
    t.add_column("Key Required")
    for p in data:
        t.add_row(p["name"], p["description"], "No" if p["name"] in ("generic",) else "Yes")
    console.print(t)

@cli.command()
@click.option("--install", is_flag=True)
@click.option("--agent", is_flag=True)
def skills(install, agent):
    """List capabilities or install into agent context."""
    if install:
        r = httpx.get(f"{API_BASE}/skills/skill.md", timeout=10)
        click.echo(r.text)
        return
    if agent or not sys.stdout.isatty():
        click.echo(json.dumps({
            "commands": ["verdict","screen","history","stats","tx","eth","stablecoins","chart","prediction","analyze","profile","trace","query","chat","ask","workspace","wallet","capabilities","providers","status","admin"],
            "providers": [p["name"] for p in list_providers()],
            "privacy": "Provider keys never leave your machine",
            "mcp_server": "https://blockintql-mcp-385334043904.us-central1.run.app/mcp",
            "source": "https://github.com/block6iq/blockintql-cli",
        }, indent=2))
        return
    t = Table(title="BlockINTQL CLI", box=box.ROUNDED, border_style="blue")
    t.add_column("Command", style="bold yellow", width=12)
    t.add_column("Description")
    t.add_column("Example")
    rows = [
        ("verdict","CLEAR/CAUTION/BLOCK","blockintql verdict --address 1ABC..."),
        ("screen","Screen + provider","blockintql screen --address 0x123... --provider trm --provider-key $KEY"),
        ("history","Ethereum wallet history","blockintql history --address 0x123..."),
        ("stats","Ethereum wallet summary","blockintql stats --address 0x123..."),
        ("tx","Verbose Ethereum tx","blockintql tx --txid 0xabc..."),
        ("eth","Ethereum-first namespace","blockintql eth stablecoins history 0x123..."),
        ("stablecoins","Ethereum stablecoin analytics","blockintql stablecoins history --address 0x123..."),
        ("chart","Terminal-native charts","blockintql chart wallet-stablecoin-balances 0x123..."),
        ("prediction","Prediction-market workflow","blockintql prediction 0x123..."),
        ("analyze","Multi-agent analysis",'blockintql analyze "check for sanctions"'),
        ("profile","OP_RETURN identity","blockintql profile --identifier @handle"),
        ("trace","FIFO/LIFO tracing","blockintql trace --txid abc123..."),
        ("query","Natural language",'blockintql query "is this safe?"'),
        ("ask","Plan or open workspace",'blockintql ask "Investigate this wallet" --address 0x123...'),
        ("workspace","Manage workspaces","blockintql workspace review <workspace_id>"),
        ("wallet","Wallet-backed access","blockintql wallet status"),
        ("capabilities","Discover supported commands","blockintql capabilities --category stablecoins"),
        ("chat","Scoped compliance + blockchain forensics conversation","blockintql chat \"Explain the sanctions risk for 0x...\" --address 0x..."),
        ("providers","List providers","blockintql providers"),
        ("skills","Agent skills","blockintql skills --install >> CONTEXT.md"),
    ]
    for r in rows: t.add_row(*r)
    console.print(t)
    console.print("\n[dim]Provider keys stay on your machine. BlockINTQL only sees the address.[/]")
    console.print("[dim]Source: github.com/block6iq/blockintql-cli[/]")


@cli.group()
def provider():
    """Connect, inspect, and test local attribution providers."""


@provider.command("connect")
@click.option("--provider", "provider_name", required=True,
              type=click.Choice(PUBLIC_PROVIDER_CHOICES))
@click.option("--provider-key", default=None, envvar="BLOCKINTQL_PROVIDER_KEY",
              help="Provider API key. If passed directly, it will be saved locally unless already supplied by env.")
@click.option("--provider-url", default=None,
              help="Required for generic/blockintai. Use {address} and optionally {chain} placeholders.")
@click.option("--risk-field", default=None, help="Field path for provider risk score, e.g. result.risk.score")
@click.option("--entity-field", default=None, help="Field path for provider entity name, e.g. result.entity.name")
@click.option("--auth-header", default=None, help="Custom auth header name for generic/blockintai providers.")
@click.option("--auth-prefix", default=None, help="Custom auth prefix. Use '' for raw key headers.")
@click.option("--set-default", is_flag=True, default=True, show_default=True,
              help="Use this provider by default for screen/verdict.")
@click.option("--agent", is_flag=True)
def provider_connect(provider_name, provider_key, provider_url, risk_field, entity_field, auth_header, auth_prefix, set_default, agent):
    """Save local provider connection settings."""
    normalized = "generic" if provider_name == "blockintai" else provider_name
    if provider_name == "blockintai" and not provider_url:
        provider_url = "https://blockint.ai/api/v1/screen/{address}"
    if provider_name in CUSTOM_ROUTE_PROVIDERS and not provider_url:
        raise click.UsageError(
            f"{provider_name} provider connections require --provider-url, for example https://api.example.com/screen/{{address}}"
        )
    config = load_config()
    provider_cfg = {
        "provider": provider_name,
        "provider_url": provider_url or "",
    }
    if risk_field is not None:
        provider_cfg["risk_field"] = risk_field
    if entity_field is not None:
        provider_cfg["entity_field"] = entity_field
    if provider_name == "blockintai":
        provider_cfg["auth_header"] = auth_header or "x-api-key"
        provider_cfg["auth_prefix"] = "" if auth_prefix is None else auth_prefix
        provider_cfg["risk_field"] = provider_cfg.get("risk_field") or "riskScore"
        provider_cfg["entity_field"] = provider_cfg.get("entity_field") or "entity"
    elif auth_header is not None:
        provider_cfg["auth_header"] = auth_header
        provider_cfg["auth_prefix"] = "" if auth_prefix is None else auth_prefix
    if provider_key:
        provider_cfg["provider_key"] = provider_key
    config["provider_connection"] = provider_cfg
    if set_default:
        config["default_provider"] = provider_name
    save_config(config)
    payload = {
        "provider": provider_name,
        "default_provider": provider_name if set_default else config.get("default_provider"),
        "provider_key_saved": bool(provider_key),
        "provider_url": provider_url or None,
        "risk_field": provider_cfg.get("risk_field"),
        "entity_field": provider_cfg.get("entity_field"),
        "auth_header": provider_cfg.get("auth_header"),
        "auth_prefix": provider_cfg.get("auth_prefix"),
        "route": provider_route_hint(provider_name, provider_url),
        "next": f"blockintql provider test --provider {provider_name} --address 0x...",
    }
    spec = get_provider_spec(provider_name)
    if spec:
        payload["provider_spec"] = {
            "status": spec.get("status"),
            "verification": spec.get("verification"),
            "docs_url": spec.get("docs_url"),
            "notes": spec.get("notes"),
        }
    if agent or not sys.stdout.isatty():
        click.echo(json.dumps(payload, indent=2))
        return
    console.print(f"[green]Saved provider connection for {provider_name}.[/]")
    console.print(f"[dim]Route:[/] {payload['route']}")
    if payload.get("risk_field"):
        console.print(f"[dim]Risk field:[/] {payload['risk_field']}")
    if payload.get("entity_field"):
        console.print(f"[dim]Entity field:[/] {payload['entity_field']}")
    if payload.get("auth_header"):
        console.print(f"[dim]Auth header:[/] {payload['auth_header']}")
    if provider_key:
        console.print("[dim]Provider key:[/] saved locally for CLI use")
    else:
        console.print("[dim]Provider key:[/] using BLOCKINTQL_PROVIDER_KEY from your shell when present")
    console.print(f"[dim]Next:[/] {payload['next']}")


@provider.command("status")
@click.option("--agent", is_flag=True)
def provider_status(agent):
    """Show the currently configured provider connection."""
    config = load_config()
    provider_cfg = config.get("provider_connection") or {}
    provider_name = provider_cfg.get("provider") or config.get("default_provider")
    provider_key = os.environ.get("BLOCKINTQL_PROVIDER_KEY") or provider_cfg.get("provider_key")
    provider_url = provider_cfg.get("provider_url")
    risk_field = provider_cfg.get("risk_field")
    entity_field = provider_cfg.get("entity_field")
    auth_header = provider_cfg.get("auth_header")
    auth_prefix = provider_cfg.get("auth_prefix")
    payload = {
        "configured": bool(provider_name),
        "provider": provider_name,
        "default_provider": config.get("default_provider"),
        "provider_key_available": bool(provider_key),
        "provider_key_source": "env" if os.environ.get("BLOCKINTQL_PROVIDER_KEY") else ("config" if provider_cfg.get("provider_key") else None),
        "provider_url": provider_url or None,
        "risk_field": risk_field,
        "entity_field": entity_field,
        "auth_header": auth_header,
        "auth_prefix": auth_prefix,
        "route": provider_route_hint(provider_name or "", provider_url),
    }
    spec = get_provider_spec(provider_name or "")
    if spec:
        payload["provider_spec"] = {
            "status": spec.get("status"),
            "verification": spec.get("verification"),
            "docs_url": spec.get("docs_url"),
            "notes": spec.get("notes"),
        }
    if agent or not sys.stdout.isatty():
        click.echo(json.dumps(payload, indent=2))
        return
    if not provider_name:
        console.print("[yellow]No provider is configured.[/]")
        console.print("[dim]Try:[/] blockintql provider connect --provider trm --provider-key YOUR_KEY")
        return
    console.print(f"[green]Provider:[/] {provider_name}")
    console.print(f"[dim]Default:[/] {payload['default_provider'] or provider_name}")
    console.print(f"[dim]Key available:[/] {'yes' if payload['provider_key_available'] else 'no'}")
    console.print(f"[dim]Key source:[/] {payload['provider_key_source'] or 'none'}")
    console.print(f"[dim]Route:[/] {payload['route']}")
    if spec:
        console.print(f"[dim]Spec status:[/] {spec.get('status')} ({spec.get('verification')})")
        if spec.get("docs_url"):
            console.print(f"[dim]Docs:[/] {spec.get('docs_url')}")
    if provider_url:
        console.print(f"[dim]URL template:[/] {provider_url}")
    if risk_field:
        console.print(f"[dim]Risk field:[/] {risk_field}")
    if entity_field:
        console.print(f"[dim]Entity field:[/] {entity_field}")
    if auth_header:
        console.print(f"[dim]Auth header:[/] {auth_header}")
        console.print(f"[dim]Auth prefix:[/] {auth_prefix if auth_prefix is not None else 'Bearer'}")


@provider.command("test")
@click.option("--provider", "provider_name", required=False,
              type=click.Choice(PUBLIC_PROVIDER_CHOICES))
@click.option("--provider-key", default=None, envvar="BLOCKINTQL_PROVIDER_KEY")
@click.option("--provider-url", default=None)
@click.option("--risk-field", default=None)
@click.option("--entity-field", default=None)
@click.option("--auth-header", default=None)
@click.option("--auth-prefix", default=None)
@click.option("--address", "-a", required=True)
@click.option("--chain", "-c", default="ethereum", type=click.Choice(["bitcoin", "ethereum"]))
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def provider_test(provider_name, provider_key, provider_url, risk_field, entity_field, auth_header, auth_prefix, address, chain, agent, quiet):
    """Call the local provider route directly and show the normalized response."""
    user_auth_header = auth_header
    user_auth_prefix = auth_prefix
    settings = get_provider_configured_settings(provider_name)
    selected = provider_name or settings.get("raw_provider") or settings.get("provider")
    selected = selected or "generic"
    effective_name = "generic" if selected == "blockintai" else selected
    provider_key = provider_key or settings.get("provider_key") or ""
    provider_url = provider_url or settings.get("provider_url")
    risk_field = risk_field or settings.get("risk_field")
    entity_field = entity_field or settings.get("entity_field")
    auth_header = auth_header or settings.get("auth_header")
    auth_prefix = settings.get("auth_prefix") if auth_prefix is None else auth_prefix
    if selected == "blockintai":
        auth_header = user_auth_header or auth_header or "x-api-key"
        auth_prefix = "" if user_auth_prefix is None else user_auth_prefix
        risk_field = risk_field or "riskScore"
        entity_field = entity_field or "entity"
    elif selected == "trm":
        auth_header = user_auth_header or "Authorization"
        auth_prefix = "Basic" if user_auth_prefix is None else user_auth_prefix
    elif selected == "chainalysis":
        auth_header = user_auth_header or "Token"
        auth_prefix = "" if user_auth_prefix is None else user_auth_prefix
    elif selected == "elliptic":
        auth_header = user_auth_header or "x-access-key"
        auth_prefix = "" if user_auth_prefix is None else user_auth_prefix
    elif selected == "nomis":
        auth_header = user_auth_header or "Authorization"
        auth_prefix = "Bearer" if user_auth_prefix is None else user_auth_prefix
    if selected in CUSTOM_ROUTE_PROVIDERS and not provider_url:
        raise click.UsageError(
            f"{selected} provider tests require --provider-url or a saved provider connection."
        )
    if not quiet and not agent:
        console.print(f"[dim]Testing provider {selected} against {address[:20]}...[/]")
        console.print(f"[dim]Route:[/] {provider_route_hint(selected, provider_url)}")
    provider_obj = get_provider(
        effective_name,
        provider_key,
        url_template=provider_url,
        risk_field=risk_field or ("riskScore" if selected == "blockintai" else "risk_score"),
        entity_field=entity_field or "entity",
        auth_header=auth_header or "Authorization",
        auth_prefix="Bearer" if auth_prefix is None else auth_prefix,
    )
    if not provider_obj:
        raise click.UsageError(f"Unknown provider '{selected}'.")
    result = provider_obj.get_address_risk(address, chain)
    spec = get_provider_spec(selected)
    payload = {
        "provider": selected,
        "chain": chain,
        "address": address,
        "route": provider_route_hint(selected, provider_url),
        "risk_field": risk_field or "risk_score",
        "entity_field": entity_field or "entity",
        "auth_header": auth_header or ("x-api-key" if selected == "blockintai" else "Authorization"),
        "auth_prefix": auth_prefix if auth_prefix is not None else ("" if selected == "blockintai" else "Bearer"),
        "normalized_result": result,
        "canonical_policy": adjudicate_provider_result(result),
    }
    if spec:
        payload["provider_spec"] = {
            "status": spec.get("status"),
            "verification": spec.get("verification"),
            "docs_url": spec.get("docs_url"),
            "notes": spec.get("notes"),
        }
    output(payload, agent, quiet)

@cli.command()
@click.option("--cdp-key-id", default=None, envvar="BLOCKINTQL_CDP_KEY_ID")
@click.option("--auto-pay", is_flag=True)
@click.option("--max-payment", default=0.10)
def pay(cdp_key_id, auto_pay, max_payment):
    """Store local payment preferences for wallet-backed billing flows."""
    config = load_config()
    payment_config = {"type": "cdp", "auto_pay": auto_pay, "max_payment_usd": max_payment}
    payment_config["cdp_key_id"] = cdp_key_id or os.environ.get("BLOCKINTQL_CDP_KEY_ID")
    payment_config["private_key_env"] = "BLOCKINTQL_CDP_PRIVATE_KEY"
    config["payment"] = payment_config
    save_config(config)
    console.print("[green]Saved local payment preferences (wallet session).[/]")
    console.print(f"[green]Auto-pay preference: {'enabled' if auto_pay else 'disabled'} | Max: ${max_payment}[/]")
    console.print("[dim]Wallet secrets are not persisted by this command. Keep them in your wallet session manager or environment.[/]")


@cli.group()
def wallet():
    """Connect and inspect wallet-backed payment access."""

@cli.group()
def compensation():
    """Claim and inspect degraded x402 compensation tokens."""


def _configure_cdp_wallet(auto_pay, max_payment, cdp_key_id, agent, *, command_name="wallet connect"):
    if cdp_key_id:
        os.environ["BLOCKINTQL_CDP_KEY_ID"] = cdp_key_id

    configured_key_id = cdp_key_id or os.environ.get("BLOCKINTQL_CDP_KEY_ID")
    configured_private_key_env = None
    if os.environ.get("BLOCKINTQL_CDP_PRIVATE_KEY"):
        configured_private_key_env = "BLOCKINTQL_CDP_PRIVATE_KEY"
    elif os.environ.get("BLOCKINTQL_PRIVATE_KEY"):
        configured_private_key_env = "BLOCKINTQL_PRIVATE_KEY"
    elif os.environ.get("EVM_PRIVATE_KEY"):
        configured_private_key_env = "EVM_PRIVATE_KEY"

    configured_private_key = os.environ.get(configured_private_key_env) if configured_private_key_env else None
    if not configured_private_key:
        message = {
            "error": "No wallet private key found for x402 payments.",
            "next_step": "Set BLOCKINTQL_PRIVATE_KEY (or EVM_PRIVATE_KEY / BLOCKINTQL_CDP_PRIVATE_KEY), then rerun login.",
            "example": "export BLOCKINTQL_PRIVATE_KEY='0x...'",
        }
        if agent or not sys.stdout.isatty():
            click.echo(json.dumps(message, indent=2))
        else:
            err_console.print("[red]No wallet private key found for x402 payments.[/]")
            console.print("[dim]Next step:[/] export BLOCKINTQL_PRIVATE_KEY='0x...'")
            console.print("[dim]Alternative:[/] export EVM_PRIVATE_KEY='0x...'")
            console.print(f"[dim]Then run:[/] blockintql {command_name} --auto-pay --max-payment 0.10")
        return False

    config = load_config()
    wallet_type = "cdp" if configured_private_key_env == "BLOCKINTQL_CDP_PRIVATE_KEY" else "privatekey"
    payment_config = {
        "type": wallet_type,
        "auto_pay": auto_pay,
        "max_payment_usd": max_payment,
        "cdp_key_id": configured_key_id,
        "private_key_env": configured_private_key_env or "BLOCKINTQL_PRIVATE_KEY",
    }
    config["payment"] = payment_config
    save_config(config)

    result = {
        "wallet_type": wallet_type,
        "auto_pay": auto_pay,
        "max_payment_usd": max_payment,
        "api_key_required": False,
        "ready": True,
        "next": [
            "unset BLOCKINTQL_API_KEY",
            "blockintql verdict --address 0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045 --agent",
        ],
    }
    if agent or not sys.stdout.isatty():
        click.echo(json.dumps(result, indent=2))
        return True
    console.print(f"[green]Wallet connected for x402 access ({wallet_type}).[/]")
    console.print(f"[green]Auto-pay: {'enabled' if auto_pay else 'disabled'} | Max payment: ${max_payment}[/]")
    console.print("[dim]No API key is required for wallet-backed x402 requests.[/]")
    console.print("[dim]Next:[/] unset BLOCKINTQL_API_KEY")
    console.print("[dim]Try:[/] blockintql verdict --address 0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045 --agent")
    return True


@cli.command("login")
@click.option("--auto-pay", is_flag=True, default=True)
@click.option("--max-payment", default=0.10, show_default=True, type=float)
@click.option("--cdp-key-id", default=None, envvar="BLOCKINTQL_CDP_KEY_ID")
@click.option("--agent", is_flag=True)
def login(auto_pay, max_payment, cdp_key_id, agent):
    """Connect a wallet session for no-key x402 access."""
    has_any_private_key = (
        os.environ.get("BLOCKINTQL_CDP_PRIVATE_KEY")
        or os.environ.get("BLOCKINTQL_PRIVATE_KEY")
        or os.environ.get("EVM_PRIVATE_KEY")
    )
    if not (cdp_key_id or os.environ.get("BLOCKINTQL_CDP_KEY_ID") or has_any_private_key):
        message = {
            "error": "blockintql login is for wallet-backed x402 access, not API-key sign-in.",
            "api_key_flow": [
                "Buy credits: blockintql buy",
                "After payment, copy the API key shown once on the success screen",
                "Save it: blockintql auth --api-key biq_sk_live_...",
            ],
            "wallet_flow": [
                "export BLOCKINTQL_PRIVATE_KEY='0x...'",
                "or export EVM_PRIVATE_KEY='0x...'",
                "blockintql login --auto-pay --max-payment 0.10",
            ],
        }
        if agent or not sys.stdout.isatty():
            click.echo(json.dumps(message, indent=2))
        else:
            err_console.print("[yellow]blockintql login is for wallet-backed x402 access, not API-key sign-in.[/]")
            console.print("[dim]API key flow:[/]")
            console.print("[dim]  1. blockintql buy[/]")
            console.print("[dim]  2. Copy the API key shown once on the payment success screen[/]")
            console.print("[dim]  3. blockintql auth --api-key biq_sk_live_...[/]")
            console.print("[dim]Wallet flow:[/]")
            console.print("[dim]  export BLOCKINTQL_PRIVATE_KEY='0x...'[/]")
            console.print("[dim]  or export EVM_PRIVATE_KEY='0x...'[/]")
            console.print("[dim]  blockintql login --auto-pay --max-payment 0.10[/]")
        return
    _configure_cdp_wallet(auto_pay, max_payment, cdp_key_id, agent, command_name="login")


@wallet.command("connect")
@click.option("--auto-pay", is_flag=True, default=True)
@click.option("--max-payment", default=0.10, show_default=True, type=float)
@click.option("--cdp-key-id", default=None, envvar="BLOCKINTQL_CDP_KEY_ID")
@click.option("--agent", is_flag=True)
def wallet_connect(auto_pay, max_payment, cdp_key_id, agent):
    """Configure wallet-based access so x402 requests can run with no API key."""
    _configure_cdp_wallet(auto_pay, max_payment, cdp_key_id, agent)


@wallet.command("status")
@click.option("--agent", is_flag=True)
def wallet_status(agent):
    """Show current wallet-based payment readiness."""
    config = load_config()
    payment_config = load_payment_config(config)
    if not payment_config:
        payload = {"ready": False, "configured": False, "message": "No wallet payment configuration found."}
        if agent or not sys.stdout.isatty():
            click.echo(json.dumps(payload, indent=2))
        else:
            console.print("[yellow]No wallet payment configuration found.[/]")
            console.print("[dim]Run:[/] blockintql login --auto-pay --max-payment 0.10")
        return

    try:
        ensure_wallet_runtime_ready(payment_config)
        ready = True
    except Exception:
        ready = False
    payload = {
        "configured": True,
        "ready": ready,
        "wallet_type": payment_config.wallet_type,
        "auto_pay": payment_config.auto_pay,
        "max_payment_usd": payment_config.max_payment_usd,
        "private_key_env": payment_config.private_key_env,
        "api_key_required": False,
    }
    if agent or not sys.stdout.isatty():
        click.echo(json.dumps(payload, indent=2))
        return
    if ready:
        console.print(f"[green]Wallet access is ready ({payment_config.wallet_type}).[/]")
    else:
        console.print(f"[yellow]Wallet config exists but the shell is missing {payment_config.private_key_env}.[/]")
    console.print(f"[dim]Auto-pay:[/] {'enabled' if payment_config.auto_pay else 'disabled'}")
    console.print(f"[dim]Max payment:[/] ${payment_config.max_payment_usd}")


@wallet.command("doctor")
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def wallet_doctor(agent, quiet):
    """Run wallet-backed x402 preflight diagnostics."""
    config = load_config()
    payment_config = load_payment_config(config)
    checks = []
    summary = {"ready": False, "checks": checks}

    if not payment_config:
        checks.append({"name": "payment_config", "ok": False, "detail": "No wallet payment configuration found."})
        checks.append({"name": "next", "ok": False, "detail": "Run: blockintql login --auto-pay --max-payment 0.10"})
        output(summary, agent, quiet)
        return

    checks.append({"name": "wallet_type", "ok": True, "detail": payment_config.wallet_type})
    checks.append({"name": "auto_pay", "ok": bool(payment_config.auto_pay), "detail": "enabled" if payment_config.auto_pay else "disabled"})

    key_value = get_evm_private_key(payment_config)
    validation = validate_evm_private_key(key_value)
    key_check = {"name": "private_key_format", "ok": bool(validation.get("ok"))}
    if validation.get("ok"):
        key_check["detail"] = "valid 0x-prefixed 64-byte hex key"
    else:
        key_check["detail"] = validation.get("reason") or "invalid"
        if "length" in validation:
            key_check["length"] = validation["length"]
    checks.append(key_check)

    try:
        x402_info = api_get("/v1/x402/info", require_auth=False, timeout=20)
        if isinstance(x402_info, dict) and not x402_info.get("error"):
            checks.append({"name": "x402_info", "ok": True, "detail": "reachable"})
        else:
            checks.append({"name": "x402_info", "ok": False, "detail": str(x402_info.get("error") if isinstance(x402_info, dict) else x402_info)})
    except Exception as exc:
        checks.append({"name": "x402_info", "ok": False, "detail": str(exc)})

    summary["ready"] = all(bool(c.get("ok")) for c in checks if c.get("name") not in {"wallet_type"})
    if not summary["ready"]:
        summary["next"] = [
            "Ensure BLOCKINTQL_PRIVATE_KEY is a real 66-char 0x-prefixed hex key",
            "Run: blockintql login --auto-pay --max-payment 0.10",
            "Retry with: blockintql verdict --address 0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045 --agent",
        ]
    output(summary, agent, quiet)


@compensation.command("claim")
@click.option("--token", "compensation_token", required=False, default=None, help="Compensation token from a degraded x402 response header.")
@click.option("--api-key", default=None, help="Optional API key override. Defaults to current auth key.")
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def compensation_claim(compensation_token, api_key, agent, quiet):
    """Claim a degraded x402 compensation token as BlockINTQL API credits."""
    token = str(compensation_token or "").strip()
    captured_at = None
    if not token:
        token, captured_at = get_last_compensation_token()
    key_to_use = str(api_key or get_api_key() or "").strip()
    if not token:
        output(
            {
                "error": "A compensation token is required.",
                "next": [
                    "Run a wallet-backed x402 request that returns compensation",
                    "Then run: blockintql compensation claim",
                ],
            },
            agent,
            quiet,
        )
        return

    wallet_claim = None
    wallet_claim_error = None
    if not key_to_use:
        wallet_claim, wallet_claim_error = _build_wallet_compensation_claim(token)
        if not wallet_claim:
            output(
                {
                    "error": "No API key is available and wallet claim signing is not ready.",
                    "details": wallet_claim_error,
                    "next": [
                        "blockintql auth --api-key biq_sk_live_...",
                        "or configure wallet mode: blockintql login --auto-pay --max-payment 0.10",
                        f"blockintql compensation claim --token {token}",
                    ],
                },
                agent,
                quiet,
            )
            return

    if not quiet and not agent:
        if key_to_use:
            console.print("[dim]Claiming compensation token as API credits...[/]")
        else:
            console.print("[dim]Claiming compensation token with wallet signature...[/]")
        if captured_at:
            console.print(f"[dim]Using last captured token from {captured_at}[/]")
    claim_body = {"compensation_token": token}
    if key_to_use:
        claim_body["api_key"] = key_to_use
    if wallet_claim:
        claim_body["wallet_claim"] = wallet_claim
    result = api_post(
        "/v1/x402/compensations/claim",
        claim_body,
        require_auth=False,
        timeout=60,
    )
    if "error" in result:
        output(result, agent, quiet)
        return
    if agent or not sys.stdout.isatty():
        output(result, agent, quiet)
        return
    console.print()
    console.print("  [bold cyan]COMPENSATION CLAIM[/bold cyan]")
    console.print(f"  [dim]{'─' * 52}[/dim]")
    console.print(f"  [dim]status   [/dim] {result.get('status')}")
    console.print(f"  [dim]token    [/dim] {result.get('compensation_token') or token}")
    console.print(f"  [dim]credits  [/dim] +{result.get('credits_awarded', 0)}")
    claim_mode = result.get("claim_mode") or ("api_key" if key_to_use else "wallet")
    console.print(f"  [dim]mode     [/dim] {claim_mode}")
    if result.get("reason"):
        console.print(f"  [dim]reason   [/dim] {result.get('reason')}")
    if result.get("claimed_at"):
        console.print(f"  [dim]claimed  [/dim] {result.get('claimed_at')}")
    console.print(f"  [dim]{'─' * 52}[/dim]")
    console.print("  [dim]BlockINTQL · degraded x402 make-good credited to your account[/dim]")

@cli.command()
@click.option("--agent", is_flag=True)
def status(agent):
    """Check authenticated account status."""
    result = api_get("/v1/me")
    error_text = str((result or {}).get("error") or "")
    if "Invalid API key" in error_text:
        result["next"] = [
            "If using wallet mode: unset BLOCKINTQL_API_KEY",
            "Then confirm wallet mode: blockintql wallet status --agent",
            "If using API key mode: blockintql auth --api-key biq_sk_live_...",
        ]
    output(result, agent, False)


@cli.command()
@click.option("--email", "-e", default="", help="Optional email for Stripe receipt only")
@click.option("--pack", default="starter", type=click.Choice(["starter","pro"]),
              help="starter=$10/1000 screens · pro=$40/5000 screens")
@click.option("--agent", is_flag=True)
def buy(email, pack, agent):
    """
    Buy a credit pack and top up your current API key.

    \b
    Examples:
      blockintql buy
      blockintql buy --pack pro
      blockintql buy --pack pro --email you@example.com
    """
    import webbrowser
    if not agent:
        console.print("[dim]Creating checkout...[/]")
    body = {"pack": pack}
    if email:
        body["email"] = email
    api_key = get_api_key()
    if api_key:
        body["api_key"] = api_key
    result = api_post("/v1/billing/checkout", body, require_auth=False)
    if "error" in result and not result.get("free_tier_exhausted"):
        err_console.print(f"  [red]✗[/red] {result['error']}")
        return
    checkout_url = result.get("checkout_url")
    if not checkout_url:
        err_console.print("[red]Could not create checkout session[/]")
        return
    if agent or not sys.stdout.isatty():
        click.echo(json.dumps({
            "checkout_url": checkout_url,
            "pack": pack,
            "email": email or None,
            "api_key_attached": bool(api_key),
            "delivery": "existing_api_key" if api_key else "success_screen_once",
        }, indent=2))
        return
    console.print(f"  [dim]Pack:[/dim]  {'$10 — 1,000 screens' if pack == 'starter' else '$40 — 5,000 screens'}")
    console.print(f"  [dim]Email:[/dim] {email or 'Not provided (receipt only)'}")
    console.print(f"  [dim]Target:[/dim] {'Current API key' if api_key else 'New API key shown once after payment'}")
    console.print(f"  [dim]URL:[/dim]   {checkout_url}")
    console.print()
    try:
        webbrowser.open(checkout_url)
        console.print("[dim]Browser opened. Complete payment to add credits.[/]")
    except:
        console.print("[dim]Copy the URL above to complete payment.[/]")
    if api_key:
        console.print("[dim]After payment run:[/dim] blockintql status")
    else:
        console.print("[dim]After payment:[/] copy the API key shown on the success screen immediately. BlockINTQL cannot restore it later.")
        console.print("[dim]Then run:[/]")
        console.print("[dim]  blockintql auth --api-key biq_sk_live_...[/]")
        console.print("[dim]  blockintql status[/]")


@cli.group()
def workspace():
    """Manage investigation workspaces."""
    _require_experimental(
        "investigation workspaces",
        next_steps=[
            "blockintql chat --interactive",
            "blockintql history <address>",
        ],
    )


@cli.group()
def admin():
    """Operator and audit commands."""
    _require_experimental(
        "admin/operator tools",
        next_steps=[
            "blockintql status --agent",
            "blockintql history <address>",
        ],
    )


@admin.command("vm-audit", hidden=True)
@click.option("--limit", default=25, type=int)
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def admin_vm_audit(limit, agent, quiet):
    """Inspect active Ubicloud VMs, cleanup state, and recent refunds."""
    if not quiet and not agent:
        console.print("[dim]Fetching VM audit view...[/]")
    result = admin_api_get("/v1/admin/audit/vms", params={"limit": limit})
    output(result, agent, quiet)


@workspace.command("create")
@click.argument("name")
@click.option("--chain", default="ethereum", type=click.Choice(["ethereum"]))
@click.option("--modules", default="verdict,stablecoins,bridge-activity,chart")
@click.option("--goal", default="", help="Short investigation brief stored with the workspace.")
@click.option("--seed-address", default="", help="Seed address to focus the workspace on.")
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def workspace_create(name, chain, modules, goal, seed_address, agent, quiet):
    """Create a provisioned investigation workspace."""
    module_list = [item.strip() for item in modules.split(",") if item.strip()]
    payload = {"name": name, "chain": chain, "modules": module_list}
    if goal.strip():
        payload["goal"] = goal.strip()
    if seed_address.strip():
        payload["seed_address"] = seed_address.strip()
    if not quiet and not agent:
        console.print("[dim]Creating workspace...[/]")
    output(api_post("/v1/workspaces/create", payload, require_auth=True), agent, quiet)


@workspace.command("list")
@click.option("--limit", default=10, type=int)
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def workspace_list(limit, agent, quiet):
    """List your recent investigation workspaces."""
    data = api_get("/v1/workspaces", params={"limit": limit}, require_auth=True)
    workspaces = data.get("workspaces") if isinstance(data, dict) else None
    if workspaces:
        ranked = rank_workspaces(workspaces)
        best_id = ranked[0].get("workspace_id") if ranked else None
        marked = []
        for item in ranked:
            enriched = dict(item)
            if best_id and item.get("workspace_id") == best_id:
                enriched["_resume_candidate"] = True
            marked.append(enriched)
        data["workspaces"] = marked
    output(data, agent, quiet)


@workspace.command("status")
@click.argument("workspace_id", required=False)
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def workspace_status(workspace_id, agent, quiet):
    """Get workspace status."""
    workspace_id = _resolve_workspace_id_or_exit(workspace_id, agent=agent, quiet=quiet)
    output(api_get(f"/v1/workspaces/{workspace_id}", require_auth=True), agent, quiet)


@workspace.command("destroy")
@click.argument("workspace_id", required=False)
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def workspace_destroy(workspace_id, agent, quiet):
    """Destroy a workspace."""
    workspace_id = _resolve_workspace_id_or_exit(workspace_id, agent=agent, quiet=quiet)
    if not quiet and not agent:
        console.print("[dim]Destroying workspace...[/]")
    output(api_post(f"/v1/workspaces/{workspace_id}/destroy", {}, require_auth=True), agent, quiet)


@workspace.command("open")
@click.argument("workspace_id", required=False)
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def workspace_open(workspace_id, agent, quiet):
    """Open the workspace explorer if it is ready."""
    import webbrowser

    workspace_id = _resolve_workspace_id_or_exit(workspace_id, agent=agent, quiet=quiet)
    data = api_get(f"/v1/workspaces/{workspace_id}/manifest", require_auth=True)
    workspace = data.get("workspace", data) if isinstance(data, dict) else data
    reason = "Opened directly from the CLI workspace command."
    output(workspace, agent, quiet)
    if agent or quiet or not sys.stdout.isatty():
        return
    url = workspace_launch_url(data)
    if not url:
        console.print("[yellow]Workspace is not ready to open yet.[/]")
        return
    url = _with_query_params(url, {"resume": "1", "resume_reason": reason, "resume_source": "workspace_open"})
    try:
        webbrowser.open(url)
        console.print("[dim]Browser opened to workspace explorer.[/]")
    except Exception:
        console.print(f"[dim]Open this URL manually:[/] {url}")


@workspace.command("resume")
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def workspace_resume(agent, quiet):
    """Open your most recent active workspace."""
    import webbrowser

    data = api_get("/v1/workspaces", params={"limit": 10}, require_auth=True)
    workspaces = data.get("workspaces") if isinstance(data, dict) else None
    if not workspaces:
        output({"error": "No workspaces found for this API key."}, agent, quiet)
        return

    ranked = rank_workspaces(workspaces)
    preferred = ranked[0]
    manifest = api_get(f"/v1/workspaces/{preferred['workspace_id']}/manifest", require_auth=True)
    workspace = manifest.get("workspace", preferred) if isinstance(manifest, dict) else preferred
    reason = describe_resume_reason(preferred)
    output(workspace, agent, quiet)
    if agent or quiet or not sys.stdout.isatty():
        return
    open_result = open_workspace_in_browser(
        preferred["workspace_id"],
        resume_reason=reason,
        resume_source="workspace_resume",
    )
    if open_result == "Workspace is not ready to open yet.":
        console.print("[yellow]Most recent workspace is not ready to open yet.[/]")
        return
    try:
        if open_result is None:
            console.print("[dim]Browser opened to most recent workspace explorer.[/]")
        elif str(open_result).startswith("http"):
            console.print(f"[dim]Open this URL manually:[/] {open_result}")
        else:
            console.print(f"[yellow]{open_result}[/]")
    except Exception:
        console.print(f"[yellow]{open_result}[/]")


@workspace.command("recommended")
@click.option("--address", "-a", default=None)
@click.option("--goal", default="")
@click.option("--limit", default=10, type=int)
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def workspace_recommended(address, goal, limit, agent, quiet):
    """Show the best workspace to resume right now."""
    data = api_get("/v1/workspaces", params={"limit": limit}, require_auth=True)
    workspaces = data.get("workspaces") if isinstance(data, dict) else None
    if not workspaces:
        output({"error": "No workspaces found for this API key."}, agent, quiet)
        return

    candidate = choose_resume_candidate(workspaces, seed_address=address, goal_text=goal)
    if not candidate:
        output({"error": "No workspace recommendation available."}, agent, quiet)
        return

    enriched = dict(candidate)
    enriched["reason"] = describe_resume_reason(candidate, seed_address=address, goal_text=goal)
    output({"workspaces": [dict(recommended_workspace_payload(enriched), _resume_candidate=True)]}, agent, quiet)


@workspace.command("chat")
@click.argument("workspace_id", required=False)
@click.argument("goal", nargs=-1, required=False)
@click.option("--goal", "goal_option", default=None, help="Follow-up question/prompt for this workspace.")
@click.option("--address", "-a", default=None, help="Optional seed override for this follow-up ask.")
@click.option("--chain", "-c", default="ethereum", type=click.Choice(["bitcoin", "ethereum"]))
@click.option("--budget-credits", type=int, default=None)
@click.option("--budget-usd", type=float, default=None)
@click.option("--upto-budget-usd", type=float, default=None)
@click.option("--open-workspace", is_flag=True, help="Open the workspace after planning the follow-up ask.")
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def workspace_chat(workspace_id, goal, goal_option, address, chain, budget_credits, budget_usd, upto_budget_usd, open_workspace, agent, quiet):
    """Continue a workspace with a conversational follow-up ask."""
    workspace_id = _resolve_workspace_id_or_exit(workspace_id, agent=agent, quiet=quiet)
    goal_text = str(goal_option or " ".join(goal or ())).strip()
    if not goal_text:
        raise click.UsageError(
            "Provide a follow-up prompt.\n"
            "Examples:\n"
            "  blockintql workspace chat ws_123 \"What changed since yesterday?\"\n"
            "  blockintql workspace chat ws_123 --goal \"Focus on USDT outflows\""
        )
    if not quiet and not agent:
        console.print("[dim]Continuing workspace conversation...[/]")
    run_ask_flow(
        goal_text,
        address=address,
        workspace_id=workspace_id,
        chain=chain,
        budget_credits=budget_credits,
        budget_usd=budget_usd,
        upto_budget_usd=upto_budget_usd,
        open_workspace=open_workspace,
        agent=agent,
        quiet=quiet,
    )


@workspace.command("next")
@click.argument("workspace_id", required=False)
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def workspace_next(workspace_id, agent, quiet):
    """Show the investigation brief and recommended next actions for a workspace."""
    workspace_id = _resolve_workspace_id_or_exit(workspace_id, agent=agent, quiet=quiet)
    data = api_get(f"/v1/workspaces/{workspace_id}/manifest", require_auth=True)
    if "error" in data:
        output(data, agent, quiet)
        return
    brief = (data.get("context") or {}).get("investigation_brief") or {}
    workspace = data.get("workspace") or {}
    result = {
        "workspace_id": workspace.get("workspace_id") or workspace_id,
        "name": workspace.get("name"),
        "status": workspace.get("status"),
        "investigation_brief": {
            "goal": brief.get("goal") or (data.get("context") or {}).get("seed", {}).get("goal"),
            "seed_address": (data.get("context") or {}).get("seed", {}).get("address"),
            "recommended_actions": [
                action.get("title") or action.get("id")
                for action in (brief.get("recommended_actions") or [])
            ],
        },
    }
    output(result, agent, quiet)


@workspace.command("brief")
@click.argument("workspace_id", required=False)
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def workspace_brief(workspace_id, agent, quiet):
    """Alias for workspace next."""
    workspace_id = _resolve_workspace_id_or_exit(workspace_id, agent=agent, quiet=quiet)
    data = api_get(f"/v1/workspaces/{workspace_id}/manifest", require_auth=True)
    if "error" in data:
        output(data, agent, quiet)
        return
    brief = (data.get("context") or {}).get("investigation_brief") or {}
    workspace = data.get("workspace") or {}
    result = {
        "workspace_id": workspace.get("workspace_id") or workspace_id,
        "name": workspace.get("name"),
        "status": workspace.get("status"),
        "investigation_brief": {
            "goal": brief.get("goal") or (data.get("context") or {}).get("seed", {}).get("goal"),
            "seed_address": (data.get("context") or {}).get("seed", {}).get("address"),
            "recommended_actions": [
                action.get("title") or action.get("id")
                for action in (brief.get("recommended_actions") or [])
            ],
        },
    }
    output(result, agent, quiet)


@workspace.command("manifest")
@click.argument("workspace_id", required=False)
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def workspace_manifest(workspace_id, agent, quiet):
    """Fetch the full workspace manifest used by the provisioned explorer."""
    workspace_id = _resolve_workspace_id_or_exit(workspace_id, agent=agent, quiet=quiet)
    output(api_get(f"/v1/workspaces/{workspace_id}/manifest", require_auth=True), agent, quiet)


def main():
    cli()

if __name__ == "__main__":
    main()


@cli.command()
@click.argument("name")
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def ens(name, agent, quiet):
    """Resolve an ENS name to an Ethereum address.

    \b
    Examples:
      blockintql ens vitalik.eth
      blockintql ens blockint.eth
    """
    _require_experimental(
        "ENS resolution",
        next_steps=[
            "blockintql history <address>",
            "blockintql screen <address>",
        ],
    )
    if not quiet and not agent:
        console.print(f"[dim]Resolving {name}...[/]")
    result = api_get(f"/v1/eth/ens/{name}")
    output(result, agent, quiet)
