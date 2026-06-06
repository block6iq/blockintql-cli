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

This tool must not be used to facilitate any activity prohibited by applicable law, including sanctions evasion, money laundering, or terrorist financing. You are responsible for ensuring your use complies with all laws and regulations in your jurisdiction.

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

For wallet-backed keyless x402 payments, use Python 3.10+ so the official `x402` buyer SDK can be installed.

From a source checkout:

```bash
pip install .
python3 -m blockintql --help
```

## Update

To get the latest released version:

```bash
pip install --upgrade blockintql
```

To get the absolute latest development version (new features before official release):

```bash
pip install --upgrade git+https://github.com/block6iq/blockintql-cli.git
```

After updating, you can verify with:

```bash
blockintql --version
```

## Quick start (new default experience)

Typing the bare command now launches the interactive chat directly:

```
blockintql
```

You will see the banner, a note that chat is the default, a recommended first prompt, and then the chat prompt (`>`).

Example first prompt that exercises screening + charts:

```
Screen 0x742d35Cc6634C0532925a3b844Bc9e7595f6EEd0 and create a chart for the last 30 days.
```

### Requirements
Chat (and most commands) require either:
- A BlockINTQL API key, or
- Wallet-backed x402 payments (`blockintql login --auto-pay`).

If you see `✗ Invalid API key` inside chat:
- `export BLOCKINTQL_API_KEY=biq_sk_live_...`
- or `blockintql auth --api-key biq_sk_live_...`
- then retry the prompt.

### Local dev testing (free, no credits, full rich panels)
Use the special admin bypass key against a local server (the server must be running with the dev bypass enabled):

```bash
export BLOCKINTQL_API_URL=http://127.0.0.1:8000
export BLOCKINTQL_API_KEY=biq_sk_live_NN_KYJVZ8-yl0HLWO7xjibKfMXnaUxIQ

# Start the local server (see dev instructions or the blockintql repo)
# Then in another shell:
blockintql
# Paste the recommended prompt above. You should get a grounded CAUTION response
# with risk score, citations, and 0 credits charged.
```

See `blockintql --help` for the full Live Now (V1) command list (chat is now the primary entry point).

## Setup

Set your API key with either an environment variable or the local config file:

```bash
export BLOCKINTQL_API_KEY=biq_sk_live_...
blockintql auth --api-key biq_sk_live_...
blockintql status
```

`blockintql auth` stores the BlockINTQL API key and an optional default provider name in `~/.blockintql/config.json` with `0600` permissions. Keep provider keys and wallet secrets in environment variables instead of the config file.

For keyless pay-per-request access, configure wallet-backed payments locally instead of setting an API key.

Run wallet preflight diagnostics before paid commands:

```bash
blockintql wallet doctor --agent
```

If an x402-paid request degrades, BlockINTQL can return a compensation token that can be claimed as API credits:

```bash
blockintql compensation claim --token x402cmp_tok_...
```

If no API key is configured, the CLI now attempts a wallet-signed claim payload automatically (`wallet_claim`) so backend services can redeem compensation using wallet identity instead of API key identity.

## Usage

```bash
# Fast verdict
blockintql verdict --address 1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa

# Full screen result
blockintql screen --address 0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045 --chain ethereum

# Enrich with a local provider call
blockintql screen --address 0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045 \
  --chain ethereum \
  --provider metasleuth \
  --provider-url "https://your-route/{address}"

# Generic provider
blockintql verdict --address 1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa \
  --provider generic \
  --provider-url "https://example.com/screen/{address}"

# Recent investigative history
blockintql history 0xC94eBB328aC25b95DB0E0AA968371885Fa516215 --days 7
blockintql history 0xC94eBB328aC25b95DB0E0AA968371885Fa516215 --days 7 --indexed-only

# Ethereum transaction details
blockintql tx --txid 0x683d6d37a97953d369c7295311158b8aa05c88e2ce207da06947a204b4a70ccd

# Stablecoin wallet intelligence
blockintql stablecoins balances 0xC94eBB328aC25b95DB0E0AA968371885Fa516215
blockintql stablecoins history 0xC94eBB328aC25b95DB0E0AA968371885Fa516215 --days 30
blockintql stablecoins counterparties 0xC94eBB328aC25b95DB0E0AA968371885Fa516215 --days 30

# Interactive compliance-forensics chat
blockintql chat "Assess laundering risk for wallet 0x7F19720A857F834887FC9A7bC0a0fBe7Fc7f8102"

# Create an image artifact
blockintql create image "A cinematic beach at sunset, ultra realistic"

# ENS resolution
blockintql ens vitalik.eth
```

## Launch Scope (Public)

Live Now (V1):

- `auth`, `buy`, `capabilities`, `chat`, `compensation`, `create`, `history`
- `login`, `pay`, `provider`, `providers`, `screen`, `status`
- `stablecoins`, `tx`, `verdict`, `wallet`, `workspace`

Preview commands remain available behind:

```bash
export BLOCKINTQL_ENABLE_EXPERIMENTAL=1
```

Preview command surfaces currently include:
- additional preview command groups shown in `blockintql --help`

## Image Output UX

`blockintql create image` always returns a saved file path for lossless output. In terminals with native image protocols (Kitty/iTerm2/WezTerm), inline rendering can be enabled directly in-terminal. If inline rendering is not supported, open the saved path shown in output.

## Launch-Safe Payment Failover

For wallet-backed runs, you can configure a backup API key used only if an x402 payment attempt fails:

```bash
export BLOCKINTQL_FALLBACK_API_KEY=biq_sk_live_...
```

When enabled, the CLI retries once with API-key credits and annotates the response payment metadata with `authorization_mode=api_key_fallback`.

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

For account verification or workspace automation in scripts:

```bash
blockintql status --agent | jq

blockintql ask "Investigate this wallet's stablecoin counterparties" \
  --address 0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045 \
  --budget-credits 12 \
  --open-workspace \
  --agent | jq
```

## Provider Enrichment

Provider calls are made directly from the CLI on your machine. BlockINTQL receives the address and chain only.

Provider privacy model:

- Provider API keys are used only in direct CLI-to-provider HTTP calls.
- Raw provider responses stay in local process memory and are not sent to BlockINTQL.
- BlockINTQL only receives the native BlockINTQL request payload, such as `address`, `chain`, and optional BlockINTQL-native context.
- The CLI only prints an allowlisted provider summary:
  - `provider`
  - `entity_name`
  - `entity_category`
  - `risk_score`
  - `risk_indicators`
  - `sanctions_hit`
  - `canonical_category`
  - `recommended_verdict`
  - `severity`
  - `confidence`
- You can verify this in the open-source source code:
  - `/blockintql/providers.py`
  - `/blockintql/cli.py`
  - `/tests/test_cli.py`

Provider adjudication model:

- Vendor-native categories are normalized locally into BlockINTQL canonical classes such as `sanctions`, `mixer`, `ransomware`, `darknet`, `scam`, `exchange`, `defi`, `bridge`, and conservative `unknown_*` buckets.
- Direct sanctions hits become local `BLOCK`.
- Mapped elevated-risk categories become local `CAUTION` or `BLOCK` based on deterministic policy.
- Unmapped or proprietary vendor categories do not silently produce `CLEAR`; they degrade to conservative `UNKNOWN` or `CAUTION` policy locally.
- Deterministic consensus output follows `sonar_consensus_v1` and emits named voters (`Sentinel`, `Cypher`, `Nova`) in `consensus.votes`.
- This normalization happens in the CLI before terminal output and without sending vendor payloads to BlockINTQL.
- Canonical deterministic decision contract: [`docs/deterministic-screening-spec-v1.md`](docs/deterministic-screening-spec-v1.md)
- Public Sonar scope at launch: [`docs/sonar-capability-scope-v1.md`](docs/sonar-capability-scope-v1.md)

Available providers:

- `blockintai`
- `chainalysis`
- `trm`
- `elliptic`
- `metasleuth`
- `crystal`
- `merkle_science`
- `nomis`
- `generic`

Provider spec confidence:

- `blockintql provider status` and `blockintql provider test` now include `provider_spec` metadata with `status` and `verification`.
- Treat `provisional` providers as non-production until route/auth/response conformance is confirmed in your tenant.
- Sweep reference: [`docs/provider-spec-sweep.md`](docs/provider-spec-sweep.md)

Examples:

```bash
export BLOCKINTQL_PROVIDER_KEY=...
blockintql screen --address 0x123... --chain ethereum --provider chainalysis

blockintql screen --address 0x123... --chain ethereum --provider metasleuth --provider-url "https://your-route/{address}"

blockintql screen --address 1ABC... \
  --provider generic \
  --provider-url "https://your-api.com/screen/{address}"
```

## Ethereum Investigation Surfaces

BlockINTQL is Ethereum-first for V1 launch screening workflows.

- `blockintql history <address>` returns a recent investigative slice instead of pretending the CLI should dump an unlimited raw ledger.
- High-throughput service wallets can return a condensed triage surface with:
  - wallet classification
  - entity badge when known
  - movement summary
  - lead counterparty
- Additional preview analytics remain available behind `BLOCKINTQL_ENABLE_EXPERIMENTAL=1`.

Example:

```bash
blockintql history 0xC94eBB328aC25b95DB0E0AA968371885Fa516215
blockintql history 0xC94eBB328aC25b95DB0E0AA968371885Fa516215 --days 1
```

## Payment Preferences

`blockintql pay` stores local wallet-backed payment settings for pay-per-request access. When no API key is present, paid CLI requests use the standard x402 buyer flow automatically.

```bash
blockintql pay --wallet-type cdp --auto-pay --max-payment 0.10
```

Use environment variables for any wallet secrets:

```bash
export BLOCKINTQL_CDP_KEY_ID=...
export BLOCKINTQL_CDP_PRIVATE_KEY=...
export BLOCKINTQL_PRIVATE_KEY=...
export EVM_PRIVATE_KEY=...
```

For agent-mode keyless payments, the CLI uses the standard EVM private-key signer path. `BLOCKINTQL_PRIVATE_KEY` and `EVM_PRIVATE_KEY` are both supported.

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

The live MCP surface is investigation-first, not a generic raw data wrapper.

Primary tools:

- `investigate_wallet`
  - returns screening, wallet stats, stablecoin balances, history mode, token lanes, and lead counterparties in one object
- `service_wallet_triage`
  - optimized for exchange, casino, bridge, and other high-throughput wallets
- `explain_decision`
  - explains why a wallet was marked `CLEAR`, `CAUTION`, or `BLOCK`

This works especially well for conversational prompts such as:

```text
Investigate this wallet and summarize the stablecoin risk.
Why did BlockINTQL say block?
Show me a triage view for this hot wallet.
```
