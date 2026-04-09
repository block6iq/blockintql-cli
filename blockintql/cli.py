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


def api_get(path, params=None, require_auth=True):
    try:
        headers = get_headers() if require_auth else {"Content-Type": "application/json"}
        r = httpx.get(f"{API_BASE}{path}", headers=headers, params=params, timeout=30)
        r.raise_for_status()
        return r.json()
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
        headers = get_headers() if require_auth else {"Content-Type": "application/json"}
        r = httpx.post(f"{API_BASE}{path}", headers=headers, json=body, timeout=60)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}


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


def output(data, agent, quiet):
    if agent or not sys.stdout.isatty():
        click.echo(json.dumps(data, indent=2, default=str))
        return
    if "error" in data:
        err_console.print(f"  [red]✗[/red] {data['error']}")
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
        console.print("  [bold]INTELLIGENCE[/bold]  [dim](2 credits)[/dim]")
        console.print("    verdict           Screen address — CLEAR / CAUTION / BLOCK")
        console.print("    screen            Full risk screening with narrative")
        console.print("    profile           Identity profile lookup")
        console.print("    trace             Follow transaction hops")
        console.print()
        console.print("  [bold]ANALYSIS[/bold]  [dim](5-20 credits)[/dim]")
        console.print("    analyze           AI-powered address analysis")
        console.print("    query             Natural language blockchain query")
        console.print("    capabilities      List supported CLI capabilities")
        console.print()
        console.print("  [bold]DATA[/bold]  [dim](1 credit)[/dim]")
        console.print("    providers         List enrichment providers")
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


@cli.command()
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


@cli.command()
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

    commands = {
        "setup": [
            {"cmd": "init", "desc": "Generate API key", "credits": "Free"},
            {"cmd": "auth", "desc": "Save existing API key", "credits": "Free"},
            {"cmd": "buy", "desc": "Purchase credits via Stripe", "credits": "Free"},
            {"cmd": "pay", "desc": "Configure local x402 payment preferences", "credits": "Free"},
            {"cmd": "status", "desc": "Check account info and credits", "credits": "1"},
        ],
        "intelligence": [
            {"cmd": "verdict", "desc": "Address risk verdict (CLEAR/CAUTION/BLOCK)", "credits": "2"},
            {"cmd": "screen", "desc": "Full counterparty screening with flags", "credits": "2"},
            {"cmd": "profile", "desc": "OP_RETURN identity search", "credits": "1"},
            {"cmd": "trace", "desc": "Fund tracing with FIFO/LIFO", "credits": "2"},
        ],
        "analysis": [
            {"cmd": "analyze", "desc": "5-agent AI forensic analysis", "credits": "10"},
            {"cmd": "query", "desc": "Natural language blockchain query", "credits": "10"},
            {"cmd": "capabilities", "desc": "List supported CLI capabilities", "credits": "Free"},
        ],
        "data": [
            {"cmd": "providers", "desc": "List local enrichment providers", "credits": "Free"},
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
    qs = "&".join(f"{k}={v}" for k,v in params.items())
    result = api_get(f"/v1/labels/search?{qs}")
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
