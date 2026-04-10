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
import click
import httpx
from rich.console import Console
from rich.table import Table
from rich import box
from . import __version__
from .providers import get_provider, list_providers

BLOCKINTQL_BANNER = """
[bold green]██████╗ ██╗      ██████╗  ██████╗██╗  ██╗██╗███╗   ██╗████████╗ ██████╗ ██╗     [/bold green]
[bold green]██╔══██╗██║     ██╔═══██╗██╔════╝██║ ██╔╝██║████╗  ██║╚══██╔══╝██╔═══██╗██║     [/bold green]
[bold green]██████╔╝██║     ██║   ██║██║     █████╔╝ ██║██╔██╗ ██║   ██║   ██║   ██║██║     [/bold green]
[bold green]██╔══██╗██║     ██║   ██║██║     ██╔═██╗ ██║██║╚██╗██║   ██║   ██║▄▄ ██║██║     [/bold green]
[bold green]██████╔╝███████╗╚██████╔╝╚██████╗██║  ██╗██║██║ ╚████║   ██║   ╚██████╔╝███████╗[/bold green]
[bold green]╚═════╝ ╚══════╝ ╚═════╝  ╚═════╝╚═╝  ╚═╝╚═╝╚═╝  ╚═══╝   ╚═╝    ╚══▀▀═╝ ╚══════╝[/bold green]
[dim]  BlockINTQL · by Block6IQ · block6iq.com[/dim]
"""

API_BASE = os.environ.get("BLOCKINTQL_API_URL", "https://btc-index-api-385334043904.us-central1.run.app")
CONFIG_FILE = os.path.expanduser("~/.blockintql/config.json")
console = Console()
err_console = Console(stderr=True)


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            return json.load(f)
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
        err_console.print("[red]No API key.[/] Run: blockintql auth  or set BLOCKINTQL_API_KEY env var")
        sys.exit(1)
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def get_optional_headers():
    key = get_api_key()
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


def api_get(path, params=None, require_auth=True):
    try:
        headers = get_headers() if require_auth else get_optional_headers()
        r = httpx.get(f"{API_BASE}{path}", headers=headers, params=params, timeout=30)
        data = r.json() if r.text else {}
        if r.status_code >= 400:
            return format_api_error(r, data)
        return data
    except Exception as e:
        return {"error": str(e)}


def fetch_credits():
    """Fetch current credit balance."""
    try:
        key = get_api_key()
        if not key:
            return None
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        r = httpx.get(f"{API_BASE}/v1/me", headers=headers, timeout=5)
        if r.status_code == 200:
            return r.json().get("credits", 0)
    except:
        pass
    return None

CREDIT_COSTS = {
    "verdict": 2, "screen": 2, "profile": 2, "trace": 2, "ens": 2,
    "graphs": 5, "analyze": 10, "query": 10, "flows": 10,
    "investigations": 20, "signals": 5, "exposure": 5, "opreturn-search": 5, "opreturn-stats": 2,
}

def show_credit_cost(command_name):
    """Show credit cost before a command runs."""
    cost = CREDIT_COSTS.get(command_name, 1)
    credits = fetch_credits()
    if credits is not None:
        console.print(f"  [dim]cost: {cost} credit{'s' if cost != 1 else ''} · balance: {credits:,} credits[/dim]")
        if credits < cost:
            console.print(f"  [dim]credits may be low — proceeding anyway[/dim]")
    return True

def show_credit_after(command_name):
    """Show remaining balance after a command."""
    credits = fetch_credits()
    if credits is not None:
        console.print(f"  [dim]remaining: {credits:,} credits[/dim]")

def api_post(path, body, require_auth=True):
    try:
        headers = get_headers() if require_auth else get_optional_headers()
        r = httpx.post(f"{API_BASE}{path}", headers=headers, json=body, timeout=60)
        data = r.json() if r.text else {}
        if r.status_code >= 400:
            return format_api_error(r, data)
        return data
    except Exception as e:
        return {"error": str(e)}


def format_api_error(response, data):
    status = response.status_code
    payload = data if isinstance(data, dict) else {}
    result = dict(payload)
    result.setdefault("error", payload.get("detail") if isinstance(payload, dict) else response.text or f"HTTP {status}")
    result["_http_status"] = status

    if status == 402:
        need = payload.get("error", "")
        result["friendly_error"] = "This command requires available credits or x402 payment."
        result["next_steps"] = [
            "Buy credits: blockintql buy --email YOUR_EMAIL",
            "Or enable x402 payment with: blockintql pay --auto-pay",
        ]
    elif status == 401:
        result["friendly_error"] = "API key is missing, invalid, or expired."
        result["next_steps"] = [
            "Generate a key: blockintql init",
            "Or save an existing key: blockintql auth --api-key YOUR_KEY",
        ]
    return result


def enrich_with_provider(result, address, chain, provider_name, provider_key, provider_url):
    if not provider_name:
        return result
    provider = get_provider(provider_name, provider_key or "", url_template=provider_url)
    if not provider:
        err_console.print(f"[yellow]Unknown provider: {provider_name}[/]")
        return result
    if provider.requires_api_key and not provider_key:
        err_console.print(f"[yellow]{provider_name} requires --provider-key or BLOCKINTQL_PROVIDER_KEY[/]")
        return result

    pd = provider.get_address_risk(address, chain)

    if "error" in pd.get("raw", {}):
        return result

    result["risk_score"] = max(pd.get("risk_score", 0), result.get("risk_score", 0))
    if pd.get("entity_name") and not result.get("entity"):
        result["entity"] = pd["entity_name"]
    if pd.get("sanctions_hit"):
        result["verdict"] = "BLOCK"
        result["safe"] = False
        result.setdefault("risk_indicators", []).append("SANCTIONS")
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


def print_rule():
    console.print(f"  [dim]{'─' * 52}[/dim]")


def preview_addresses(addresses, limit=3):
    items = [a for a in addresses if a]
    if not items:
        return "none"
    shown = items[:limit]
    if len(items) > limit:
        shown.append(f"+{len(items) - limit} more")
    return ", ".join(shown)


def render_status(data):
    console.print()
    console.print("  [bold green]Account active[/bold green]")
    print_rule()
    console.print(f"  [dim]key      [/dim] {data.get('key_prefix', 'unknown')}")
    console.print(f"  [dim]tier     [/dim] {data.get('tier', 'unknown')}")
    console.print(f"  [dim]credits  [/dim] {data.get('credits', 0)}")
    console.print(f"  [dim]name     [/dim] {data.get('display_name') or 'Not set'}")
    console.print(f"  [dim]email    [/dim] {data.get('email') or 'Not set'}")
    if data.get("created_at"):
        console.print(f"  [dim]created  [/dim] {data['created_at']}")
    print_rule()
    if data.get("credits", 0) <= 0:
        console.print("  [yellow]No available credits on this key[/yellow]")
        console.print("  [dim]Next: blockintql buy --email YOUR_EMAIL[/dim]")
        console.print("  [dim]Or use x402 per request: blockintql pay --auto-pay[/dim]")
    else:
        console.print("  [dim]Next: blockintql verdict <address>[/dim]")
    console.print()


def render_trace(data):
    console.print()
    console.print("  [bold cyan]Trace complete[/bold cyan]")
    print_rule()
    console.print(f"  [dim]txid     [/dim] {data.get('txid', '')}")
    console.print(f"  [dim]method   [/dim] {data.get('method', 'FIFO')}")
    console.print(f"  [dim]hops     [/dim] {data.get('hops_analyzed', 0)} analyzed / {data.get('transactions_traced', 0)} txs")
    console.print(f"  [dim]outputs  [/dim] {data.get('traceable_outputs', 0)} traceable outputs")
    if data.get("narrative"):
        print_rule()
        console.print(f"  [dim]{data['narrative']}[/dim]")

    tx_summary = data.get("tx_summary") or {}
    if tx_summary:
        print_rule()
        console.print("  [bold]Transaction Shape[/bold]")
        console.print(f"  [dim]in/out   [/dim] {tx_summary.get('input_count', 0)} inputs · {tx_summary.get('output_count', 0)} outputs")
        console.print(f"  [dim]btc      [/dim] {tx_summary.get('total_input_btc', 0)} in · {tx_summary.get('total_output_btc', 0)} out")
        console.print(f"  [dim]fee      [/dim] {tx_summary.get('fee_btc', 0)} BTC")
        console.print(f"  [dim]largest  [/dim] {tx_summary.get('largest_output_btc', 0)} BTC")
        console.print(f"  [dim]inputs   [/dim] {preview_addresses(tx_summary.get('input_addresses', []))}")
        console.print(f"  [dim]outputs  [/dim] {preview_addresses(tx_summary.get('output_addresses', []))}")

    observations = data.get("observations") or []
    if observations:
        print_rule()
        console.print("  [bold]Observations[/bold]")
        for item in observations[:4]:
            console.print(f"  [dim]• {item}[/dim]")

    destinations = data.get("destinations") or []
    if destinations:
        print_rule()
        console.print("  [bold]Resolved Destinations[/bold]")
        for dest in destinations[:5]:
            label = dest.get("entity") or dest.get("destination_type", "unknown")
            console.print(f"  [dim]• {dest.get('amount_btc', 0)} BTC -> {label} (hop {dest.get('hop', '?')})[/dim]")

    unresolved = data.get("unresolved_spends") or []
    if unresolved:
        print_rule()
        console.print(f"  [bold]Unresolved Spends[/bold] [dim]({len(unresolved)})[/dim]")
        for item in unresolved[:4]:
            console.print(f"  [dim]• {item.get('amount_btc', 0)} BTC at {item.get('address', 'unknown')}[/dim]")

    skipped = data.get("skipped") or []
    if skipped:
        print_rule()
        console.print(f"  [bold]Skipped During Analysis[/bold] [dim]({len(skipped)})[/dim]")
        for item in skipped[:3]:
            console.print(f"  [dim]• {item.get('txid', '')} — {item.get('reason', 'unknown')}[/dim]")

    print_rule()
    console.print("  [dim]Next: blockintql report --address <address> --entity \"Observed Entity\" --category OTHER[/dim]")
    console.print()


def render_opreturn_search(data):
    console.print()
    count = data.get("results", 0)
    title = "OP_RETURN matches found" if count else "No OP_RETURN matches found"
    color = "green" if count else "yellow"
    console.print(f"  [bold {color}]{title}[/bold {color}]")
    print_rule()
    console.print(f"  [dim]query    [/dim] {data.get('query') or '(none)'}")
    console.print(f"  [dim]protocol [/dim] {data.get('protocol', 'all')}")
    console.print(f"  [dim]results  [/dim] {count}")

    summary = data.get("summary") or {}
    top_protocols = summary.get("top_protocols") or []
    if top_protocols:
        top_summary = ", ".join(f"{row['protocol']} ({row['count']})" for row in top_protocols[:3])
        console.print(f"  [dim]top      [/dim] {top_summary}")
    if "identity_hit_count" in summary:
        console.print(f"  [dim]identity [/dim] {summary.get('identity_hit_count', 0)} records")

    rows = data.get("data") or []
    if rows:
        print_rule()
        console.print("  [bold]Previews[/bold]")
        for row in rows[:3]:
            proto = row.get("protocol") or "unknown"
            txid = row.get("tx_hash", "")[:12]
            preview = row.get("preview") or row.get("decoded_text") or "(no preview)"
            console.print(f"  [dim]• {proto} · {txid}…[/dim]")
            console.print(f"    {preview}")

    guidance = data.get("guidance") or {}
    tips = guidance.get("tips") or []
    if tips:
        print_rule()
        console.print("  [bold]Search Tips[/bold]")
        for tip in tips[:3]:
            console.print(f"  [dim]• {tip}[/dim]")

    print_rule()
    console.print("  [dim]Next: try a shorter keyword or add --protocol for a narrower search[/dim]")
    console.print()


def render_opreturn_tx(data):
    console.print()
    found = data.get("found", False)
    console.print(f"  [bold {'green' if found else 'yellow'}]{'OP_RETURN data found' if found else 'No indexed OP_RETURN data found'}[/bold {'green' if found else 'yellow'}]")
    print_rule()
    console.print(f"  [dim]txid     [/dim] {data.get('tx_hash', '')}")
    console.print(f"  [dim]results  [/dim] {data.get('results', 0)}")
    rows = data.get("data") or []
    for row in rows[:3]:
        console.print(f"  [dim]protocol [/dim] {row.get('protocol') or 'unknown'}")
        console.print(f"  [dim]preview  [/dim] {row.get('preview') or '(no preview)'}")
    guidance = (data.get("guidance") or {}).get("tips") or []
    if guidance:
        print_rule()
        for tip in guidance[:2]:
            console.print(f"  [dim]• {tip}[/dim]")
    console.print()


def render_stablecoin_balances(data):
    payload = data.get("data", data)
    balances = payload.get("stablecoin_balances", {})
    console.print()
    console.print("  [bold cyan]Stablecoin balances[/bold cyan]")
    print_rule()
    console.print(f"  [dim]address  [/dim] {payload.get('address', '')}")
    console.print(f"  [dim]total    [/dim] ${payload.get('wallet_total_usd', 0)}")
    coverage = payload.get("coverage", {})
    if coverage.get("coverage_note"):
        console.print(f"  [dim]coverage [/dim] {coverage['coverage_note']}")
    if balances:
        print_rule()
        for symbol, item in balances.items():
            console.print(f"  [dim]{symbol:<8}[/dim] {item.get('balance', 0)}")
    console.print()


def render_stablecoin_history(data):
    payload = data.get("data", data)
    rows = payload.get("rows", [])
    console.print()
    console.print("  [bold cyan]Stablecoin history[/bold cyan]")
    print_rule()
    console.print(f"  [dim]address  [/dim] {payload.get('address', '')}")
    console.print(f"  [dim]window   [/dim] {payload.get('days', 0)} days · {payload.get('interval', 'day')}")
    console.print(f"  [dim]token    [/dim] {payload.get('token', 'all')}")
    if not rows:
        console.print("  [yellow]No stablecoin history found for this wallet and time window[/yellow]")
        console.print()
        return
    print_rule()
    for row in rows[:8]:
        bucket = str(row.get("bucket", ""))[:19]
        console.print(
            f"  [dim]{bucket}[/dim]  "
            f"{row.get('token_symbol', ''):<5}  "
            f"+{row.get('incoming_amount', 0)}  "
            f"-{row.get('outgoing_amount', 0)}  "
            f"net {row.get('net_amount', 0)}"
        )
    console.print()


def render_stablecoin_counterparties(data):
    payload = data.get("data", data)
    rows = payload.get("counterparties", [])
    console.print()
    console.print("  [bold cyan]Stablecoin counterparties[/bold cyan]")
    print_rule()
    console.print(f"  [dim]address  [/dim] {payload.get('address', '')}")
    console.print(f"  [dim]token    [/dim] {payload.get('token', 'all')}")
    console.print(f"  [dim]window   [/dim] {payload.get('days', 0)} days")
    console.print(f"  [dim]dir      [/dim] {payload.get('direction', 'both')}")
    if not rows:
        console.print("  [yellow]No stablecoin counterparties found for this wallet and filter set[/yellow]")
        console.print()
        return
    print_rule()
    for row in rows[:8]:
        counterparty = row.get("counterparty", "unknown")
        if len(counterparty) > 18:
            counterparty = f"{counterparty[:8]}...{counterparty[-6:]}"
        console.print(
            f"  [dim]{row.get('token_symbol', ''):<5}[/dim] "
            f"{counterparty:<20} "
            f"{row.get('direction', ''):<8} "
            f"{row.get('total_amount', 0)}"
        )
    console.print()


def render_stablecoin_flows(data):
    payload = data.get("data", data)
    series = payload.get("series", [])
    console.print()
    console.print("  [bold cyan]Stablecoin flows[/bold cyan]")
    print_rule()
    console.print(f"  [dim]window   [/dim] {payload.get('hours', 0)} hours")
    console.print(f"  [dim]interval [/dim] {payload.get('interval', 'hour')}")
    console.print(f"  [dim]token    [/dim] {payload.get('token', 'all')}")
    summary = payload.get("summary", {})
    if summary:
        top = sorted(summary.items(), key=lambda kv: kv[1].get("total_volume", 0), reverse=True)[:4]
        print_rule()
        for symbol, stats in top:
            console.print(f"  [dim]{symbol:<5}[/dim] volume {round(stats.get('total_volume', 0), 2)} · txs {stats.get('transfer_count', 0)}")
    if not series:
        console.print("  [yellow]No stablecoin flow activity found for this window[/yellow]")
        console.print()
        return
    print_rule()
    for row in series[:10]:
        bucket = str(row.get("bucket", ""))[:19]
        volume = float(row.get("total_volume") or 0)
        bar_length = min(24, max(1, int(volume / 100000))) if volume > 0 else 0
        bar = "█" * bar_length
        console.print(
            f"  [dim]{bucket}[/dim] "
            f"{row.get('token_symbol', ''):<5} "
            f"{bar} {round(volume, 2)}"
        )
    console.print()


def render_stablecoin_large_transfers(data):
    payload = data.get("data", data)
    rows = payload.get("rows", [])
    console.print()
    console.print("  [bold cyan]Large stablecoin transfers[/bold cyan]")
    print_rule()
    console.print(f"  [dim]token    [/dim] {payload.get('token', 'all')}")
    console.print(f"  [dim]window   [/dim] {payload.get('hours', 0)} hours")
    console.print(f"  [dim]minimum  [/dim] {payload.get('min_amount', 0)}")
    console.print(f"  [dim]count    [/dim] {payload.get('count', len(rows))}")
    if not rows:
        console.print("  [yellow]No large stablecoin transfers found for this filter set[/yellow]")
        console.print()
        return
    print_rule()
    for row in rows[:8]:
        tx_hash = row.get("tx_hash", "")
        short_tx = f"{tx_hash[:8]}...{tx_hash[-6:]}" if len(tx_hash) > 16 else tx_hash
        console.print(
            f"  [dim]{row.get('token_symbol', ''):<5}[/dim] "
            f"{short_tx:<18} "
            f"{row.get('amount', 0)}"
        )
    console.print()


def render_wallet_stablecoin_chart(data):
    payload = data.get("data", data)
    rows = payload.get("rows", [])
    console.print()
    console.print("  [bold cyan]Wallet stablecoin chart[/bold cyan]")
    print_rule()
    console.print(f"  [dim]address  [/dim] {payload.get('address', '')}")
    console.print(f"  [dim]window   [/dim] {payload.get('days', 0)} days · {payload.get('interval', 'day')}")
    console.print(f"  [dim]token    [/dim] {payload.get('token', 'all')}")
    if not rows:
        console.print("  [yellow]No stablecoin history found for this wallet and time window[/yellow]")
        console.print()
        return

    grouped = {}
    for row in rows:
        token = row.get("token_symbol", "UNK")
        grouped.setdefault(token, []).append(float(row.get("net_amount") or 0))

    print_rule()
    for token, values in list(grouped.items())[:4]:
        latest = values[:8]
        max_abs = max(abs(v) for v in latest) if latest else 1
        spark = []
        for value in latest:
            if max_abs == 0:
                spark.append("·")
            elif value > 0:
                spark.append("▇" if abs(value) / max_abs > 0.66 else "▅" if abs(value) / max_abs > 0.33 else "▃")
            elif value < 0:
                spark.append("▁" if abs(value) / max_abs > 0.66 else "▂" if abs(value) / max_abs > 0.33 else "·")
            else:
                spark.append("·")
        console.print(f"  [dim]{token:<5}[/dim] {''.join(spark)}  net {round(sum(latest), 2)}")
    console.print()


def render_counterparty_chart(data):
    payload = data.get("data", data)
    rows = payload.get("counterparties", [])
    console.print()
    console.print("  [bold cyan]Stablecoin counterparty chart[/bold cyan]")
    print_rule()
    console.print(f"  [dim]address  [/dim] {payload.get('address', '')}")
    console.print(f"  [dim]token    [/dim] {payload.get('token', 'all')}")
    console.print(f"  [dim]window   [/dim] {payload.get('days', 0)} days")
    if not rows:
        console.print("  [yellow]No counterparties found for this filter set[/yellow]")
        console.print()
        return

    max_amount = max(float(row.get("total_amount") or 0) for row in rows[:8]) or 1
    print_rule()
    for row in rows[:8]:
        counterparty = row.get("counterparty", "unknown")
        if len(counterparty) > 18:
            counterparty = f"{counterparty[:8]}...{counterparty[-6:]}"
        amount = float(row.get("total_amount") or 0)
        bar_length = max(1, int((amount / max_amount) * 24))
        console.print(
            f"  [dim]{counterparty:<20}[/dim] "
            f"{'█' * bar_length} {round(amount, 2)}"
        )
    console.print()


def render_workspace_plan(name, chain, modules):
    console.print()
    console.print("  [bold cyan]Workspace plan[/bold cyan]")
    print_rule()
    console.print(f"  [dim]name     [/dim] {name}")
    console.print(f"  [dim]chain    [/dim] {chain}")
    console.print(f"  [dim]modules  [/dim] {', '.join(modules)}")
    print_rule()
    console.print("  [dim]This will map to an ephemeral investigation workspace once the VM control plane is live.[/dim]")
    console.print("  [dim]Recommended modules: verdict, stablecoins, bridge-activity, chart[/dim]")
    console.print()


def render_workspace_status(data):
    console.print()
    console.print("  [bold cyan]Workspace[/bold cyan]")
    print_rule()
    console.print(f"  [dim]id       [/dim] {data.get('workspace_id', '')}")
    console.print(f"  [dim]name     [/dim] {data.get('name', '')}")
    console.print(f"  [dim]chain    [/dim] {data.get('chain', '')}")
    console.print(f"  [dim]status   [/dim] {data.get('status', '')}")
    console.print(f"  [dim]modules  [/dim] {', '.join(data.get('modules', []))}")
    if data.get("access_url"):
        console.print(f"  [dim]url      [/dim] {data.get('access_url')}")
    if data.get("ssh"):
        console.print(f"  [dim]ssh      [/dim] {data.get('ssh')}")
    notes = data.get("notes") or []
    if notes:
        print_rule()
        for note in notes[:4]:
            console.print(f"  [dim]• {note}[/dim]")
    print_rule()
    if data.get("status") in {"queued", "provisioning", "planned", "terminating"}:
        console.print(f"  [dim]Next: blockintql workspace status {data.get('workspace_id', '')}[/dim]")
    elif data.get("status") == "ready":
        console.print(f"  [dim]Next: blockintql workspace destroy {data.get('workspace_id', '')}[/dim]")
    console.print()


def render_capability_catalog(data):
    console.print()
    console.print("  [bold cyan]Capabilities[/bold cyan]")
    print_rule()
    console.print(f"  [dim]surfaces [/dim] {', '.join(data.get('surfaces', []))}")
    console.print(f"  [dim]version  [/dim] {data.get('version', 'unknown')}")
    notes = data.get("notes") or []
    if notes:
        for note in notes[:2]:
            console.print(f"  [dim]• {note}[/dim]")
    print_rule()

    grouped = {}
    for item in data.get("capabilities", []):
        grouped.setdefault(item.get("category", "other"), []).append(item)

    for category, rows in grouped.items():
        console.print(f"  [bold]{category.upper()}[/bold]")
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column(style="yellow", width=24)
        table.add_column(style="white")
        table.add_column(style="dim", justify="right", width=8)
        for row in rows:
            cost = row.get("estimated_cost", {}).get("credits")
            cost_label = "Free" if cost in (None, 0) and not row.get("price_usd") else str(cost) if cost is not None else "Varies"
            table.add_row(row.get("id", ""), row.get("description", ""), cost_label)
        console.print(table)
    console.print()


def render_plan(data):
    console.print()
    console.print("  [bold cyan]Investigation plan[/bold cyan]")
    print_rule()
    console.print(f"  [dim]goal     [/dim] {data.get('goal', '')}")
    if data.get("address"):
        console.print(f"  [dim]address  [/dim] {data.get('address')}")
    console.print(f"  [dim]chain    [/dim] {data.get('chain', '')}")
    console.print(f"  [dim]surface  [/dim] {data.get('recommended_surface', 'api')}")
    console.print(f"  [dim]estimate [/dim] {data.get('estimated_total_credits', 0)} credits · ${data.get('estimated_total_usd', 0)}")
    if data.get("upto_budget_usd") not in (None, 0, 0.0):
        console.print(f"  [dim]upto     [/dim] ${data.get('upto_budget_usd')} suggested ceiling")
    if data.get("execution_mode"):
        console.print(f"  [dim]mode     [/dim] {data.get('execution_mode')}")
    if data.get("summary"):
        print_rule()
        console.print(f"  [dim]{data['summary']}[/dim]")
    steps = data.get("steps") or []
    if steps:
        print_rule()
        for idx, step in enumerate(steps, start=1):
            cost = step.get("estimated_credits")
            cost_label = f"{cost} cr" if cost is not None else "varies"
            console.print(f"  [bold]{idx}. {step.get('title', '')}[/bold] [dim]({step.get('surface', 'api')} · {cost_label})[/dim]")
            console.print(f"     {step.get('rationale', '')}")
            if step.get("endpoint"):
                console.print(f"     [dim]endpoint:[/dim] {step['endpoint']}")
            if step.get("cli_command"):
                console.print(f"     [dim]cli:[/dim] {step['cli_command']}")
    first_step = data.get("first_executable_step")
    workspace = data.get("recommended_workspace")
    execution_skipped = data.get("execution_skipped")
    if first_step or workspace:
        print_rule()
    if first_step:
        console.print(f"  [dim]first executable:[/dim] {first_step.get('title', first_step.get('capability_id', ''))}")
    if workspace:
        console.print(f"  [dim]workspace:[/dim] {workspace.get('name')} [{', '.join(workspace.get('modules', []))}]")
    if execution_skipped:
        print_rule()
        console.print(f"  [yellow]execution skipped[/yellow] [dim]· {execution_skipped.get('reason', '')}[/dim]")
        if execution_skipped.get("next"):
            console.print(f"  [dim]{execution_skipped.get('next')}[/dim]")
    print_rule()
    console.print("  [dim]Next: run the first executable step directly, open the recommended workspace, or pass this plan into your own agent workflow[/dim]")
    console.print()


def execute_planned_first_step(plan, address):
    step = plan.get("first_executable_step")
    if not step:
        steps = plan.get("steps") or []
        if not steps:
            return {"error": "No executable steps in plan"}
        step = steps[0]

    if not step:
        return {"error": "No executable steps in plan"}
    capability_id = step.get("capability_id")
    plan_address = plan.get("address") or address

    if capability_id == "verdict":
        if not plan_address:
            return {"error": "Address required to execute verdict"}
        return api_post("/v1/verdict", {"address": plan_address, "chain": "ethereum"})

    if capability_id == "screen":
        if not plan_address:
            return {"error": "Address required to execute screen"}
        return api_post("/v1/screen", {"address": plan_address, "chain": "ethereum"})

    if capability_id == "stablecoin_balances":
        if not plan_address:
            return {"error": "Address required to fetch stablecoin balances"}
        return api_get(f"/v1/eth/address/{plan_address}/stablecoins")

    if capability_id == "stablecoin_counterparties":
        if not plan_address:
            return {"error": "Address required to fetch stablecoin counterparties"}
        return api_get(f"/v1/eth/address/{plan_address}/stablecoin-counterparties", params={"direction": "both", "days": 30, "limit": 25})

    if capability_id == "stablecoin_history":
        if not plan_address:
            return {"error": "Address required to fetch stablecoin history"}
        return api_get(f"/v1/eth/address/{plan_address}/stablecoin-history", params={"days": 30, "interval": "day"})

    if capability_id == "stablecoin_flows":
        return api_get("/v1/eth/stablecoins/flows", params={"hours": 24, "interval": "hour"})

    return {"error": f"First planned step '{capability_id}' is not executable from ask yet"}


def open_planned_workspace(plan, address, goal):
    workspace = plan.get("recommended_workspace")
    if workspace:
        body = dict(workspace.get("payload") or {})
        if not body.get("name"):
            body["name"] = workspace.get("name") or "workspace"
        if not body.get("chain"):
            body["chain"] = plan.get("chain") or "ethereum"
        if not body.get("modules"):
            body["modules"] = workspace.get("modules") or ["verdict", "stablecoins", "bridge-activity", "chart"]
        if address and "address" not in body:
            body["address"] = address
        return api_post("/v1/workspaces/create", body)

    steps = plan.get("steps") or []
    has_workspace = any(step.get("capability_id") == "workspace_create" for step in steps)
    if not has_workspace:
        return {"error": "Plan does not recommend a workspace"}

    slug = "".join(c.lower() if c.isalnum() else "-" for c in (goal or "workspace"))[:32].strip("-") or "workspace"
    modules = ["verdict", "stablecoins", "bridge-activity", "chart"]
    if any(step.get("capability_id") == "stablecoin_counterparties" for step in steps):
        modules.append("counterparties")
    body = {"name": slug, "chain": "ethereum", "modules": modules}
    if address:
        body["address"] = address
    return api_post("/v1/workspaces/create", body)


def should_retry_plan_without_execution(data):
    if "error" not in data:
        return False
    text = f"{data.get('error', '')} {data.get('friendly_error', '')}".lower()
    triggers = [
        "api key required",
        "requires available credits",
        "x402 payment",
        "missing api key",
    ]
    return any(trigger in text for trigger in triggers)


def output(data, agent, quiet):
    if agent or not sys.stdout.isatty():
        click.echo(json.dumps(data, indent=2, default=str))
        return
    if "error" in data:
        err_console.print(f"  [red]✗[/red] {data.get('friendly_error') or data['error']}")
        if data.get("error") and data.get("friendly_error") and data["friendly_error"] != data["error"]:
            err_console.print(f"  [dim]{data['error']}[/dim]")
        for step in data.get("next_steps", []):
            err_console.print(f"  [dim]{step}[/dim]")
        return

    if "key_prefix" in data and "credits" in data and "tier" in data:
        render_status(data)
        return

    if "verdict" in data and "risk_score" in data:
        v = data["verdict"]
        color = verdict_color(v)
        risk = int(data.get("risk_score", 0))
        safe = data.get("safe", False)

        console.print()
        console.print(
            f"  [bold {color}]{v}[/bold {color}]  [dim]·[/dim]  "
            f"[{color}]{risk}/100 risk[/{color}]  [dim]·[/dim]  "
            f"[dim]{'SAFE' if safe else 'DO NOT TRANSACT'}[/dim]"
        )
        console.print(f"  [dim]{'─' * 52}[/dim]")

        if not quiet:
            addr = data.get("address") or data.get("subject", "")
            console.print(f"  [dim]address [/dim] {addr}")
            console.print(f"  [dim]chain   [/dim] {data.get('chain', '')}")
            console.print(f"  [dim]entity  [/dim] {data.get('entity') or 'Unknown'}")
            if data.get("risk_indicators"):
                console.print(f"  [dim]flags   [/dim] [{color}]{', '.join(data['risk_indicators'])}[/{color}]")
            if data.get("action"):
                console.print(f"  [dim]action  [/dim] {data['action']}")
            if data.get("provider_data"):
                pd = data["provider_data"]
                console.print(f"  [dim]{'─' * 52}[/dim]")
                console.print(f"  [dim]{pd.get('provider', '').upper()} · local · key never sent to BlockINTQL[/dim]")
                if pd.get("entity_name"):
                    console.print(f"  [dim]entity  [/dim] {pd['entity_name']}")
                console.print(f"  [dim]risk    [/dim] {pd.get('risk_score', 0)}/100")
                if pd.get("sanctions_hit"):
                    console.print(f"  [red]  ⚠  SANCTIONS HIT[/red]")
            if data.get("narrative"):
                console.print(f"  [dim]{'─' * 52}[/dim]")
                console.print(f"  [dim]{data['narrative'][:300]}[/dim]")

        console.print(f"  [dim]{'─' * 52}[/dim]")
        console.print("  [dim]BlockINTQL · block6iq.com[/dim]")
        console.print()
        return

    if "profile" in data:
        found = data.get("found", False)
        console.print()
        status = "[bold green]█ FOUND[/bold green]" if found else "[dim]█ NOT FOUND[/dim]"
        console.print(f"  {status}")
        console.print(f"  [dim]{'─' * 52}[/dim]")
        console.print(f"  [dim]identifier[/dim] {data['identifier']} ({data.get('identifier_type', '')})")
        if found:
            p = data.get("profile", {})
            if p.get("entity_name"):
                console.print(f"  [dim]entity    [/dim] {p['entity_name']}")
            console.print(f"  [dim]risk      [/dim] {p.get('risk_score', 0)}/100")
            for addr in p.get("linked_bitcoin_addresses", [])[:5]:
                console.print(f"  [dim]btc       [/dim] {addr}")
            for l in p.get("linked_identifiers", [])[:5]:
                console.print(f"  [dim]linked    [/dim] {l['identifier']} ({l['type']})")
        console.print(f"  [dim]{'─' * 52}[/dim]")
        console.print("  [dim]BlockINTQL · OP_RETURN identity graph · block6iq.com[/dim]")
        console.print()
        return

    if "tx_summary" in data and "transactions_traced" in data:
        render_trace(data)
        return

    if "query" in data and "guidance" in data and "summary" in data and "data" in data:
        render_opreturn_search(data)
        return

    if "tx_hash" in data and "found" in data and "guidance" in data:
        render_opreturn_tx(data)
        return

    if ("stablecoin_balances" in data.get("data", {}) or "stablecoin_balances" in data) and "coverage" in data.get("data", data):
        render_stablecoin_balances(data)
        return

    if "rows" in data.get("data", {}) and "interval" in data.get("data", {}) and "days" in data.get("data", {}):
        render_stablecoin_history(data)
        return

    if "counterparties" in data.get("data", {}) and "direction" in data.get("data", {}):
        render_stablecoin_counterparties(data)
        return

    if "series" in data.get("data", {}) and "summary" in data.get("data", {}):
        render_stablecoin_flows(data)
        return

    if "rows" in data.get("data", {}) and "min_amount" in data.get("data", {}):
        render_stablecoin_large_transfers(data)
        return

    if "workspace_id" in data and "modules" in data and "status" in data:
        render_workspace_status(data)
        return

    if "capabilities" in data and "surfaces" in data:
        render_capability_catalog(data)
        return

    if "goal" in data and "steps" in data and "estimated_total_credits" in data:
        render_plan(data)
        return

    if not quiet:
        console.print_json(json.dumps(data, default=str))



def display_analytics_table(result):
    """Display analytics results as a Rich table."""
    columns = result.get("columns", [])
    rows = result.get("rows", [])
    
    if not rows:
        console.print("[yellow]No results found[/yellow]")
        return
    
    # Create table
    table = Table(box=box.ROUNDED, border_style="blue")
    
    # Add columns
    for col in columns:
        table.add_column(col.replace("_", " ").title(), style="cyan")
    
    # Add rows (limit to 50 for display)
    for row in rows[:50]:
        table.add_row(*[str(row.get(col, "")) for col in columns])
    
    console.print()
    console.print(table)
    console.print()
    console.print(f"[dim]Showing {min(len(rows), 50)} of {len(rows)} results[/dim]")

def display_analytics_chart(result):
    """Display analytics results as ASCII bar chart."""
    rows = result.get("rows", [])
    columns = result.get("columns", [])
    
    if not rows or len(columns) < 2:
        console.print("[yellow]Not enough data for chart[/yellow]")
        return
    
    # Assume first column is label, second is value
    label_col = columns[0]
    value_col = columns[1]
    
    console.print(f"\n[bold]{value_col.replace('_', ' ').title()}[/bold]\n")
    
    # Get max value for scaling
    max_val = max(float(row.get(value_col, 0)) for row in rows[:20])
    
    # Display bars
    for row in rows[:20]:
        label = str(row.get(label_col, ""))[:20]
        value = float(row.get(value_col, 0))
        bar_length = int((value / max_val) * 50) if max_val > 0 else 0
        bar = "█" * bar_length
        console.print(f"{label:20} {bar} {value:,.0f}")
    
    console.print()
provider_opts = [
    click.option(
        "--provider",
        "-p",
        default=None,
        type=click.Choice(["chainalysis", "trm", "elliptic", "crystal", "merkle_science", "nomis", "generic"]),
        help="Attribution provider (key stays on your machine)",
    ),
    click.option(
        "--provider-key",
        default=None,
        envvar="BLOCKINTQL_PROVIDER_KEY",
        help="Provider API key — never sent to BlockINTQL",
    ),
    click.option(
        "--provider-url",
        default=None,
        help="Custom provider URL template with {address} placeholder",
    ),
]


def with_provider(f):
    for opt in reversed(provider_opts):
        f = opt(f)
    return f


class CustomGroup(click.Group):
    def format_help(self, ctx, formatter):
        # Delegate to our custom branded help
        cli.invoke(ctx)

@click.group(cls=CustomGroup, invoke_without_command=True)
@click.version_option(__version__, prog_name="blockintql")
@click.pass_context
def cli(ctx):
    """BlockINTQL — Sovereign Blockchain Intelligence CLI"""
    if ctx.invoked_subcommand is None:
        console.print(BLOCKINTQL_BANNER)
        v = __version__
        credits = fetch_credits()
        key = get_api_key()
        # Status line
        if key:
            status = f"[green]●[/green] authenticated"
            if credits is not None:
                status += f" · [bold]{credits:,}[/bold] credits"
            else:
                status += " · [dim]credits: unknown[/dim]"
        else:
            status = "[red]●[/red] no API key — run: blockintql init"
        console.print(f"  [dim]v{v}[/dim]  {status}")
        console.print()
        console.print("  [bold]SETUP[/bold]")
        console.print("    init              Generate API key")
        console.print("    auth              Save existing API key")
        console.print("    buy               Purchase credits via Stripe")
        console.print("    pay               Configure x402 USDC payments")
        console.print("    status            Check key & credit balance")
        console.print()
        console.print("  [bold]INTELLIGENCE[/bold]")
        console.print("    verdict           Screen address — CLEAR / CAUTION / BLOCK")
        console.print("    screen            Full risk screening with narrative")
        console.print()
        console.print("  [bold]ANALYSIS[/bold]")
        console.print("    analyze           AI-powered wallet analysis")
        console.print("    query             Natural language wallet and stablecoin query")
        console.print("    capabilities      List supported CLI capabilities")
        console.print()
        console.print("  [bold]DATA[/bold]")
        console.print("    providers         List enrichment providers")
        console.print("    stablecoins       Stablecoin intelligence and wallet views")
        console.print("    chart             Terminal-native chart views")
        console.print()
        console.print("  [bold]COMMUNITY[/bold]  [dim](free)[/dim]")
        console.print("    report            Report address(es) for review")
        console.print("    list-categories   Valid reporting categories")
        console.print("    label-search      Search address labels")
        console.print("    leaderboard       Attribution leaderboard")
        console.print("    set-name          Set your display name")
        console.print()
        console.print("  [dim]Docs: https://blockintql.com/docs/blockintql · GitHub: github.com/block6iq/blockintql-cli[/dim]")
        console.print()


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
@click.argument("address")
@click.option("--chain", "-c", default="bitcoin", type=click.Choice(["bitcoin", "ethereum"]))
@click.option("--context", default="")
@with_provider
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def verdict(address, chain, context, provider, provider_key, provider_url, agent, quiet):
    if not agent and sys.stdout.isatty():
        if not show_credit_cost("verdict"):
            return
    config = load_config()
    provider = provider or config.get("default_provider")
    if not quiet and not agent:
        p_info = f" + {provider} (local)" if provider else ""
        console.print(f"[dim]Screening {address[:20]}...{p_info}[/]")

    result = api_post("/v1/verdict", {"address": address, "chain": chain, "context": context})

    if provider and "error" not in result:
        result = enrich_with_provider(result, address, chain, provider, provider_key, provider_url)

    output(result, agent, quiet)


@cli.command()
@click.argument("address")
@click.option("--chain", "-c", default="bitcoin", type=click.Choice(["bitcoin", "ethereum"]))
@with_provider
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def screen(address, chain, provider, provider_key, provider_url, agent, quiet):
    if not agent and sys.stdout.isatty():
        if not show_credit_cost("screen"):
            return
    config = load_config()
    provider = provider or config.get("default_provider")
    if not quiet and not agent:
        p_info = f" + {provider} (local)" if provider else ""
        console.print(f"[dim]Screening {address[:20]}...{p_info}[/]")

    result = api_post("/v1/screen", {"address": address, "chain": chain})

    if provider and "error" not in result:
        result = enrich_with_provider(result, address, chain, provider, provider_key, provider_url)

    output(result, agent, quiet)


@cli.command()
@click.argument("query", required=False)
@click.option("--address", "-a", multiple=True)
@click.option("--chain", "-c", default="ethereum", type=click.Choice(["bitcoin", "ethereum", "both"]))
@click.option("--format", "fmt", default="full", type=click.Choice(["full", "graph", "narrative"]))
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def analyze(query, address, chain, fmt, agent, quiet):
    if not query and not address:
        raise click.UsageError("Provide a QUERY or --address")
    if not quiet and not agent:
        console.print("[dim]Running autonomous analysis...[/]")
    result = api_post(
        "/v1/analyze",
        {"query": query or "", "addresses": list(address), "chain": chain, "output_format": fmt},
    )
    output(result, agent, quiet)


@cli.command(hidden=True)
@click.argument("identifier")
@click.option(
    "--type",
    "id_type",
    default="auto",
    type=click.Choice(["auto", "email", "telegram", "twitter", "phone", "btc_address", "eth_address", "pgp_fingerprint"]),
)
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def profile(identifier, id_type, agent, quiet):
    if not quiet and not agent:
        console.print("[dim]Searching identity graph...[/]")
    result = api_get("/v1/profile/search", {"identifier": identifier, "type": id_type})
    output(result, agent, quiet)


@cli.command(hidden=True)
@click.option("--txid", "-t", required=True)
@click.option("--hops", default=5)
@click.option("--method", default="fifo", type=click.Choice(["fifo", "lifo"]))
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def trace(txid, hops, method, agent, quiet):
    if not quiet and not agent:
        console.print(f"[dim]Tracing {txid[:20]}... ({hops} hops)[/]")
    result = api_post("/v1/trace", {"txid": txid, "hops": hops, "method": method})
    output(result, agent, quiet)


@cli.command()
@click.argument("query")
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def query(query, agent, quiet):
    if not quiet and not agent:
        console.print("[dim]Processing...[/]")
    result = api_post("/v1/intelligence/search", {"query": query})
    output(result, agent, quiet)


@cli.command()
@click.argument("goal")
@click.option("--address", "-a", default="")
@click.option("--chain", "-c", default="ethereum", type=click.Choice(["ethereum"]))
@click.option("--budget-credits", type=int, default=None)
@click.option("--budget-usd", type=float, default=None)
@click.option("--surface", "prefer_surface", default="auto", type=click.Choice(["auto", "api", "cli", "mcp", "workspace"]))
@click.option("--execute-first-step", is_flag=True, help="Execute the first recommended sync step after planning")
@click.option("--open-workspace", is_flag=True, help="Create a workspace if the plan recommends one")
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def ask(goal, address, chain, budget_credits, budget_usd, prefer_surface, execute_first_step, open_workspace, agent, quiet):
    if not quiet and not agent:
        console.print("[dim]Planning investigation workflow...[/]")
    body = {
        "goal": goal,
        "address": address,
        "chain": chain,
        "budget_credits": budget_credits,
        "budget_usd": budget_usd,
        "prefer_surface": prefer_surface,
        "execute": bool(execute_first_step),
        "execute_workspace": bool(open_workspace),
    }
    result = api_post("/v1/plan", body, require_auth=False)
    if "error" in result and (execute_first_step or open_workspace) and should_retry_plan_without_execution(result):
        fallback_body = dict(body)
        fallback_body["execute"] = False
        fallback = api_post("/v1/plan", fallback_body, require_auth=False)
        if "error" not in fallback:
            fallback["execution_skipped"] = {
                "reason": "Execution requires credits or payment authorization",
                "next": "Authenticate with an API key, add credits, or enable x402 before executing actions",
            }
            result = fallback
    if "error" not in result and open_workspace:
        if result.get("execution_skipped"):
            pass
        elif result.get("executed_workspace") is not None:
            result = result["executed_workspace"]
        else:
            result = open_planned_workspace(result, address, goal)
    elif "error" not in result and execute_first_step:
        if result.get("execution_skipped"):
            pass
        elif result.get("executed_action", {}).get("result") is not None:
            result = result["executed_action"]["result"]
        else:
            result = execute_planned_first_step(result, address)
    output(result, agent, quiet)



@cli.command(hidden=True)
@click.argument("query_text")
@click.option("--format", "fmt", default="table", type=click.Choice(["table", "json", "chart"]))
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def analytics(query_text, fmt, agent, quiet):
    """Run analytics queries with instant results from materialized views.
    
    Examples:
      blockintql analytics "daily active users"
      blockintql analytics "top 50 USDT holders"
      blockintql analytics "token launches last week"
    """
    if not agent and sys.stdout.isatty():
        if not show_credit_cost("analytics"):
            return
    
    if not quiet and not agent:
        console.print("[dim]Running analytics query...[/]")
    
    result = api_post("/v1/analytics", {"query": query_text})
    
    if agent or fmt == "json":
        click.echo(json.dumps(result, indent=2))
        return
    
    if "error" in result:
        err_console.print(f"  [red]✗[/red] {result['error']}")
        return
    
    # Format as table or chart
    if fmt == "table":
        display_analytics_table(result)
    elif fmt == "chart":
        display_analytics_chart(result)
    
    if not agent and sys.stdout.isatty():
        show_credit_after("analytics")
@cli.command()
@click.option("--agent", is_flag=True)
def providers(agent):
    data = list_providers()
    if agent or not sys.stdout.isatty():
        click.echo(json.dumps(data, indent=2))
        return
    t = Table(
        title="Attribution Providers (all local — keys never sent to BlockINTQL)",
        box=box.ROUNDED,
        border_style="blue",
    )
    t.add_column("Provider", style="bold yellow")
    t.add_column("Key Required")
    for p in data:
        t.add_row(p["name"], "No" if p["name"] in ("generic",) else "Yes")
    console.print(t)


@cli.group()
def stablecoins():
    """Stablecoin intelligence commands."""


@stablecoins.command("balances")
@click.argument("address")
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def stablecoin_balances(address, agent, quiet):
    if not quiet and not agent:
        console.print(f"[dim]Loading stablecoin balances for {address[:20]}...[/]")
    result = api_get(f"/v1/eth/address/{address}/stablecoins")
    output(result, agent, quiet)


@stablecoins.command("history")
@click.argument("address")
@click.option("--days", default=30, type=int)
@click.option("--interval", default="day", type=click.Choice(["hour", "day"]))
@click.option("--token", default=None)
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def stablecoin_history(address, days, interval, token, agent, quiet):
    if not quiet and not agent:
        console.print(f"[dim]Building stablecoin history for {address[:20]}...[/]")
    params = {"days": days, "interval": interval}
    if token:
        params["token"] = token
    result = api_get(f"/v1/eth/address/{address}/stablecoin-history", params=params)
    output(result, agent, quiet)


@stablecoins.command("counterparties")
@click.argument("address")
@click.option("--token", default=None)
@click.option("--direction", default="both", type=click.Choice(["inbound", "outbound", "both"]))
@click.option("--days", default=30, type=int)
@click.option("--limit", default=25, type=int)
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def stablecoin_counterparties(address, token, direction, days, limit, agent, quiet):
    if not quiet and not agent:
        console.print(f"[dim]Resolving stablecoin counterparties for {address[:20]}...[/]")
    params = {"direction": direction, "days": days, "limit": limit}
    if token:
        params["token"] = token
    result = api_get(f"/v1/eth/address/{address}/stablecoin-counterparties", params=params)
    output(result, agent, quiet)


@stablecoins.command("flows")
@click.option("--hours", default=24, type=int)
@click.option("--interval", default="hour", type=click.Choice(["hour", "day"]))
@click.option("--token", default=None)
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def stablecoin_flows(hours, interval, token, agent, quiet):
    if not quiet and not agent:
        console.print("[dim]Loading network stablecoin flows...[/]")
    params = {"hours": hours, "interval": interval}
    if token:
        params["token"] = token
    result = api_get("/v1/eth/stablecoins/flows", params=params)
    output(result, agent, quiet)


@stablecoins.command("large-transfers")
@click.option("--min-amount", default=100000, type=float)
@click.option("--hours", default=24, type=int)
@click.option("--token", default=None)
@click.option("--limit", default=100, type=int)
@click.option("--agent", is_flag=True)
@click.option("--quiet", "-q", is_flag=True)
def stablecoin_large_transfers(min_amount, hours, token, limit, agent, quiet):
    if not quiet and not agent:
        console.print("[dim]Loading large stablecoin transfers...[/]")
    params = {"min_amount": min_amount, "hours": hours, "limit": limit}
    if token:
        params["token"] = token
    result = api_get("/v1/eth/stablecoins/large-transfers", params=params)
    output(result, agent, quiet)


@cli.group()
def chart():
    """Terminal-native chart views."""


@chart.command("stablecoin-flows")
@click.option("--hours", default=24, type=int)
@click.option("--interval", default="hour", type=click.Choice(["hour", "day"]))
@click.option("--token", default=None)
@click.option("--agent", is_flag=True)
def chart_stablecoin_flows(hours, interval, token, agent):
    params = {"hours": hours, "interval": interval}
    if token:
        params["token"] = token
    result = api_get("/v1/eth/stablecoins/flows", params=params)
    output(result, agent, False)


@chart.command("wallet-stablecoins")
@click.argument("address")
@click.option("--days", default=30, type=int)
@click.option("--interval", default="day", type=click.Choice(["hour", "day"]))
@click.option("--token", default=None)
@click.option("--agent", is_flag=True)
def chart_wallet_stablecoins(address, days, interval, token, agent):
    params = {"days": days, "interval": interval}
    if token:
        params["token"] = token
    result = api_get(f"/v1/eth/address/{address}/stablecoin-history", params=params)
    if agent or not sys.stdout.isatty():
        output(result, agent, False)
        return
    if "error" in result:
        output(result, agent, False)
        return
    render_wallet_stablecoin_chart(result)


@chart.command("counterparties")
@click.argument("address")
@click.option("--token", default=None)
@click.option("--direction", default="both", type=click.Choice(["inbound", "outbound", "both"]))
@click.option("--days", default=30, type=int)
@click.option("--limit", default=25, type=int)
@click.option("--agent", is_flag=True)
def chart_counterparties(address, token, direction, days, limit, agent):
    params = {"direction": direction, "days": days, "limit": limit}
    if token:
        params["token"] = token
    result = api_get(f"/v1/eth/address/{address}/stablecoin-counterparties", params=params)
    if agent or not sys.stdout.isatty():
        output(result, agent, False)
        return
    if "error" in result:
        output(result, agent, False)
        return
    render_counterparty_chart(result)


@cli.group(hidden=True)
def workspace():
    """Ephemeral investigation workspace controls."""


@workspace.command("create")
@click.argument("name")
@click.option("--chain", default="ethereum", type=click.Choice(["ethereum"]))
@click.option("--modules", default="verdict,stablecoins,bridge-activity,chart")
@click.option("--agent", is_flag=True)
def workspace_create(name, chain, modules, agent):
    module_list = [m.strip() for m in modules.split(",") if m.strip()]
    if not agent and sys.stdout.isatty():
        console.print("[dim]Provisioning investigation workspace...[/]")
    result = api_post("/v1/workspaces/create", {"name": name, "chain": chain, "modules": module_list})
    output(result, agent, False)


@workspace.command("status")
@click.argument("workspace_id")
@click.option("--agent", is_flag=True)
def workspace_status(workspace_id, agent):
    result = api_get(f"/v1/workspaces/{workspace_id}")
    output(result, agent, False)


@workspace.command("destroy")
@click.argument("workspace_id")
@click.option("--agent", is_flag=True)
def workspace_destroy(workspace_id, agent):
    if not agent and sys.stdout.isatty():
        console.print("[dim]Destroying workspace...[/]")
    result = api_post(f"/v1/workspaces/{workspace_id}/destroy", {})
    output(result, agent, False)


@cli.command()
@click.option("--install", is_flag=True)
@click.option("--agent", is_flag=True)
@click.option("--category", type=click.Choice(["setup", "intelligence", "analysis", "data", "community"]), help="Filter by category")
def capabilities(install, agent, category):
    """List supported CLI capabilities."""

    if install:
        r = httpx.get(f"{API_BASE}/skills/skill.md", timeout=10)
        click.echo(r.text)
        return

    remote = api_get("/v1/capabilities", require_auth=False)
    if "error" not in remote:
        if category:
            remote["capabilities"] = [item for item in remote.get("capabilities", []) if item.get("category") == category]
        output(remote, agent, False)
        return

    commands = {
        "setup": [
            {"cmd": "init", "desc": "Generate API key", "credits": "Free"},
            {"cmd": "auth", "desc": "Save existing API key", "credits": "Free"},
            {"cmd": "buy", "desc": "Purchase credits via Stripe", "credits": "Free"},
            {"cmd": "pay", "desc": "Configure local x402 payment preferences", "credits": "Free"},
            {"cmd": "status", "desc": "Check account info and credits", "credits": "Free"},
        ],
        "intelligence": [
            {"cmd": "verdict", "desc": "Address risk verdict (CLEAR/CAUTION/BLOCK)", "credits": "2"},
            {"cmd": "screen", "desc": "Full counterparty screening with flags", "credits": "2"},
        ],
        "analysis": [
            {"cmd": "analyze", "desc": "AI forensic analysis for wallets and counterparties", "credits": "10"},
            {"cmd": "query", "desc": "Natural language wallet and stablecoin query", "credits": "10"},
            {"cmd": "ask", "desc": "Plan an investigation workflow from a goal", "credits": "Free"},
            {"cmd": "capabilities", "desc": "List supported CLI capabilities", "credits": "Free"},
        ],
        "data": [
            {"cmd": "providers", "desc": "List local enrichment providers", "credits": "Free"},
            {"cmd": "stablecoins", "desc": "Stablecoin intelligence commands", "credits": "Varies"},
            {"cmd": "chart", "desc": "Terminal-native chart views", "credits": "Varies"},
        ],
        "community": [
            {"cmd": "report", "desc": "Submit address labels for review", "credits": "Free"},
            {"cmd": "list-categories", "desc": "List valid reporting categories", "credits": "Free"},
            {"cmd": "label-search", "desc": "Search labeled addresses", "credits": "2"},
            {"cmd": "leaderboard", "desc": "View contributor leaderboard", "credits": "1"},
            {"cmd": "set-name", "desc": "Set your display name", "credits": "Free"},
        ],
    }

    if agent or not sys.stdout.isatty():
        payload = {
            "commands": [row["cmd"] for rows in commands.values() for row in rows],
            "categories": list(commands.keys()),
            "total_commands": sum(len(rows) for rows in commands.values()),
            "capabilities": commands,
            "privacy": "Provider keys never leave your machine",
            "docs": "https://blockintql.com/docs/blockintql",
            "source": "https://github.com/block6iq/blockintql-cli",
        }
        click.echo(json.dumps(payload, indent=2))
        return

    console.print(BLOCKINTQL_BANNER)
    credits = fetch_credits()
    key = get_api_key()
    if key:
        status = f"[green]●[/green] authenticated"
        if credits is not None:
            status += f" · [bold]{credits:,}[/bold] credits"
        else:
            status += " · [dim]credits: unknown[/dim]"
    else:
        status = "[red]●[/red] no API key — run: blockintql init"
    console.print(f"\n[bold]v{__version__}[/bold]  {status}\n")

    categories_to_show = {category: commands[category]} if category else commands
    for cat_name, rows in categories_to_show.items():
        console.print(f"\n[bold cyan]{cat_name.upper()}[/bold cyan]")
        t = Table(show_header=False, box=None, padding=(0, 2))
        t.add_column(style="yellow", width=18)
        t.add_column(style="white")
        t.add_column(style="dim", justify="right", width=8)
        for row in rows:
            t.add_row(row["cmd"], row["desc"], row["credits"])
        console.print(t)

    console.print("\n[dim]Docs: [/dim][cyan]https://blockintql.com/docs/blockintql[/cyan]")
    console.print("[dim]GitHub: [/dim][cyan]https://github.com/block6iq/blockintql-cli[/cyan]")


@cli.command()
@click.option("--wallet-type", default="cdp", type=click.Choice(["cdp", "privatekey"]))
@click.option("--cdp-key-id", default=None, envvar="BLOCKINTQL_CDP_KEY_ID")
@click.option("--cdp-private-key", default=None, envvar="BLOCKINTQL_CDP_PRIVATE_KEY")
@click.option("--private-key", default=None, envvar="BLOCKINTQL_PRIVATE_KEY")
@click.option("--auto-pay", is_flag=True)
@click.option("--max-payment", default=0.10)
def pay(wallet_type, cdp_key_id, cdp_private_key, private_key, auto_pay, max_payment):
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
    output(api_get("/v1/me"), agent, False)


@cli.command()
@click.option("--email", "-e", required=True, help="Email to receive your API key")
@click.option("--pack", default="starter", type=click.Choice(["starter", "pro"]))
@click.option("--agent", is_flag=True)
def buy(email, pack, agent):
    import webbrowser

    if not agent:
        console.print(f"[dim]Creating checkout for {email}...[/]")
    existing_key = get_api_key() or ""
    result = api_post("/v1/billing/checkout", {"email": email, "pack": pack, "api_key": existing_key}, require_auth=False)
    if "error" in result and not result.get("free_tier_exhausted"):
        err_console.print(f"  [red]✗[/red] {result['error']}")
        return
    checkout_url = result.get("checkout_url")
    if not checkout_url:
        err_console.print("[red]Could not create checkout session[/]")
        return
    if agent or not sys.stdout.isatty():
        click.echo(json.dumps({"checkout_url": checkout_url, "pack": pack, "email": email}, indent=2))
        return
    console.print(f"  [dim]Pack:[/dim]  {'$10 — 1,000 screens' if pack == 'starter' else '$40 — 5,000 screens'}")
    console.print(f"  [dim]Email:[/dim] {email}")
    console.print(f"  [dim]URL:[/dim]   {checkout_url}")
    console.print()
    try:
        webbrowser.open(checkout_url)
        console.print("[dim]Browser opened. Complete payment to receive your API key.[/]")
    except Exception:
        console.print("[dim]Copy the URL above to complete payment.[/]")
    console.print("[dim]Credits will be added to your existing key automatically.[/]")



@cli.command()
@click.option("--agent", is_flag=True)
def init(agent):
    """
    Generate a free API key instantly — no email, no payment required.
    10 free screens per day. Buy credits to remove the limit.

    \b
    Examples:
      blockintql init
      blockintql init --agent | jq -r '.api_key'
    """
    result = api_post("/v1/keys/generate", {}, require_auth=False)

    if "error" in result:
        err_console.print(f"  [red]✗[/red] {result['error']}")
        return

    key = result.get("api_key", "")

    if agent or not sys.stdout.isatty():
        click.echo(json.dumps(result, indent=2))
        return

    # Auto-save key
    config = load_config()
    config["api_key"] = key
    save_config(config)

    console.print()
    console.print(f"  [bold green]API key generated and saved[/bold green]")
    console.print(f"  [dim]{'─' * 50}[/dim]")
    console.print(f"  [dim]key    [/dim] {key}")
    console.print(f"  [dim]tier   [/dim] pay-as-you-go")
    console.print(f"  [dim]credits[/dim] 0 — buy credits to start")
    console.print(f"  [dim]{'─' * 50}[/dim]")
    console.print(f"  [dim]Need more?[/dim]")
    console.print(f"  blockintql buy --email YOUR_EMAIL")
    console.print(f"  blockintql pay --auto-pay [dim](agents — USDC on Base)[/dim]")
    console.print()



@cli.command()
@click.option("--address", "-a", default="")
@click.option("--bulk", type=click.Path(exists=True), default=None)
@click.option("--entity", "-e", required=True)
@click.option("--category", "-c", default="OTHER")
@click.option("--source-url", default="")
@click.option("--evidence", default="")
@click.option("--agent", is_flag=True)
def report(address, bulk, entity, category, source_url, evidence, agent):
    """Report address(es) for community review."""
    addresses = []
    if bulk:
        with open(bulk) as f:
            addresses = [l.strip() for l in f if l.strip()]
    elif address:
        addresses = [address]
    else:
        err_console.print("[red]Provide --address or --bulk[/red]"); return
    body = {"addresses": addresses, "entity": entity,
            "category": category.upper(), "source_url": source_url, "evidence": evidence}
    result = api_post("/v1/labels/report", body)
    if agent:
        click.echo(json.dumps(result, indent=2)); return
    if "error" in result:
        err_console.print(f"  [red]{result['error']}[/red]"); return
    cnt = result.get("count", 0)
    console.print(f"  [green]Submitted {cnt} address(es)[/green]")
    console.print(f"  [dim]entity:[/dim] {entity}")
    console.print(f"  [dim]category:[/dim] {category}")
    console.print(f"  [dim]Credits awarded upon approval[/dim]")


@cli.command("list-categories")
@click.option("--agent", is_flag=True)
def list_categories(agent):
    """List valid categories for reporting."""
    result = api_get("/v1/labels/categories", require_auth=False)
    if agent:
        click.echo(json.dumps(result, indent=2)); return
    for cat in result.get("categories", []):
        console.print(f"  {cat}")


@cli.command("label-add", hidden=True)
@click.option("--address", "-a", required=True)
@click.option("--entity", "-e", required=True)
@click.option("--category", "-c", default="OTHER")
@click.option("--risk", default="MEDIUM")
@click.option("--sanctioned", is_flag=True)
@click.option("--agent", is_flag=True)
def label_add(address, entity, category, risk, sanctioned, agent):
    """Admin: add or update an address label."""
    body = {"address": address, "entity": entity,
            "category": category.upper(), "risk_level": risk.upper(),
            "is_sanctioned": sanctioned}
    result = api_post("/v1/labels/add", body)
    if agent:
        click.echo(json.dumps(result, indent=2)); return
    if "error" in result:
        err_console.print(f"  [red]{result['error']}[/red]"); return
    console.print(f"  [green]Label added[/green]: {entity} ({category})")


@cli.command("label-search")
@click.option("--entity", "-e", default="")
@click.option("--category", "-c", default="")
@click.option("--address", "-a", default="")
@click.option("--agent", is_flag=True)
def label_search(entity, category, address, agent):
    """Search address labels."""
    params = {}
    if entity: params["entity"] = entity
    if category: params["category"] = category
    if address: params["address"] = address
    if not params:
        err_console.print("[red]Provide --entity, --category, or --address[/red]"); return
    result = api_get("/v1/labels/search", params=params)
    output(result, agent, False)


@cli.command("leaderboard")
@click.option("--agent", is_flag=True)
def leaderboard(agent):
    """View community attribution leaderboard."""
    result = api_get("/v1/labels/leaderboard")
    if agent:
        click.echo(json.dumps(result, indent=2)); return
    for r in result.get("leaderboard", []):
        console.print(f"  #{r['rank']} {r.get('approved',0)} approved {r.get('credits_earned',0)} credits")


@cli.command("set-name")
@click.argument("name")
def set_name(name):
    """Set your display name for the leaderboard."""
    result = api_post("/v1/me/name", {"display_name": name})
    if "error" in result:
        err_console.print(f"  [red]{result['error']}[/red]"); return
    console.print(f"  [green]Display name set:[/green] {name}")

def main():
    cli()


if __name__ == "__main__":
    main()
