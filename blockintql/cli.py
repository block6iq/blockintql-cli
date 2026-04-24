#!/usr/bin/env python3
"""
BlockINTQL CLI

PRIVACY ARCHITECTURE:
  BlockINTQL API receives: address + chain ONLY
  Provider API receives: address + your key (direct from your machine)
  BlockINTQL NEVER sees: your provider key or raw provider response

Verify this by reading the source. Open source: github.com/block6iq/blockintql-cli
"""

import sys, os, json, base64
from pathlib import Path
from urllib.parse import urlencode, urlparse, parse_qsl, urlunparse
import click
import httpx
from rich.console import Console
from rich.table import Table
from rich import box
from . import __version__
from .payments import (
    PaymentError,
    enforce_payment_policy,
    ensure_wallet_runtime_ready,
    load_payment_config,
)
from .providers import adjudicate_provider_result, get_provider, list_providers
from .x402_runtime import request_with_x402

# ── BANNER ────────────────────────────────────────────────────────────────────
BLOCKINTQL_BANNER = """
[bold white]██████╗ ██╗      ██████╗  ██████╗██╗  ██╗██╗███╗   ██╗████████╗ ██████╗ ██╗     [/bold white]
[bold white]██╔══██╗██║     ██╔═══██╗██╔════╝██║ ██╔╝██║████╗  ██║╚══██╔══╝██╔═══██╗██║     [/bold white]
[bold white]██████╔╝██║     ██║   ██║██║     █████╔╝ ██║██╔██╗ ██║   ██║   ██║   ██║██║     [/bold white]
[bold white]██╔══██╗██║     ██║   ██║██║     ██╔═██╗ ██║██║╚██╗██║   ██║   ██║▄▄ ██║██║     [/bold white]
[bold white]██████╔╝███████╗╚██████╔╝╚██████╗██║  ██╗██║██║ ╚████║   ██║   ╚██████╔╝███████╗[/bold white]
[bold white]╚═════╝ ╚══════╝ ╚═════╝  ╚═════╝╚═╝  ╚═╝╚═╝╚═╝  ╚═══╝   ╚═╝    ╚══▀▀═╝ ╚══════╝[/bold white]
[dim]  Sovereign Blockchain Intelligence · blockintql.com[/dim]
"""

DEFAULT_API_BASE = "https://blockintql.com"
DIRECT_API_BASE = "https://btc-index-api-385334043904.us-central1.run.app"
API_BASE = os.environ.get("BLOCKINTQL_API_URL", DEFAULT_API_BASE)
CONFIG_FILE = os.path.expanduser("~/.blockintql/config.json")
PAYMENT_RESPONSE_HEADER_CANDIDATES = ("PAYMENT-RESPONSE", "payment-response")
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

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f: return json.load(f)
    return {}

def save_config(config):
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)
    Path(CONFIG_FILE).chmod(0o600)

def get_api_key():
    return os.environ.get("BLOCKINTQL_API_KEY") or load_config().get("api_key")


def get_admin_key():
    return os.environ.get("BLOCKINTQL_ADMIN_KEY") or load_config().get("admin_api_key")


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
    return int(getattr(response, "status_code", 0) or 0) in {502, 503, 504, 520, 522, 524}


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
        raise PaymentError(
            "The x402-paid request did not complete successfully.",
            details=payment_details,
        )
    payment_metadata = dict(payment_details)
    payment_metadata.update(_build_payment_metadata(payment_config, result.get("receipt")))
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

    result = api_post("/v1/plan", body, require_auth=bool(open_workspace or workspace_id))

    if workspace_id and "error" not in result:
        workspace = api_get(f"/v1/workspaces/{workspace_id}", require_auth=True)
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
            existing = api_get("/v1/workspaces", params={"limit": 10}, require_auth=True)
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

def enrich_with_provider(result, address, chain, provider_name, provider_key, provider_url):
    """
    PRIVACY: Runs entirely on your local machine.
    Calls provider API directly — key never sent to BlockINTQL.
    Only the merged verdict (no raw provider data) is shown to user.
    """
    if not provider_name:
        return result
    provider = get_provider(provider_name, provider_key or "", url_template=provider_url)
    if not provider:
        err_console.print(f"[yellow]Unknown provider: {provider_name}[/]")
        return result
    if provider.requires_api_key and not provider_key:
        err_console.print(f"[yellow]{provider_name} requires --provider-key or BLOCKINTQL_PROVIDER_KEY[/]")
        return result

    # PRIVACY: This call goes directly to provider API from your machine
    pd = provider.get_address_risk(address, chain)

    if "error" in pd.get("raw", {}):
        return result

    provider_policy = adjudicate_provider_result(pd)

    # Merge — take higher risk score
    result["risk_score"] = max(pd.get("risk_score", 0), result.get("risk_score", 0))
    if pd.get("entity_name") and not result.get("entity"):
        result["entity"] = pd["entity_name"]
    provider_recommended_verdict = provider_policy.get("recommended_verdict")
    canonical_category = provider_policy.get("canonical_category")
    if pd.get("sanctions_hit") or provider_recommended_verdict == "BLOCK":
        result["verdict"] = "BLOCK"
        result["safe"] = False
        if canonical_category:
            result.setdefault("risk_indicators", []).append(f"PROVIDER_{canonical_category.upper()}")
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
    if provider_recommended_verdict == "BLOCK":
        result["action"] = "block"

    # Store an allowlisted summary only. Raw provider responses stay local.
    result["provider_data"] = {
        "provider": provider_name,
        "entity_name": pd.get("entity_name"),
        "entity_category": pd.get("entity_category"),
        "risk_score": pd.get("risk_score", 0),
        "risk_indicators": pd.get("risk_indicators", []),
        "sanctions_hit": pd.get("sanctions_hit", False),
        "canonical_category": canonical_category,
        "recommended_verdict": provider_recommended_verdict,
        "severity": provider_policy.get("severity"),
        "confidence": provider_policy.get("confidence"),
        "reasons": provider_policy.get("reasons", []),
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
            console.print("[dim]Try a wider window like `--hours 72` or `--hours 168`, or focus a token with `--token USDC` / `--token USDT`.[/]")
        return

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


def choose_resume_candidate(workspaces, seed_address=None, goal_text=""):
    ranked = rank_workspaces(workspaces)
    if not ranked:
        return None
    normalized_goal = (goal_text or "").strip().lower()
    for item in ranked:
        context = item.get("workspace_context") or {}
        existing_seed = (context.get("seed_address") or "").strip().lower()
        existing_goal = (context.get("goal") or "").strip().lower()
        if seed_address and existing_seed == seed_address.strip().lower():
            return item
        if normalized_goal and existing_goal and normalized_goal in existing_goal:
            return item
    return ranked[0]


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
    if address:
        cmd = cmd.replace("<address>", address)
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
    commands = []
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
            commands.append(command)
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
        workspace_actions = [
            "Run Expansion",
            "Sync Artifacts",
            "Hydrate Graph",
        ]

    return commands, workspace_actions


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
        console.print(f"  [dim]{'─' * 52}[/dim]")
        console.print("  [dim]BlockINTQL · compliance + blockchain forensics only[/dim]")
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
                if pd.get("entity_name"):
                    console.print(f"  [dim]entity  [/dim] {pd['entity_name']}")
                if pd.get("canonical_category"):
                    console.print(f"  [dim]class   [/dim] {pd.get('canonical_category')}")
                console.print(f"  [dim]risk    [/dim] {pd.get('risk_score',0)}/100")
                if pd.get("recommended_verdict"):
                    console.print(f"  [dim]policy  [/dim] {pd.get('recommended_verdict')} · {pd.get('confidence','unknown')} confidence")
                if pd.get("sanctions_hit"):
                    console.print(f"  [red]  ⚠  SANCTIONS HIT[/red]")
                elif pd.get("reasons"):
                    console.print(f"  [dim]why     [/dim] {pd.get('reasons')[0]}")
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
        continue_commands, workspace_actions = continue_plan_instructions(data)
        if continue_commands or workspace_actions:
            selected_label = (selected_profile.get("label") or "").strip()
            heading = "continue with selected mode" if selected_label else "continue with this plan"
            console.print(f"  [dim]{heading}[/dim]")
            for command in continue_commands[:4]:
                console.print(f"    [cyan]$[/cyan] {command}")
            if workspace_actions:
                console.print("    [dim]Then in the workspace:[/dim]")
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
                 type=click.Choice(["chainalysis","trm","elliptic","arkham","metamask","generic"]),
                 help="Attribution provider (key stays on your machine)"),
    click.option("--provider-key", default=None, envvar="BLOCKINTQL_PROVIDER_KEY",
                 help="Provider API key — never sent to BlockINTQL"),
    click.option("--provider-url", default=None,
                 help="Custom provider URL template with {address} placeholder"),
]

def with_provider(f):
    for opt in reversed(provider_opts): f = opt(f)
    return f

@click.group(invoke_without_command=True)
@click.version_option(__version__, prog_name="blockintql")
@click.pass_context
def cli(ctx):
    """BlockINTQL — Sovereign Blockchain Intelligence CLI

    Your provider key never leaves your machine.
    BlockINTQL only receives the address being screened.
    """
    if ctx.invoked_subcommand is None:
        console.print(BLOCKINTQL_BANNER)
        click.echo(ctx.get_help())
        console.print()
        console.print("[dim]Wallet-based access:[/] [bold]blockintql login --auto-pay --max-payment 0.10[/]")

@cli.command()
@click.option("--api-key", required=True)
@click.option("--provider", default=None)
def auth(api_key, provider):
    """Save API key and optional default provider name."""
    config = load_config()
    config["api_key"] = api_key
    if provider:
        config["default_provider"] = provider
    save_config(config)
    console.print("[green]Saved API configuration.[/]")
    console.print("[dim]Keep provider keys in environment variables instead of config files.[/]")

@cli.command()
@click.option("--address", "-a", required=True)
@click.option("--chain", "-c", default="auto", type=click.Choice(["auto","bitcoin","ethereum"]))
@click.option("--context", default="")
@with_provider
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def verdict(address, chain, context, provider, provider_key, provider_url, agent, quiet):
    """Get a CLEAR/CAUTION/BLOCK verdict.

    \b
    Privacy: BlockINTQL receives address+chain only.
    Provider key stays on your machine.

    \b
    Examples:
      blockintql verdict --address 1A1zP1e...
      blockintql verdict --address 0x123... --provider chainalysis --provider-key $KEY
    """
    chain = infer_chain_from_value(address, fallback="bitcoin") if chain == "auto" else chain
    config = load_config()
    provider = provider or config.get("default_provider")
    if not quiet and not agent:
        p_info = f" + {provider} (local)" if provider else ""
        console.print(f"[dim]Screening {address[:20]}...{p_info}[/]")

    # STEP 1: BlockINTQL gets address+chain ONLY
    result = api_post("/v1/verdict", {"address": address, "chain": chain, "context": context})

    # STEP 2: Provider called directly from YOUR machine — key never sent to BlockINTQL
    if provider and "error" not in result:
        result = enrich_with_provider(result, address, chain, provider, provider_key, provider_url)

    output(result, agent, quiet)

@cli.command()
@click.option("--address", "-a", required=True)
@click.option("--chain", "-c", default="auto", type=click.Choice(["auto","bitcoin","ethereum"]))
@with_provider
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def screen(address, chain, provider, provider_key, provider_url, agent, quiet):
    """Screen a counterparty before transacting.

    \b
    Privacy: Your provider key never touches BlockINTQL servers.
    Provider is called directly from your machine.

    \b
    Examples:
      blockintql screen --address 1A1zP1e...
      blockintql screen --address 0x123... --provider trm --provider-key $KEY
    """
    chain = infer_chain_from_value(address, fallback="bitcoin") if chain == "auto" else chain
    config = load_config()
    provider = provider or config.get("default_provider")
    if not quiet and not agent:
        p_info = f" + {provider} (local)" if provider else ""
        console.print(f"[dim]Screening {address[:20]}...{p_info}[/]")

    # STEP 1: BlockINTQL gets address+chain ONLY
    result = api_post("/v1/screen", {"address": address, "chain": chain})

    # STEP 2: Provider called directly from YOUR machine — key never sent to BlockINTQL
    if provider and "error" not in result:
        result = enrich_with_provider(result, address, chain, provider, provider_key, provider_url)

    output(result, agent, quiet)


@cli.command()
@click.argument("address_arg", required=False)
@click.option("--address", "-a", required=False)
@click.option("--chain", "-c", default="ethereum", type=click.Choice(["ethereum"]))
@click.option("--limit", default=25, show_default=True, type=int)
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def history(address_arg, address, chain, limit, agent, quiet):
    """Fetch unified Ethereum wallet history (native + token transfers)."""
    address = coalesce_address(address_arg, address)
    if not address:
        raise click.UsageError("Provide an address as an argument or with --address")
    if not quiet and not agent:
        console.print(f"[dim]Loading {chain} history for {address[:20]}...[/]")
    result = api_get(f"/v1/eth/address/{address}/history", {"limit": limit})
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
    render_stablecoin_flow_chart(result, hours=hours, interval=interval, token=token)


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
    result = api_get(f"/v1/eth/address/{address}/stablecoin-history", params)
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
@click.option("--limit", default=25, show_default=True, type=int)
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def eth_history(address, limit, agent, quiet):
    """Fetch unified Ethereum wallet history."""
    result = api_get(f"/v1/eth/address/{address}/history", {"limit": limit})
    output(result, agent, quiet)


@eth.command("tx")
@click.argument("txid")
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def eth_tx(txid, agent, quiet):
    """Fetch verbose Ethereum transaction details."""
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
    if not quiet and not agent:
        console.print(f"[dim]Searching identity graph...[/]")
    result = api_get("/v1/profile/search", {"identifier": identifier, "type": id_type})
    output(result, agent, quiet)

@cli.command()
@click.option("--txid", "-t", required=True)
@click.option("--hops", default=5)
@click.option("--method", default="fifo", type=click.Choice(["fifo","lifo"]))
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def trace(txid, hops, method, agent, quiet):
    """Trace funds with FIFO/LIFO accounting."""
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
    query_text = " ".join(query).strip()
    if not quiet and not agent: console.print("[dim]Processing...[/]")
    result = api_post("/v1/intelligence/search", {"query": query_text})
    output(result, agent, quiet)


@cli.command()
@click.argument("message", nargs=-1, required=True)
@click.option("--session-id", default=None, help="Continue an existing BlockINTQL chat session.")
@click.option("--address", "-a", default=None, help="Optional address to anchor the chat turn.")
@click.option("--chain", "-c", default="ethereum", type=click.Choice(["bitcoin", "ethereum"]))
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def chat(message, session_id, address, chain, agent, quiet):
    """Scoped multi-turn compliance and blockchain forensics chat."""
    message_text = " ".join(message).strip()
    if not quiet and not agent:
        console.print("[dim]Chatting with BlockINTQL...[/]")
    payload = {"message": message_text, "chain": chain}
    if session_id:
        payload["session_id"] = session_id
    if address:
        payload["address"] = address
    result = api_post("/v1/chat", payload, require_auth=True, timeout=120)
    output(result, agent, quiet)

@cli.command()
@click.argument("goal", nargs=-1, required=True)
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
    goal_text = " ".join(goal).strip()
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


@cli.group()
def prediction():
    """Prediction-market investigation commands."""


@prediction.group()
def market():
    """Prediction-market workflows for Ethereum investigations."""


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
def prediction_market_analysis(address_arg, address, workspace_id, chain, budget_credits, budget_usd, upto_budget_usd, execution_mode, open_workspace, agent, quiet):
    """Plan or open a prediction-market investigation workflow."""
    address = coalesce_address(address_arg, address)
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
        t.add_row(p["name"], p["description"], "No" if p["name"] in ("metamask","generic") else "Yes")
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
            "commands": ["verdict","screen","history","tx","eth","stablecoins","chart","prediction","analyze","profile","trace","query","chat","ask","workspace","wallet","capabilities","providers","status","admin"],
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
        ("tx","Verbose Ethereum tx","blockintql tx --txid 0xabc..."),
        ("eth","Ethereum-first namespace","blockintql eth stablecoins history 0x123..."),
        ("stablecoins","Ethereum stablecoin analytics","blockintql stablecoins history --address 0x123..."),
        ("chart","Terminal-native charts","blockintql chart wallet-stablecoin-balances 0x123..."),
        ("prediction","Prediction-market workflow","blockintql prediction market analysis 0x123..."),
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


def _configure_cdp_wallet(auto_pay, max_payment, cdp_key_id, agent, *, command_name="wallet connect"):
    if cdp_key_id:
        os.environ["BLOCKINTQL_CDP_KEY_ID"] = cdp_key_id

    configured_key_id = cdp_key_id or os.environ.get("BLOCKINTQL_CDP_KEY_ID")
    configured_private_key = os.environ.get("BLOCKINTQL_CDP_PRIVATE_KEY")
    if not configured_key_id or not configured_private_key:
        message = {
            "error": "No wallet session credentials found for CDP mode.",
            "next_step": "Set BLOCKINTQL_CDP_KEY_ID and BLOCKINTQL_CDP_PRIVATE_KEY, then rerun login.",
            "example": "export BLOCKINTQL_CDP_KEY_ID='...'; export BLOCKINTQL_CDP_PRIVATE_KEY='-----BEGIN ...'",
        }
        if agent or not sys.stdout.isatty():
            click.echo(json.dumps(message, indent=2))
        else:
            err_console.print("[red]No wallet session credentials found for CDP mode.[/]")
            console.print("[dim]Next step:[/] export BLOCKINTQL_CDP_KEY_ID='...'")
            console.print("[dim]            export BLOCKINTQL_CDP_PRIVATE_KEY='-----BEGIN ...'")
            console.print(f"[dim]Then run:[/] blockintql {command_name} --auto-pay --max-payment 0.10")
        return False

    config = load_config()
    payment_config = {
        "type": "cdp",
        "auto_pay": auto_pay,
        "max_payment_usd": max_payment,
        "cdp_key_id": configured_key_id,
        "private_key_env": "BLOCKINTQL_CDP_PRIVATE_KEY",
    }
    config["payment"] = payment_config
    save_config(config)

    result = {
        "wallet_type": "cdp",
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
    console.print("[green]Wallet connected for x402 access (cdp).[/]")
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

    env_names = [payment_config.private_key_env]
    if payment_config.wallet_type == "cdp":
        env_names = ["BLOCKINTQL_CDP_PRIVATE_KEY"]
    ready = any(os.environ.get(name) for name in env_names) and bool(
        payment_config.cdp_key_id or os.environ.get("BLOCKINTQL_CDP_KEY_ID")
    )
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

@cli.command()
@click.option("--agent", is_flag=True)
def status(agent):
    """Check authenticated account status."""
    output(api_get("/v1/me"), agent, False)


@cli.command()
@click.option("--email", "-e", default="", help="Optional email for Stripe receipt / fallback delivery")
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
        click.echo(json.dumps({"checkout_url": checkout_url, "pack": pack, "email": email or None, "api_key_attached": bool(api_key)}, indent=2))
        return
    console.print(f"  [dim]Pack:[/dim]  {'$10 — 1,000 screens' if pack == 'starter' else '$40 — 5,000 screens'}")
    console.print(f"  [dim]Email:[/dim] {email or 'Not provided'}")
    console.print(f"  [dim]Target:[/dim] {'Current API key' if api_key else 'No API key attached'}")
    console.print(f"  [dim]URL:[/dim]   {checkout_url}")
    console.print()
    try:
        webbrowser.open(checkout_url)
        console.print("[dim]Browser opened. Complete payment to add credits.[/]")
    except:
        console.print("[dim]Copy the URL above to complete payment.[/]")
    console.print("[dim]After payment run:[/dim] blockintql status")


@cli.group()
def workspace():
    """Manage investigation workspaces."""


@cli.group()
def admin():
    """Operator and audit commands."""


@admin.command("vm-audit")
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
@click.argument("workspace_id")
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def workspace_status(workspace_id, agent, quiet):
    """Get workspace status."""
    output(api_get(f"/v1/workspaces/{workspace_id}", require_auth=True), agent, quiet)


@workspace.command("destroy")
@click.argument("workspace_id")
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def workspace_destroy(workspace_id, agent, quiet):
    """Destroy a workspace."""
    if not quiet and not agent:
        console.print("[dim]Destroying workspace...[/]")
    output(api_post(f"/v1/workspaces/{workspace_id}/destroy", {}, require_auth=True), agent, quiet)


@workspace.command("open")
@click.argument("workspace_id")
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def workspace_open(workspace_id, agent, quiet):
    """Open the workspace explorer if it is ready."""
    import webbrowser

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
@click.argument("workspace_id")
@click.argument("goal")
@click.option("--address", "-a", default=None, help="Optional seed override for this follow-up ask.")
@click.option("--chain", "-c", default="ethereum", type=click.Choice(["bitcoin", "ethereum"]))
@click.option("--budget-credits", type=int, default=None)
@click.option("--budget-usd", type=float, default=None)
@click.option("--upto-budget-usd", type=float, default=None)
@click.option("--open-workspace", is_flag=True, help="Open the workspace after planning the follow-up ask.")
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def workspace_chat(workspace_id, goal, address, chain, budget_credits, budget_usd, upto_budget_usd, open_workspace, agent, quiet):
    """Continue a workspace with a conversational follow-up ask."""
    if not quiet and not agent:
        console.print("[dim]Continuing workspace conversation...[/]")
    run_ask_flow(
        goal,
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
@click.argument("workspace_id")
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def workspace_next(workspace_id, agent, quiet):
    """Show the investigation brief and recommended next actions for a workspace."""
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
@click.argument("workspace_id")
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def workspace_brief(workspace_id, agent, quiet):
    """Alias for workspace next."""
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
@click.argument("workspace_id")
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def workspace_manifest(workspace_id, agent, quiet):
    """Fetch the full workspace manifest used by the provisioned explorer."""
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
    if not quiet and not agent:
        console.print(f"[dim]Resolving {name}...[/]")
    result = api_get(f"/v1/eth/ens/{name}")
    output(result, agent, quiet)
