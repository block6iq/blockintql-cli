# Credits and Payments Flow

## Goal

BlockINTQL should support both:

- agents paying in real time with a USDC wallet
- humans using a simple prepaid credit flow

The payment model should feel unified even if the underlying mechanisms differ.

## Recommended product model

### Agents

Agents should default to:

- x402 / USDC wallet payment
- real-time per-request charging
- optional max-payment guardrails
- no manual credit top-up required

Examples:

```bash
blockintql login --auto-pay --max-payment 0.10
```

This is the right model for:

- autonomous agents
- wallet-native automation
- pay-per-request services on agentic marketplaces

### Humans

Humans should default to:

- prepaid credits attached to an API key
- top-up through a simple checkout flow
- visible balance in CLI and UI
- optional wallet-based auto-pay for power users

Examples:

```bash
blockintql buy --pack starter
blockintql status
```

This is the right model for:

- analysts
- operators
- buyers who want predictable spend
- people who do not want to think about wallet signatures for every action

## Unified UX principle

The user should not have to care about the internal payment rail during normal use.

They should only understand:

1. how much a command costs
2. whether they have enough balance or wallet allowance
3. whether they were charged
4. whether they were refunded

## Recommended CLI behavior

### For human/API-key users

- if credits are available:
  - run immediately
- if credits are low:
  - warn before execution
- if credits are exhausted:
  - offer checkout
  - do not fail with confusing payment internals

Recommended flow:

```bash
blockintql history --address 0x...
```

If no credits:

```text
This command costs 1 credit.
Your current balance is 0.
Run next:
  blockintql buy --pack starter
```

### For wallet/agent users

- if wallet auto-pay is configured:
  - charge live
- if the charge exceeds guardrails:
  - block and explain

## Refund rule

Users should not be charged for:

- degraded results
- infrastructure failures
- empty results where the paid contract promised data and none could be delivered

The refund should be:

- automatic
- visible
- attached to the response

Recommended response fields:

- `charged`
- `refunded`
- `refund_reason`
- `payment_mode`

## Best product split

### Default human path

- API key
- prepaid credits
- checkout top-up

### Default agent path

- wallet
- x402 auto-pay
- per-request charging

### Optional hybrid path

Humans can opt into wallet mode if they want:

- `blockintql login --auto-pay`

This should be optional, not required.

## Why this is the right flow

It keeps the product aligned with the agent economy while still being easy for normal users.

In short:

- agents = live wallet payments
- humans = prepaid credits
- both = same command surface
