# BlockINTQL CLI Public Update: V1 Scope Clarity

Today we tightened the public V1 scope in the CLI so command discovery and runtime behavior are fully aligned.

## What’s Live Now (V1)

- `auth`
- `buy`
- `capabilities`
- `chat`
- `compensation`
- `history`
- `login`
- `pay`
- `provider`
- `providers`
- `screen`
- `status`
- `verdict`
- `wallet`

## What’s in Preview

Preview commands remain available behind:

```bash
export BLOCKINTQL_ENABLE_EXPERIMENTAL=1
```

This includes deeper and expanded workflows such as:

- `create`
- `stablecoins`
- `tx`
- `workspace`
- and other preview command groups

## Why this update matters

- Clearer first-run experience for new users
- Stronger trust in command-level launch status
- Cleaner handoff for teams building production workflows on top of the CLI

## Notes for builders

- Provider keys continue to remain local to your machine
- `--agent` output remains available for automation and pipeline usage
- `capabilities` now reflects launch-ready scope by default
- Provider names in public CLI scope are:
  - `chainalysis`
  - `trm`
  - `elliptic`
  - `metasleuth`
  - `crystal`
  - `merkle_science`
  - `nomis`
  - `generic`
