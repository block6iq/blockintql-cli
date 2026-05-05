# Alchemy Fallback Pricing Guardrail

## Goal

If BlockINTQL falls back to Alchemy for Ethereum reads, pricing must always cover:

- direct RPC compute cost
- retry/headroom
- orchestration overhead
- a margin for degraded-mode operations

## Recommended rule

Treat Alchemy as a **premium fallback source**, not the default path.

### Billing policy

- indexed/local Postgres path:
  - normal endpoint pricing
- Alchemy single-address fallback:
  - charge at least `2x` the normal read price
- Alchemy broad trace or expansion fallback:
  - require explicit budget confirmation or a premium tier
- local shell actions:
  - no charge

## Why

Fallback reads are not just another source switch. They introduce:

- external variable cost
- higher latency risk
- retried RPC overhead
- cost spikes on `eth_getLogs`-heavy flows

So the fallback path should be visible and intentionally more expensive.

## Product contract

When fallback is used, surface it in the UI and API:

- `source: alchemy_fallback`
- `fallback: true`
- `estimated_cost_class: premium`

And in the explorer:

- show the fallback source in the `Agent Timeline`
- show the fallback source and charge badge in the drawer/result context

## Suggested default thresholds

- wallet history fallback:
  - allowed
- node drawer evidence fallback:
  - allowed
- single-address transaction lookup:
  - allowed
- wide graph expansion fallback:
  - gated
- network-wide scans on fallback:
  - disallowed by default

## Practical pricing stance

If a normal indexed history call is cheap, the fallback equivalent should not be priced the same.

The safe default is:

- standard indexed read: base credits
- fallback read: `base credits x 2`
- fallback expansion: premium or confirmation-required

This keeps the product honest and protects margins when infrastructure degrades.
