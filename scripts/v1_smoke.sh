#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" == "" ]]; then
  echo "Usage: $0 <address>"
  echo "Example: $0 0x7F19720A857F834887FC9A7bC0a0fBe7Fc7f8102"
  exit 1
fi

ADDRESS="$1"
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

run_json() {
  local name="$1"
  shift
  echo "==> $name"
  "$@" --agent > "$TMPDIR/$name.json"
  cat "$TMPDIR/$name.json"
  echo
}

run_json wallet_status blockintql wallet status
run_json wallet_doctor blockintql wallet doctor
run_json verdict blockintql verdict --address "$ADDRESS"
run_json history_primary blockintql history --address "$ADDRESS" --days 30 --limit 50
run_json history_network blockintql history --address "$ADDRESS" --days 30 --limit 50 --allow-network-read

python3 - <<'PY' "$TMPDIR"
import json, pathlib, sys
root = pathlib.Path(sys.argv[1])

def read(name):
    return json.loads((root / f"{name}.json").read_text())

checks = []
wallet = read("wallet_status")
doctor = read("wallet_doctor")
verdict = read("verdict")
hist_primary = read("history_primary")
hist_network = read("history_network")

checks.append(("wallet_ready", bool(wallet.get("ready"))))
checks.append(("doctor_ready", bool(doctor.get("ready"))))
checks.append(("verdict_has_decision", bool(verdict.get("verdict"))))
checks.append(("history_primary_not_fallback", hist_primary.get("source") != "live_network_read"))
checks.append(("history_network_attempted", bool(hist_network.get("source"))))

failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(f"{name}: {'PASS' if ok else 'FAIL'}")

if failed:
    print("\nSmoke check failed:", ", ".join(failed))
    sys.exit(2)
print("\nSmoke check passed.")
PY
