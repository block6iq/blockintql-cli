# BlockINTQL CLI

Sovereign blockchain intelligence from the command line.
Built for AI agents, compliance teams, and developers.

## Install
```bash
pip install blockintql
```

## Setup
```bash
blockintql auth --api-key biq_sk_live_YOUR_KEY
```

Get an API key at [blockintql.com](https://blockintql.com)

## Usage
```bash
# Screen before accepting payment
blockintql screen --address 1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa

# Enrich with your own Chainalysis/TRM key
blockintql screen --address 0x123... --chain ethereum \
  --provider chainalysis --provider-key $KEY

# Natural language intelligence
blockintql query "is this address linked to Lazarus Group?"

# Multi-agent analysis
blockintql analyze "check if these wallets transacted with each other" \
  --address 0x123... --address 0x456...

# OP_RETURN identity search (unique blockchain data)
blockintql profile --identifier @lazarus_trader

# Trace funds FIFO/LIFO
blockintql trace --txid abc123... --hops 5

# List attribution providers
blockintql providers

# Install skills into agent context
blockintql skills --install >> CLAUDE.md
```

## Agent Mode

All commands support `--agent` for machine-readable JSON:
```bash
# Use in AI agent pipelines
RESULT=$(blockintql screen --address $PAYMENT_DEST --agent)
SAFE=$(echo $RESULT | jq -r '.safe')

if [ "$SAFE" = "false" ]; then
  echo "Payment blocked"
  exit 1
fi
```

## x402 Autonomous Payments

Configure once, pay per screen automatically:
```bash
blockintql pay --wallet-type cdp \
  --cdp-key-id $CDP_KEY_ID \
  --cdp-private-key $CDP_PRIVATE_KEY \
  --auto-pay

# Every screen now auto-pays $0.001 USDC on Base
```

## Attribution Providers

Bring your own key — we never see your data:

| Provider | Command |
|---|---|
| Chainalysis | `--provider chainalysis --provider-key $KEY` |
| TRM Labs | `--provider trm --provider-key $KEY` |
| Elliptic | `--provider elliptic --provider-key $KEY` |
| Arkham | `--provider arkham --provider-key $KEY` |
| MetaMask | `--provider metamask` (free, no key needed) |

## MCP Server

For AI agents using MCP (Model Context Protocol):
```
https://blockintql-mcp-385334043904.us-central1.run.app/mcp
```

## Powered By

- Sovereign Bitcoin node (fully synced, 942k+ blocks)
- Sovereign Ethereum node (fully synced, 24M+ blocks)
- 11.6M Bitcoin address clusters
- 53,994+ OP_RETURN identity signals
- 3.35B Ethereum transactions indexed

---

Block6IQ — [block6iq.com](https://block6iq.com)

## Privacy Guarantee

Your attribution provider key never leaves your machine.

Provider API calls (Chainalysis, TRM, Elliptic, etc.) are made **directly 
from the CLI** on your local machine or agent environment. BlockINTQL's 
servers only receive the address being screened — never your provider key, 
never the raw provider response.

You can verify this by reading the source code:
- `blockintql/providers.py` — all provider calls are direct HTTP from CLI
- `blockintql/cli.py` — only address + chain sent to BlockINTQL API

Open source. Verify yourself.
