# BlockINTQL

Blockchain intelligence from the command line. Screen addresses against sanctioned entities and known threat actors, trace fund flows, search Bitcoin OP_RETURN messages, and run AI-powered forensic analysis — from your terminal or your AI agent.
```
pip install blockintql
```

## 30-Second Start
```bash
blockintql init                              # generates API key, saves it locally
blockintql verdict --address 1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa
```

That's it. You get a `CLEAR`, `CAUTION`, or `BLOCK` verdict backed by OFAC sanctions data, pig butchering heuristics, exchange labels, and community-submitted intelligence.
```
  CLEAR  ·  0/100 risk  ·  SAFE

  address  1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa
  chain    bitcoin
  entity   Satoshi Nakamoto (Genesis Block)
```

## Commands

### Intelligence (2 credits)

| Command | What it does |
|---------|-------------|
| `verdict` | Fast CLEAR / CAUTION / BLOCK decision for any address |
| `screen` | Full counterparty screening with sanctions, mixing, darknet flags |
| `ens` | Resolve ENS name to address with risk check |

### Analysis (5–20 credits)

| Command | What it does |
|---------|-------------|
| `analyze` | AI-powered multi-agent forensic analysis |
| `trace` | FIFO/LIFO fund tracing across hops |
| `query` | Natural language — ask anything about an address or transaction |
| `profile` | Search the OP_RETURN identity graph by email, handle, phone, PGP key |

### Community (free)

| Command | What it does |
|---------|-------------|
| `report` | Submit an address label — earn credits when approved |
| `list-categories` | Valid label categories (SANCTIONS, PIG_BUTCHERING, RANSOMWARE, etc.) |
| `leaderboard` | Top community contributors |
| `set-name` | Set your display name on the leaderboard |

### Setup

| Command | What it does |
|---------|-------------|
| `init` | Generate an API key instantly — no email required |
| `auth` | Save an existing API key (reads env var or interactive prompt) |
| `buy` | Purchase credit packs ($10 / 1,000 or $40 / 5,000) |
| `pay` | Configure x402 USDC auto-pay on Base |
| `status` | API health check |
| `providers` | List available attribution providers |
| `capabilities` | Full command reference for agents |

## Agent Mode

Every command supports `--agent` for structured JSON output and `--quiet` to suppress progress text. Pipe to `jq`, feed to your LLM, or embed in CI:
```bash
RESULT=$(blockintql verdict --address $ADDR --chain bitcoin --agent --quiet)
SAFE=$(echo $RESULT | jq -r '.safe')
if [ "$SAFE" != "true" ]; then
  echo "Blocked: $(echo $RESULT | jq -r '.risk_indicators')"
  exit 1
fi
```

### MCP Server

For Claude, Cursor, or any MCP-compatible agent:
```
https://blockintql-mcp-385334043904.us-central1.run.app/mcp
```

### Agent Skill

Dump the skill prompt into your agent's context:
```bash
blockintql capabilities --install >> CONTEXT.md
```

## Provider Enrichment

Combine BlockINTQL's database with your existing Chainalysis, TRM, Elliptic, Crystal, or Merkle Science subscription. The CLI calls your provider directly from your machine — **your provider key never touches BlockINTQL servers**.
```bash
export BLOCKINTQL_PROVIDER_KEY=your_chainalysis_key
blockintql screen --address 0x742d... --chain ethereum --provider chainalysis
```

Both results merge into a single verdict. BlockINTQL sees the address; your provider sees the address + your key. The two never cross.

Available providers: `chainalysis`, `trm`, `elliptic`, `crystal`, `merkle_science`, `nomis`, `generic`

## Privacy Architecture

This CLI is open source so you can verify every claim.

**What stays on your machine:**
- Provider API keys — never sent to BlockINTQL, never logged, never proxied
- Config file (`~/.blockintql/config.json`) — stored with 0600 permissions

**What the BlockINTQL API receives per command:**

| Command | Data sent |
|---------|-----------|
| `verdict` | address, chain, context (if supplied) |
| `screen` | address, chain |
| `analyze` | query text, addresses, chain, output format |
| `profile` | identifier, type |
| `trace` | txid, hops, method |
| `query` | natural-language question |
| `buy` | email |
| `ens` | ENS name |

The narrow claim is: **provider keys never leave your machine**. We don't make broader claims than the code supports. Read `blockintql/cli.py` — it's 550 lines, not a thousand-file monorepo.

## Response Schema

All screening commands return:
```json
{
  "verdict": "CLEAR | CAUTION | BLOCK",
  "safe": true,
  "risk_score": 0,
  "chain": "bitcoin",
  "entity": "Coinbase",
  "risk_indicators": [],
  "narrative": "..."
}
```

`screen` adds: `sanctions_hit`, `mixing_detected`, `darknet_exposure`, `exchange_identified`

Risk score semantics: 0–30 low, 30–70 medium, 70+ high. `>= 70` should block in automated pipelines.

## Chain Handling

Defaults to `--chain bitcoin`. Pass `--chain ethereum` for `0x` addresses.

Commands that auto-detect chain: `ens` (always Ethereum), `query` (inferred), `analyze` (defaults Ethereum).

## Auth
```bash
# Option 1: env var (recommended — avoids shell history)
export BLOCKINTQL_API_KEY=biq_sk_live_...

# Option 2: interactive prompt
blockintql auth

# Option 3: generate a new key
blockintql init
```

Auth precedence: API key → x402 auto-pay → free tier (10/day).

## Development
```bash
git clone https://github.com/block6iq/blockintql-cli.git
cd blockintql-cli
pip install -e .
pytest tests/ -v
```

The test suite includes privacy invariant tests that assert provider keys never appear in any request to the BlockINTQL API — headers, body, params, or URL. These run on every command that supports provider enrichment.

## Links

- **API docs**: [blockintql.com](https://blockintql.com)
- **MCP server**: `https://blockintql-mcp-385334043904.us-central1.run.app/mcp`
- **PyPI**: [pypi.org/project/blockintql](https://pypi.org/project/blockintql/)
- **Report an address**: `blockintql report` (free, earn credits)
- **Block6IQ**: [block6iq.com](https://block6iq.com)

## License

MIT
