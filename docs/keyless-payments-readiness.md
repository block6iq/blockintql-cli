# Keyless Payments Readiness

The CLI supports keyless pay-per-request access when an operator can configure a wallet locally and successfully complete a paid request without providing an API key.

## Scope

This document defines the rollout criteria for wallet-based pay-per-request access in the CLI.

In scope:

- Wallet-backed payment configuration
- Payment-aware HTTP transport for paid API requests
- Automatic payment challenge handling and retry
- Machine-readable receipt handling in agent mode
- Operator policy controls for auto-pay and spend limits
- Test coverage and release readiness criteria

Out of scope:

- Marketing copy
- Hosted workspace session design
- Non-CLI clients unless explicitly included in the rollout plan

## Acceptance Criteria

The feature is considered ready when all of the following are true:

1. An operator can configure wallet-backed payments locally without storing sensitive private key material in the config file.
2. A paid CLI command can complete successfully without `BLOCKINTQL_API_KEY` being set.
3. The CLI can make an initial unauthenticated request to a paid endpoint and detect a payment challenge response.
4. The CLI can authorize the required payment using the configured wallet and retry the request automatically.
5. The retried request succeeds and returns the requested data without requiring signup or API-key setup.
6. Agent mode returns machine-readable payment metadata for successful paid requests.
7. Auto-pay settings and maximum payment limits are enforced before a payment is authorized.
8. When payment cannot proceed, the CLI returns a clear machine-readable error explaining the reason.

## Required User Flows

The following flows must succeed before release:

1. Configure wallet-backed payments locally.
2. Run `blockintql screen --address ... --agent` with no API key present.
3. Complete the paid request through the wallet-backed payment flow.
4. Return the screening result plus payment metadata in agent mode.

The following policy flows must also be validated:

1. Auto-pay disabled: the CLI does not authorize payment automatically.
2. Max payment exceeded: the CLI declines the payment before authorization.
3. Wallet not configured: the CLI returns a clear setup error.
4. Payment verification failure: the CLI returns a clear payment failure error.

## Milestones

### 1. Payment-Aware Transport

- Add a shared HTTP transport for CLI API requests.
- Support unauthenticated requests for paid endpoints.
- Detect payment challenge responses and route them through the payment flow.
- Retry the original request after successful payment authorization.

### 2. Wallet Integration

- Load wallet-backed payment settings from local CLI configuration.
- Support the initial wallet backends selected for rollout.
- Keep sensitive wallet secrets in environment variables instead of the config file.
- Validate operator configuration before paid requests are attempted.

### 3. Operator Policy Controls

- Enforce `auto_pay` before authorizing payment.
- Enforce `max_payment_usd` before authorizing payment.
- Return clear machine-readable errors when policy blocks payment.
- Surface payment outcome details in agent mode.

### 4. Command Integration

- Route paid commands through the payment-aware transport.
- Preserve existing API-key behavior when an API key is present.
- Ensure keyless behavior works for the initial rollout commands.

### 5. Receipt Handling

- Capture payment receipt metadata from successful paid requests.
- Return payment metadata in `--agent` output.
- Preserve a consistent response shape for downstream agent consumers.

### 6. Documentation And Release Readiness

- Update public CLI documentation to describe wallet-based pay-per-request setup.
- Keep examples aligned with validated command behavior.
- Only describe keyless pay-per-request access after acceptance criteria and tests pass.

## Test Coverage

The rollout should include automated coverage for the following cases:

1. Paid request succeeds without an API key when wallet-backed payments are configured.
2. Payment challenge is detected and retried automatically.
3. Agent mode includes payment metadata after a successful paid request.
4. Auto-pay disabled returns a policy error instead of authorizing payment.
5. Max payment exceeded returns a policy error instead of authorizing payment.
6. Missing wallet configuration returns a setup error.
7. Payment verification failure returns a payment error.
8. Existing API-key flows continue to work unchanged.

Recommended test names:

- `test_screen_supports_keyless_payment`
- `test_verdict_supports_keyless_payment`
- `test_agent_mode_returns_payment_metadata`
- `test_auto_pay_policy_is_enforced`
- `test_max_payment_policy_is_enforced`
- `test_missing_wallet_configuration_returns_error`
- `test_payment_verification_failure_returns_error`

## Release Readiness

The feature is ready to describe as keyless pay-per-request access when:

1. The required user flows pass on a clean machine with no API key configured.
2. The automated tests listed above are in place and passing.
3. The CLI documentation reflects the validated setup and runtime behavior.
4. Agent mode returns stable machine-readable output for successful and unsuccessful payment flows.

## Clean-Machine Validation

Use the following validation standard before release:

1. Start from an environment with no `BLOCKINTQL_API_KEY`.
2. Configure wallet-backed payment settings locally.
3. Set any required wallet secrets through environment variables.
4. Run a paid CLI command in agent mode.
5. Confirm the CLI completes the request through the wallet-backed payment flow.
6. Confirm the output includes both the requested data and payment metadata.

When this validation passes together with the automated test coverage above, the CLI is ready to present as supporting keyless pay-per-request access.
