# BlockINTQL CLI

Blockchain intelligence CLI for screening addresses, tracing funds, searching identities, and calling the BlockINTQL API from scripts or agents.

## Disclaimer

Read this before using BlockINTQL in compliance workflows, with autonomous AI agents, or in any context where outputs may inform a financial, legal, or regulatory decision. Full payment terms, governing law, indemnification, and acceptable use restrictions are set out in the BlockINTQL Terms of Service at [blockintql.com/terms](https://blockintql.com/terms). By using this software you agree to those Terms.

### 1. No Legal or Compliance Advice

BlockINTQL outputs, including CLEAR, CAUTION, and BLOCK verdicts, risk scores, transaction traces, and forensic analysis, are algorithmically generated risk indicators. They are not legal advice, compliance determinations, or regulatory guidance. They do not represent that any address or counterparty is free from sanctions exposure or illicit association. You are solely responsible for all decisions made using this tool's outputs.

### 2. CLEAR Verdicts Are Not Guarantees

CLEAR means no adverse indicators were found in Block6IQ's database at the time of query. It does not mean an address is safe or sanctions-free. Other databases may contain adverse data not present in Block6IQ's dataset. Independent verification against current, authoritative government sources is required for any regulated use case.

### 3. Regulatory Disclaimer

Block6IQ is a software and data provider, not a registered compliance service, licensed money services business, or substitute for a qualified compliance officer. Use of this tool does not satisfy any obligation to conduct sanctions screening, AML due diligence, KYC verification, or any other regulated compliance function.

This tool is not intended for use by individuals or entities subject to comprehensive OFAC sanctions programs, or for use in any activity prohibited by applicable law. You are responsible for ensuring your use complies with all laws in your jurisdiction.

### 4. Autonomous AI Agents

Certain features are designed for use by autonomous AI agents. Agents act without human review. Block6IQ does not monitor or control decisions made by autonomous agents acting on BlockINTQL outputs. Operators are solely responsible for ensuring appropriate human oversight and accountability for any compliance or transactional decisions made by those agents.

AI-generated outputs may contain errors. Commands using AI-powered analysis produce LLM-generated outputs that may contain factual errors or inaccuracies. They are not reviewed by a human before delivery. Regulatory obligations remain with the operator. Deploying BlockINTQL in an agentic workflow does not satisfy any obligation that would otherwise require human review, professional judgment, or a licensed compliance function.

### 5. Third-Party Provider Integrations

The Service supports optional integration with third-party blockchain analytics providers. If you configure a provider key, the CLI queries that provider directly from your machine. Your provider API key is never transmitted to Block6IQ servers. It is your sole responsibility to confirm that your use of any provider's API via the Service is permitted under your agreement with that provider.

### 6. Open Source Scope

The MIT License applies solely to the CLI client software in this repository. It does not extend to the Block6IQ API, intelligence database, risk models, or the BlockINTQL query language and architecture, which are proprietary. Use of the API is governed by the Block6IQ Terms of Service at [blockintql.com/terms](https://blockintql.com/terms).

### 7. No Warranty; Liability Cap

THE CLI IS PROVIDED "AS IS" WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED. BLOCK6IQ ASSUMES NO LIABILITY OR RESPONSIBILITY FOR ANY ERRORS, MISTAKES, INACCURACIES, OR OMISSIONS IN ANY OUTPUT OF THIS TOOL.

TO THE MAXIMUM EXTENT PERMITTED BY LAW, BLOCK6IQ'S TOTAL LIABILITY ARISING FROM YOUR USE OF THIS TOOL SHALL NOT EXCEED THE AMOUNTS PAID BY YOU TO BLOCK6IQ IN THE PRECEDING 12 MONTHS. BLOCK6IQ IS NOT LIABLE FOR ANY INDIRECT, INCIDENTAL, CONSEQUENTIAL, OR PUNITIVE DAMAGES ARISING FROM RELIANCE ON THIS TOOL.

### 8. Data and Privacy

Provider API keys never leave your machine. When using the x402 USDC payment path, your payment wallet address is permanently visible on the Base blockchain. Block6IQ does not control on-chain data visibility. Email addresses are collected only if voluntarily provided during a Stripe credit purchase. See the Block6IQ Privacy Policy at [blockintql.com/privacy](https://blockintql.com/privacy).

### 9. Acceptance

By installing, downloading, or running BlockINTQL, you confirm you have read this disclaimer and agree to the Block6IQ Terms of Service at [blockintql.com/terms](https://blockintql.com/terms). If you do not agree, do not use this software.

## Install

```bash
pip install blockintql
```

From a source checkout:

```bash
pip install .
python3 -m blockintql --help
```

## Setup

Set your API key with either an environment variable or the local config file:

```bash
export BLOCKINTQL_API_KEY=biq_sk_live_...
blockintql auth --api-key biq_sk_live_...
```

`blockintql auth` stores the BlockINTQL API key and an optional default provider name in `~/.blockintql/config.json` with `0600` permissions. Keep provider keys and wallet secrets in environment variables instead of the config file.

## Usage

```bash
# Fast verdict
blockintql verdict --address 1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa

# Full screen result
blockintql screen --address 0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045 --chain ethereum

# Enrich with a local provider call
blockintql screen --address 0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045 \
  --chain ethereum \
  --provider metamask

# Generic provider
blockintql verdict --address 1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa \
  --provider generic \
  --provider-url "https://example.com/screen/{address}"

# Natural language intelligence
blockintql query "is this address linked to Lazarus Group?"

# Multi-address analysis
blockintql analyze "check if these wallets transacted with each other" \
  --address 0x123... \
  --address 0x456...

# Identity search
blockintql profile --identifier @lazarus_trader

# Transaction tracing
blockintql trace --txid abc123... --hops 5

# ENS resolution
blockintql ens vitalik.eth
```

## Agent Mode

Use `--agent --quiet` for machine-readable output in pipelines:

```bash
RESULT=$(blockintql screen --address "$PAYMENT_DEST" --chain bitcoin --agent --quiet)
SAFE=$(echo "$RESULT" | jq -r '.safe')

if [ "$SAFE" = "false" ]; then
  echo "Payment blocked"
  exit 1
fi
```

## Provider Enrichment

Provider calls are made directly from the CLI on your machine. BlockINTQL receives the address and chain only.

Available providers:

- `chainalysis`
- `trm`
- `elliptic`
- `arkham`
- `metamask`
- `generic`

Examples:

```bash
export BLOCKINTQL_PROVIDER_KEY=...
blockintql screen --address 0x123... --chain ethereum --provider chainalysis

blockintql screen --address 0x123... --chain ethereum --provider metamask

blockintql screen --address 1ABC... \
  --provider generic \
  --provider-url "https://your-api.com/screen/{address}"
```

## Payment Preferences

`blockintql pay` stores local billing preferences only. It does not execute wallet payments by itself in this repository.

```bash
blockintql pay --wallet-type cdp --auto-pay --max-payment 0.10
```

Use environment variables for any wallet secrets:

```bash
export BLOCKINTQL_CDP_KEY_ID=...
export BLOCKINTQL_CDP_PRIVATE_KEY=...
export BLOCKINTQL_PRIVATE_KEY=...
```

## LangChain

```python
from blockintql.integrations.langchain import BlockINTQLTools

tools = BlockINTQLTools(api_key="biq_sk_live_...").get_tools()
```

## JavaScript

The JavaScript integration exports the SDK from `integrations/javascript/src/index.js`. This repository does not currently ship a standalone JavaScript CLI binary.

## MCP Server

For Model Context Protocol clients:

```text
https://blockintql-mcp-385334043904.us-central1.run.app/mcp
```
