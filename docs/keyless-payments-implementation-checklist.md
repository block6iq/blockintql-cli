# Keyless Payments Implementation Checklist

This checklist translates the keyless pay-per-request readiness criteria into concrete implementation work against the current CLI codepaths.

## Primary Goal

Make paid CLI commands succeed without `BLOCKINTQL_API_KEY` by using locally configured wallet-backed payments and automatic payment challenge handling.

## Current Codepaths

The current implementation work centers on these files:

- [blockintql/cli.py](/Users/block6iq/Documents/Playground/blockintql-cli/blockintql/cli.py)
- [tests/test_cli.py](/Users/block6iq/Documents/Playground/blockintql-cli/tests/test_cli.py)
- [README.md](/Users/block6iq/Documents/Playground/blockintql-cli/README.md)
- [CONTEXT.md](/Users/block6iq/Documents/Playground/blockintql-cli/CONTEXT.md)

Follow-on client surfaces after the CLI rollout:

- [blockintql_python SDK client](/Users/block6iq/Documents/Playground/blockintql-python/blockintql_sdk/client.py)
- [TypeScript SDK](/Users/block6iq/Documents/Playground/blockintql-ts/src/index.ts)
- [LangChain integration](/Users/block6iq/Documents/Playground/blockintql-cli/blockintql/integrations/langchain/tool.py)

## Implementation Checklist

### 1. Add Shared Payment-Aware Transport

Target file:

- [blockintql/cli.py](/Users/block6iq/Documents/Playground/blockintql-cli/blockintql/cli.py)

Tasks:

1. Extract the current raw `httpx.get` and `httpx.post` request logic out of `api_get`, `api_post`, and `api_put` into a shared request helper.
2. Add a transport flow that can send requests without an API key when keyless payment mode is intended.
3. Detect payment challenge responses from paid endpoints.
4. Retry the original request automatically after successful payment authorization.
5. Preserve the current API-key path when an API key is present.

Definition of done:

- `api_get`, `api_post`, and `api_put` all route through one shared payment-aware transport path.

### 2. Load Wallet Payment Configuration At Runtime

Target file:

- [blockintql/cli.py](/Users/block6iq/Documents/Playground/blockintql-cli/blockintql/cli.py)

Tasks:

1. Add a helper to load the existing `config["payment"]` data saved by `blockintql pay`.
2. Validate `wallet_type`, `auto_pay`, and `max_payment_usd` before attempting a paid request.
3. Resolve runtime secrets from environment variables rather than the config file.
4. Return a clear machine-readable error when wallet-backed payment configuration is missing or incomplete.

Definition of done:

- The `pay` command configuration is consumed by runtime request execution instead of existing only as stored preferences.

### 3. Add Wallet Authorization Backends

Target files:

- New payment module under `blockintql/`
- [blockintql/cli.py](/Users/block6iq/Documents/Playground/blockintql-cli/blockintql/cli.py)

Tasks:

1. Add a wallet abstraction that accepts a payment requirement and returns an authorized payment payload.
2. Implement the first wallet backend for `cdp`.
3. Implement the first wallet backend for `privatekey`.
4. Keep wallet-specific code outside the command functions so command handlers stay thin.

Definition of done:

- The CLI can authorize a payment using the configured wallet backend without manual intervention in agent mode.

### 4. Enforce Operator Policy Controls

Target file:

- [blockintql/cli.py](/Users/block6iq/Documents/Playground/blockintql-cli/blockintql/cli.py)

Tasks:

1. Enforce `auto_pay` before any payment authorization call is made.
2. Enforce `max_payment_usd` before any payment authorization call is made.
3. Return clear machine-readable policy errors when payment is declined by local policy.
4. Keep interactive and non-interactive behavior predictable, with agent mode remaining fully machine-readable.

Definition of done:

- The CLI never authorizes payment when local payment policy disallows it.

### 5. Capture And Return Payment Metadata

Target files:

- [blockintql/cli.py](/Users/block6iq/Documents/Playground/blockintql-cli/blockintql/cli.py)
- [tests/test_cli.py](/Users/block6iq/Documents/Playground/blockintql-cli/tests/test_cli.py)

Tasks:

1. Parse payment receipt metadata from successful paid responses.
2. Add a stable `payment` or similarly named object to agent-mode output for paid requests.
3. Include enough metadata for downstream automation to audit what happened.
4. Keep existing result fields intact for current agent consumers.

Definition of done:

- Agent mode returns both the command result and machine-readable payment metadata after a successful paid request.

### 6. Route Initial Paid Commands Through The New Transport

Target file:

- [blockintql/cli.py](/Users/block6iq/Documents/Playground/blockintql-cli/blockintql/cli.py)

Initial command scope:

- `verdict`
- `screen`
- `trace`
- `query`
- `analyze`

Tasks:

1. Update the command handlers above to use the shared payment-aware transport without duplicating payment logic.
2. Confirm the commands still work when an API key is present.
3. Confirm the commands can complete without an API key when wallet-backed payments are configured.

Definition of done:

- The initial paid command set works in both API-key and keyless payment modes.

### 7. Add Automated Test Coverage

Target file:

- [tests/test_cli.py](/Users/block6iq/Documents/Playground/blockintql-cli/tests/test_cli.py)

Tasks:

1. Add a test covering a paid request that succeeds without an API key.
2. Add a test covering automatic retry after a payment challenge.
3. Add a test covering receipt metadata in agent mode.
4. Add a test covering missing wallet configuration.
5. Add a test covering `auto_pay` disabled.
6. Add a test covering `max_payment_usd` exceeded.
7. Add a test covering payment verification failure.
8. Keep existing API-key tests passing.

Suggested test names:

- `test_screen_supports_keyless_payment`
- `test_verdict_supports_keyless_payment`
- `test_agent_mode_returns_payment_metadata`
- `test_auto_pay_policy_is_enforced`
- `test_max_payment_policy_is_enforced`
- `test_missing_wallet_configuration_returns_error`
- `test_payment_verification_failure_returns_error`

Definition of done:

- The keyless payment flow is protected by automated tests, not just manual verification.

### 8. Update Public CLI Documentation After Behavior Is Validated

Target files:

- [README.md](/Users/block6iq/Documents/Playground/blockintql-cli/README.md)
- [CONTEXT.md](/Users/block6iq/Documents/Playground/blockintql-cli/CONTEXT.md)

Tasks:

1. Update setup guidance so wallet-based pay-per-request is documented as a supported path.
2. Replace any wording that implies payment configuration alone is sufficient if runtime authorization is not yet wired in.
3. Add examples showing keyless execution for agent mode.
4. Keep public wording aligned with the validated command behavior.

Definition of done:

- Documentation describes the behavior that the CLI now actually supports.

## Recommended Delivery Order

1. Add the shared payment-aware transport.
2. Load runtime payment configuration and wallet secrets.
3. Implement wallet authorization backends.
4. Enforce operator payment policy.
5. Capture and return payment metadata.
6. Wire `screen` and `verdict`.
7. Add automated tests for the keyless path.
8. Expand the transport to the remaining paid commands.
9. Update README and context docs.
10. Apply the same transport pattern to the SDK and integration surfaces.

## Clean-Machine Validation Command

Use this validation standard before describing the CLI as supporting keyless pay-per-request access:

1. Ensure `BLOCKINTQL_API_KEY` is not set.
2. Configure wallet-backed payment settings locally.
3. Export the required wallet secrets through environment variables.
4. Run a paid CLI command in agent mode.
5. Confirm the CLI completes the request through wallet-backed payment handling.
6. Confirm the output includes both the result and machine-readable payment metadata.

## Release Gate

Do not describe the CLI as supporting keyless pay-per-request access until:

1. The clean-machine validation flow succeeds.
2. The automated tests for the keyless path are in place and passing.
3. The documentation examples match the validated behavior.
