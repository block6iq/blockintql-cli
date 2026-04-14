#!/usr/bin/env python3
"""
BlockINTQL CLI

PRIVACY ARCHITECTURE:
  BlockINTQL API receives: address + chain ONLY
  Provider API receives: address + your key (direct from your machine)
  BlockINTQL NEVER sees: your provider key or raw provider response

Verify this by reading the source. Open source: github.com/block6iq/blockintql-cli
"""

import sys, os, json
from pathlib import Path
from urllib.parse import urlencode, urlparse, parse_qsl, urlunparse
import click
import httpx
from rich.console import Console
from rich.table import Table
from rich import box
from . import __version__
from .providers import get_provider, list_providers

# ── BANNER ────────────────────────────────────────────────────────────────────
BLOCKINTQL_BANNER = """
[bold white]██████╗ ██╗      ██████╗  ██████╗██╗  ██╗██╗███╗   ██╗████████╗ ██████╗ ██╗     [/bold white]
[bold white]██╔══██╗██║     ██╔═══██╗██╔════╝██║ ██╔╝██║████╗  ██║╚══██╔══╝██╔═══██╗██║     [/bold white]
[bold white]██████╔╝██║     ██║   ██║██║     █████╔╝ ██║██╔██╗ ██║   ██║   ██║   ██║██║     [/bold white]
[bold white]██╔══██╗██║     ██║   ██║██║     ██╔═██╗ ██║██║╚██╗██║   ██║   ██║▄▄ ██║██║     [/bold white]
[bold white]██████╔╝███████╗╚██████╔╝╚██████╗██║  ██╗██║██║ ╚████║   ██║   ╚██████╔╝███████╗[/bold white]
[bold white]╚═════╝ ╚══════╝ ╚═════╝  ╚═════╝╚═╝  ╚═╝╚═╝╚═╝  ╚═══╝   ╚═╝    ╚══▀▀═╝ ╚══════╝[/bold white]
[dim]  Sovereign Blockchain Intelligence · by Block6IQ · block6iq.com[/dim]
"""

API_BASE = os.environ.get("BLOCKINTQL_API_URL", "https://blockintql.com")
CONFIG_FILE = os.path.expanduser("~/.blockintql/config.json")
console = Console()
err_console = Console(stderr=True)

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

def get_headers():
    key = get_api_key()
    if not key:
        err_console.print("[red]No API key.[/] Run: blockintql auth --api-key YOUR_KEY")
        sys.exit(1)
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

def api_get(path, params=None, require_auth=True):
    """Query BlockINTQL API — sends address+chain ONLY, never provider keys."""
    try:
        headers = get_headers() if require_auth else {"Content-Type": "application/json"}
        r = httpx.get(f"{API_BASE}{path}", headers=headers, params=params, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}

def api_post(path, body, require_auth=True):
    """Query BlockINTQL API — sends address+chain ONLY, never provider keys."""
    try:
        headers = get_headers() if require_auth else {"Content-Type": "application/json"}
        r = httpx.post(f"{API_BASE}{path}", headers=headers, json=body, timeout=60)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}


def api_put(path, body, require_auth=True):
    """Update BlockINTQL API resources with authenticated JSON payloads."""
    try:
        headers = get_headers() if require_auth else {"Content-Type": "application/json"}
        r = httpx.put(f"{API_BASE}{path}", headers=headers, json=body, timeout=60)
        r.raise_for_status()
        return r.json()
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
                 upto_budget_usd=None, open_workspace=False, agent=False, quiet=False):
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
    url = _with_query_params(
        url,
        {
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

    # Merge — take higher risk score
    result["risk_score"] = max(pd.get("risk_score", 0), result.get("risk_score", 0))
    if pd.get("entity_name") and not result.get("entity"):
        result["entity"] = pd["entity_name"]
    if pd.get("sanctions_hit"):
        result["verdict"] = "BLOCK"
        result["safe"] = False
        result.setdefault("risk_indicators", []).append("SANCTIONS")
    # Store provider summary (not raw response) for display
    result["provider_data"] = {
        "provider": provider_name,
        "entity_name": pd.get("entity_name"),
        "entity_category": pd.get("entity_category"),
        "risk_score": pd.get("risk_score", 0),
        "risk_indicators": pd.get("risk_indicators", []),
        "sanctions_hit": pd.get("sanctions_hit", False),
    }
    return result

def verdict_color(v):
    return {"CLEAR": "green", "CAUTION": "yellow", "BLOCK": "red"}.get(str(v).upper(), "white")


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
                console.print(f"  [dim]risk    [/dim] {pd.get('risk_score',0)}/100")
                if pd.get("sanctions_hit"):
                    console.print(f"  [red]  ⚠  SANCTIONS HIT[/red]")
            if data.get("narrative"):
                console.print(f"  [dim]{'─' * 52}[/dim]")
                console.print(f"  [dim]{data['narrative'][:300]}[/dim]")

        console.print(f"  [dim]{'─' * 52}[/dim]")
        console.print(f"  [dim]BlockINTQL · block6iq.com[/dim]")
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
        console.print(f"  [dim]BlockINTQL · OP_RETURN identity graph · block6iq.com[/dim]")
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
        console.print(f"  [dim]BlockINTQL · block6iq.com[/dim]")
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
        guardrails = data.get("cost_guardrails") or {}
        if guardrails.get("message"):
            console.print(f"  [dim]guardrail[/dim] {guardrails.get('message')}")
        if data.get("execution_error"):
            err = data["execution_error"]
            console.print(f"  [red]error    [/red] {err.get('detail', err)}")
        if data.get("ask_history_warning"):
            console.print(f"  [yellow]history  [/yellow] {data.get('ask_history_warning')}")
        console.print(f"  [dim]{'─' * 52}[/dim]")
        console.print(f"  [dim]BlockINTQL · block6iq.com[/dim]")
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
        console.print(f"  [dim]BlockINTQL · block6iq.com[/dim]")
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
@click.option("--chain", "-c", default="bitcoin", type=click.Choice(["bitcoin","ethereum"]))
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
@click.option("--chain", "-c", default="bitcoin", type=click.Choice(["bitcoin","ethereum"]))
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
@click.argument("query", required=False)
@click.option("--address", "-a", multiple=True)
@click.option("--chain", "-c", default="ethereum", type=click.Choice(["bitcoin","ethereum","both"]))
@click.option("--format", "fmt", default="full", type=click.Choice(["full","graph","narrative"]))
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def analyze(query, address, chain, fmt, agent, quiet):
    """Run autonomous multi-agent analysis."""
    if not query and not address:
        raise click.UsageError("Provide a QUERY or --address")
    if not quiet and not agent:
        console.print("[dim]Running autonomous analysis...[/]")
    result = api_post("/v1/analyze", {"query": query or "", "addresses": list(address),
                                       "chain": chain, "output_format": fmt})
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
@click.argument("query")
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def query(query, agent, quiet):
    """Natural language blockchain intelligence."""
    if not quiet and not agent: console.print("[dim]Processing...[/]")
    result = api_post("/v1/intelligence/search", {"query": query})
    output(result, agent, quiet)

@cli.command()
@click.argument("goal")
@click.option("--address", "-a", default=None)
@click.option("--workspace-id", default=None, help="Continue an existing workspace instead of starting fresh.")
@click.option("--chain", "-c", default="ethereum", type=click.Choice(["bitcoin","ethereum"]))
@click.option("--budget-credits", type=int, default=None)
@click.option("--budget-usd", type=float, default=None)
@click.option("--upto-budget-usd", type=float, default=None)
@click.option("--open-workspace", is_flag=True, help="Prefer workspace execution and open a workspace when possible.")
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def ask(goal, address, workspace_id, chain, budget_credits, budget_usd, upto_budget_usd, open_workspace, agent, quiet):
    """Plan an investigation and optionally open a workspace."""
    if not quiet and not agent:
        console.print("[dim]Planning investigation...[/]")
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
            "commands": ["verdict","screen","analyze","profile","trace","query","ask","providers","status"],
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
        ("analyze","Multi-agent analysis",'blockintql analyze "check for sanctions"'),
        ("profile","OP_RETURN identity","blockintql profile --identifier @handle"),
        ("trace","FIFO/LIFO tracing","blockintql trace --txid abc123..."),
        ("query","Natural language",'blockintql query "is this safe?"'),
        ("ask","Plan or open workspace",'blockintql ask "Investigate this wallet" --address 0x123...'),
        ("providers","List providers","blockintql providers"),
        ("skills","Agent skills","blockintql skills --install >> CONTEXT.md"),
    ]
    for r in rows: t.add_row(*r)
    console.print(t)
    console.print("\n[dim]Provider keys stay on your machine. BlockINTQL only sees the address.[/]")
    console.print("[dim]Source: github.com/block6iq/blockintql-cli[/]")

@cli.command()
@click.option("--wallet-type", default="cdp", type=click.Choice(["cdp","privatekey"]))
@click.option("--cdp-key-id", default=None, envvar="BLOCKINTQL_CDP_KEY_ID")
@click.option("--cdp-private-key", default=None, envvar="BLOCKINTQL_CDP_PRIVATE_KEY")
@click.option("--private-key", default=None, envvar="BLOCKINTQL_PRIVATE_KEY")
@click.option("--auto-pay", is_flag=True)
@click.option("--max-payment", default=0.10)
def pay(wallet_type, cdp_key_id, cdp_private_key, private_key, auto_pay, max_payment):
    """Store local payment preferences for wallet-based billing flows."""
    config = load_config()
    payment_config = {"type": wallet_type, "auto_pay": auto_pay, "max_payment_usd": max_payment}
    if wallet_type == "cdp":
        payment_config["cdp_key_id"] = cdp_key_id or os.environ.get("BLOCKINTQL_CDP_KEY_ID")
    elif wallet_type == "privatekey":
        payment_config["private_key_env"] = "BLOCKINTQL_PRIVATE_KEY"
    config["payment"] = payment_config
    save_config(config)
    console.print(f"[green]Saved local payment preferences ({wallet_type}).[/]")
    console.print(f"[green]Auto-pay preference: {'enabled' if auto_pay else 'disabled'} | Max: ${max_payment}[/]")
    console.print("[dim]Sensitive wallet keys are not persisted by this command. Keep them in environment variables.[/]")

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
