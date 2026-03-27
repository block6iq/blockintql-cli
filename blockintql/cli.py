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
import click
import httpx
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box
from .providers import get_provider, list_providers

API_BASE = os.environ.get("BLOCKINTQL_API_URL", "https://btc-index-api-385334043904.us-central1.run.app")
CONFIG_FILE = os.path.expanduser("~/.blockintql/config.json")
console = Console()
err_console = Console(stderr=True)

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f: return json.load(f)
    return {}

def save_config(config):
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, "w") as f: json.dump(config, f, indent=2)

def get_api_key():
    return os.environ.get("BLOCKINTQL_API_KEY") or load_config().get("api_key")

def get_headers():
    key = get_api_key()
    if not key:
        err_console.print("[red]No API key.[/] Run: blockintql auth --api-key YOUR_KEY")
        sys.exit(1)
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

def api_get(path, params=None):
    """Query BlockINTQL API — sends address+chain ONLY, never provider keys."""
    try:
        r = httpx.get(f"{API_BASE}{path}", headers=get_headers(), params=params, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}

def api_post(path, body):
    """Query BlockINTQL API — sends address+chain ONLY, never provider keys."""
    try:
        r = httpx.post(f"{API_BASE}{path}", headers=get_headers(), json=body, timeout=60)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}

def enrich_with_provider(result, address, chain, provider_name, provider_key):
    """
    PRIVACY: Runs entirely on your local machine.
    Calls provider API directly — key never sent to BlockINTQL.
    Only the merged verdict (no raw provider data) is shown to user.
    """
    if not provider_name or not provider_key:
        return result
    provider = get_provider(provider_name, provider_key)
    if not provider:
        err_console.print(f"[yellow]Unknown provider: {provider_name}[/]")
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

        VERDICT_ART = {
            "CLEAR":   "█▀▀ █   █▀▀ ▄▀█ █▀█",
            "CAUTION": "█▀▀ ▄▀█ █ █ ▀█▀ █ █ █▄",
            "BLOCK":   "█▄▄ █▄▄ █▄█ █▄▀ █▄▀",
        }

        console.print()
        console.print(f"  [bold {color}]{VERDICT_ART.get(v, v)}[/bold {color}]")
        console.print(f"  [bold {color}]{v}[/bold {color}]  [dim]·[/dim]  [{color}]{risk}/100 risk[/{color}]  [dim]·[/dim]  [dim]{'SAFE' if safe else 'DO NOT TRANSACT'}[/dim]")
        console.print(f"  [dim]{'─' * 52}[/dim]")

        if not quiet:
            console.print(f"  [dim]address [/dim] {data.get('address','')}")
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

    if not quiet:
        console.print_json(json.dumps(data, default=str))


def with_provider(f):
    for opt in reversed(provider_opts): f = opt(f)
    return f

@click.group()
@click.version_option("1.0.0", prog_name="blockintql")
def cli():
    """BlockINTQL — Sovereign Blockchain Intelligence CLI

    Your provider key never leaves your machine.
    BlockINTQL only receives the address being screened.
    """
    pass

@cli.command()
@click.option("--api-key", required=True)
@click.option("--provider", default=None)
@click.option("--provider-key", default=None)
def auth(api_key, provider, provider_key):
    """Save API key and optional default provider."""
    config = load_config()
    config["api_key"] = api_key
    if provider: config["default_provider"] = provider
    if provider_key: config["default_provider_key"] = provider_key
    save_config(config)
    console.print("[green]✅ Saved.[/]")

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
    provider_key = provider_key or config.get("default_provider_key")
    if not quiet and not agent:
        p_info = f" + {provider} (local)" if provider else ""
        console.print(f"[dim]Screening {address[:20]}...{p_info}[/]")

    # STEP 1: BlockINTQL gets address+chain ONLY
    result = api_post("/v1/verdict", {"address": address, "chain": chain, "context": context})

    # STEP 2: Provider called directly from YOUR machine — key never sent to BlockINTQL
    if provider and provider_key and "error" not in result:
        result = enrich_with_provider(result, address, chain, provider, provider_key)

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
    provider_key = provider_key or config.get("default_provider_key")
    if not quiet and not agent:
        p_info = f" + {provider} (local)" if provider else ""
        console.print(f"[dim]Screening {address[:20]}...{p_info}[/]")

    # STEP 1: BlockINTQL gets address+chain ONLY
    result = api_post("/v1/screen", {"address": address, "chain": chain})

    # STEP 2: Provider called directly from YOUR machine — key never sent to BlockINTQL
    if provider and provider_key and "error" not in result:
        result = enrich_with_provider(result, address, chain, provider, provider_key)

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
            "commands": ["verdict","screen","analyze","profile","trace","query","providers"],
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
        ("providers","List providers","blockintql providers"),
        ("skills","Agent skills","blockintql skills --install >> CLAUDE.md"),
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
    """Configure x402 auto-payment — $0.001 USDC per screen on Base."""
    config = load_config()
    payment_config = {"type": wallet_type, "auto_pay": auto_pay, "max_payment_usd": max_payment}
    if wallet_type == "cdp":
        if not cdp_key_id or not cdp_private_key:
            err_console.print("[red]CDP requires --cdp-key-id and --cdp-private-key[/]")
            return
        payment_config.update({"cdp_key_id": cdp_key_id, "cdp_private_key": cdp_private_key})
    elif wallet_type == "privatekey":
        if not private_key:
            err_console.print("[red]Requires --private-key[/]")
            return
        payment_config["private_key"] = private_key
    config["payment"] = payment_config
    save_config(config)
    console.print(f"[green]✅ Payment wallet configured ({wallet_type})[/]")
    console.print(f"[green]✅ Auto-pay: {'enabled' if auto_pay else 'disabled'} | Max: ${max_payment}[/]")
    console.print(f"[dim]Payments → 0x32984663A11b9d7634Bf35835AE32B5A031637D5 (Base)[/]")

@cli.command()
@click.option("--agent", is_flag=True)
def status(agent):
    """Check node health."""
    output(api_get("/health"), agent, False)

def main():
    cli()

if __name__ == "__main__":
    main()
