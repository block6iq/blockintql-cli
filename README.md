# BlockINTQL CLI

Sovereign blockchain intelligence from the command line.
Built for AI agents, compliance teams, and developers.

## Install

    pip install blockintql

## Setup

    blockintql auth --api-key biq_sk_live_YOUR_KEY

Get an API key at blockintql.com

## Usage

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

    # OP_RETURN identity search
    blockintql profile --identifier @lazarus_trader

    # Trace funds FIFO/LIFO
    blockintql trace --txid abc123... --hops 5

    # List attribution providers
    blockintql providers

    # Install skills into agent context
    blockintql skills --install >> CLAUDE.md

## Agent Mode

All commands support --agent for machine-readable JSON:

    RESULT=$(blockintql screen --address $PAYMENT_DEST --agent)
    SAFE=$(echo $RESULT | jq -r '.safe')

    if [ "$SAFE" = "false" ]; then
      echo "Payment blocked"
      exit 1
    fi

## x402 Autonomous Payments

Configure once, pay per screen automatically:

    blockintql pay --wallet-type cdp \
      --cdp-key-id $CDP_KEY_ID \
      --cdp-private-key $CDP_PRIVATE_KEY \
      --auto-pay

Every screen auto-pays $0.001 USDC on Base to:
0x32984663A11b9d7634Bf35835AE32B5A031637D5

## Attribution Providers

Bring your own key — we never see your data:

  chainalysis   --provider chainalysis --provider-key $KEY
  trm           --provider trm --provider-key $KEY
  elliptic      --provider elliptic --provider-key $KEY
  arkham        --provider arkham --provider-key $KEY
  metamask      --provider metamask (free, no key needed)
  generic       --provider generic --provider-url https://your-api.com/screen/{address}

## Privacy Guarantee

Your attribution provider key never leaves your machine.

Provider API calls are made directly from the CLI on your local machine.
BlockINTQL servers only receive the address being screened — never your
provider key, never the raw provider response.

Verify this by reading the source:
  blockintql/providers.py — all provider calls are direct HTTP from CLI
  blockintql/cli.py — only address + chain sent to BlockINTQL API

Open source. Verify yourself: github.com/block6iq/blockintql-cli

## MCP Server

For AI agents using MCP (Model Context Protocol):

    https://blockintql-mcp-385334043904.us-central1.run.app/mcp

## Powered By

- Sovereign Bitcoin node — fully synced, 942,000+ blocks
- Sovereign Ethereum node — fully synced, 24,000,000+ blocks  
- 50,000+ OP_RETURN identity signals mined from the Bitcoin blockchain
- BlockINTAI — autonomous multi-agent analytics engine
- BlockINTQL — sovereign blockchain query language

Block6IQ — block6iq.com

## Troubleshooting

### "blockintql: command not found" on Mac

Add Python's bin directory to your PATH:

    echo 'export PATH="$PATH:/Users/$(whoami)/Library/Python/3.9/bin"' >> ~/.zshrc
    source ~/.zshrc

Or use python3 directly:

    python3 -m blockintql --help

### Use pip3 instead of pip on Mac

    pip3 install blockintql
