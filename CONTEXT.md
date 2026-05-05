# BlockINTQL — Agent Context

Blockchain intelligence CLI and API. Screen addresses, trace funds, analyze wallets, search identities.

## Installation

```bash
pip3 install blockintql
blockintql auth --api-key biq_sk_live_...
```

For wallet-backed keyless x402 payments, use Python 3.10+.

## Command Reference

### `verdict` vs `screen`

| Command | Use when | Returns |
|---|---|---|
| `verdict` | Fast CLEAR/CAUTION/BLOCK decision | verdict, safe, risk_score, entity, action |
| `screen` | Counterparty screening with the same base schema | verdict, safe, risk_score, entity, action, plus provider summary and public-safe consensus metadata when local enrichment is used |

```bash
blockintql verdict --address 1A1zP1e... --agent --quiet
blockintql screen --address 1A1zP1e... --agent --quiet
```

## Chain Handling

Defaults to `--chain bitcoin`.

- Pass `--chain ethereum` for `0x...` addresses.
- `ens` always resolves on Ethereum and does not take `--chain`.
- `query` and `analyze` rely on API-side interpretation.

## Auth Behavior

`blockintql` supports two authenticated access paths:

- API key access through `Authorization: Bearer ...`
- Keyless pay-per-request access through the standard x402 buyer flow when wallet-backed payments are configured locally

Prefer environment variables for secrets:

```bash
export BLOCKINTQL_API_KEY=biq_sk_live_...
export BLOCKINTQL_PROVIDER_KEY=...
```

The local config file stores the BlockINTQL API key and optional default provider name with `0600` permissions. It does not persist provider keys or wallet private keys.

## Agent Mode

Always use `--agent --quiet` in pipelines:

```bash
RESULT=$(blockintql screen --address "$ADDR" --chain bitcoin --agent --quiet)
SAFE=$(echo "$RESULT" | jq -r '.safe')
if [ "$SAFE" != "true" ]; then exit 1; fi
```

## Response Schema

```json
{
  "verdict": "CLEAR",
  "safe": true,
  "risk_score": 0,
  "risk_indicators": [],
  "entity": null,
  "action": "No significant risk indicators detected.",
  "chain": "bitcoin",
  "consensus": {
    "enabled": true,
    "mode": "address_screening",
    "decision": "CLEAR",
    "confidence": "high",
    "vote_split": { "block": 0, "review": 0, "clear": 3 }
  }
}
```

- `verdict`: `CLEAR`, `CAUTION`, or `BLOCK`
- `safe`: boolean for payment decisions
- `risk_score`: numeric score from `0` to `100`
- `risk_indicators`: list of flags such as `SANCTIONS`, `MIXER`, `DARKNET`
- `entity`: identified entity name if available
- `consensus`: public-safe decision envelope (no private prompts/weights/heuristics)

## Provider Enrichment

Provider keys stay local. BlockINTQL servers do not receive provider keys or raw provider responses.

```bash
blockintql screen --address 1ABC... --provider chainalysis --provider-key "$KEY" --agent --quiet
blockintql screen --address 0x123... --chain ethereum --provider metasleuth --provider-url "https://your-route/{address}" --agent --quiet
blockintql verdict --address 1ABC... --provider generic --provider-url "https://your-api.com/screen/{address}" --agent --quiet
```

Available providers: `chainalysis`, `trm`, `elliptic`, `metasleuth`, `crystal`, `merkle_science`, `nomis`, `generic`

## Payment Preferences

`blockintql pay` stores local wallet-backed payment settings for keyless pay-per-request access. Paid CLI requests can use these settings when no API key is present.

## MCP Server

```text
https://blockintql-mcp-385334043904.us-central1.run.app/mcp
```

Block6IQ — block6iq.com
