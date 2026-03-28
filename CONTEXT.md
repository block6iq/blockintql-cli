# BlockINTQL — Agent Context

Blockchain intelligence CLI and API. Screen addresses, trace funds, analyze wallets, search identities.

## Installation
```bash
pip3 install blockintql
blockintql auth --api-key biq_sk_live_...
```

---

## Command Reference

### `verdict` vs `screen`

| Command | Use when | Returns |
|---|---|---|
| `verdict` | Fast CLEAR/CAUTION/BLOCK decision | verdict, safe, risk_score, entity, action |
| `screen` | Full counterparty detail before transacting | All verdict fields + sanctions_hit, mixing_detected, darknet_exposure, exchange_identified |
```bash
blockintql verdict --address 1A1zP1e... --agent
blockintql screen --address 1A1zP1e... --agent
```

---

## Chain Handling

Defaults to `--chain bitcoin`. Always pass `--chain ethereum` for `0x...` addresses.

Commands that infer chain internally — no `--chain` needed:
- `ens` — always Ethereum
- `query` — inferred from context
- `analyze` — defaults to ethereum

Commands requiring explicit `--chain ethereum` for ETH addresses:
- `verdict`, `screen`, `trace`, `profile`

---

## Auth Precedence

1. API key — checked first, x402 not triggered if valid
2. x402 auto-pay — only when no API key present, $0.01 USDC per request on Base
3. Free tier — 10 requests/day per IP, no key or wallet configured

If both API key and x402 configured, API key wins. x402 not charged.

---

## Agent Mode

Always use `--agent --quiet` in pipelines:
```bash
RESULT=$(blockintql screen --address $ADDR --chain bitcoin --agent --quiet)
SAFE=$(echo $RESULT | jq -r '.safe')
if [ "$SAFE" != "true" ]; then exit 1; fi
```

---

## Response Schema

verdict: "CLEAR" | "CAUTION" | "BLOCK"
safe: true | false
risk_score: integer or float, 0-100. Treat >= 70 as high risk.
risk_indicators: ["SANCTIONS", "MIXER", "DARKNET", "EXCHANGE"]
entity: string or null
screen adds: sanctions_hit, mixing_detected, darknet_exposure, exchange_identified

---

## MCP Server

https://blockintql-mcp-385334043904.us-central1.run.app/mcp

---

## Provider Enrichment (CLI only)

Provider keys called directly from CLI — never sent to BlockINTQL servers:
```bash
blockintql screen --address 1ABC... --provider chainalysis --provider-key $KEY --agent
```

Available: chainalysis, trm, elliptic, arkham, generic

---

Block6IQ — block6iq.com
