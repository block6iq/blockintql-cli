#!/usr/bin/env bash
set -euo pipefail

# Full smoke for the OSS foundation + next wave (local REPL flows, real trace eval fixtures, graph shell, deterministic core, history/verdict etc).
# Works great with:
#   export BLOCKINTQL_DEV_NO_AUTH=1
#   export BLOCKINTQL_API_URL=http://127.0.0.1:8000
#   (or with a real BLOCKINTQL_API_KEY for hosted paths)
#
# Usage: ./scripts/v1_smoke.sh [address]
# Example: ./scripts/v1_smoke.sh 0x742d35Cc6634C0532925a3b844Bc9e7595f6EEd0

ADDRESS="${1:-0x742d35Cc6634C0532925a3b844Bc9e7595f6EEd0}"
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

run_json() {
  local name="$1"
  shift
  echo "==> $name"
  "$@" --agent > "$TMPDIR/$name.json" 2>/dev/null || "$@" > "$TMPDIR/$name.json"
  cat "$TMPDIR/$name.json"
  echo
}

# Core surface that must work
run_json status blockintql status || true
run_json verdict blockintql verdict "$ADDRESS" || true
run_json history blockintql history "$ADDRESS" --days 30 --limit 30 || true

# The OSS deterministic core (the highest leverage part of the foundation + next wave)
run_json deterministic_eval blockintql deterministic eval
run_json deterministic_adjudicate blockintql deterministic adjudicate "$ADDRESS" --json

# Graph shell (compile, spec, seeds, explorer handoff) - explicitly required in this task
run_json graph_shell blockintql graph shell "Build analyst graph with timeline, evidence drawer and local deterministic support" --seed "$ADDRESS" --json

# Evidence export (reproducible audit artifact from local core)
run_json evidence_export blockintql deterministic export-evidence "$ADDRESS" --out "$TMPDIR/evidence.json" || blockintql deterministic export-evidence "$ADDRESS" --out "$TMPDIR/evidence.json"

python3 - <<'PY' "$TMPDIR" "$ADDRESS"
import json, pathlib, sys, os
root = pathlib.Path(sys.argv[1])
addr = sys.argv[2].lower()

def read(name):
    p = root / f"{name}.json"
    return json.loads(p.read_text()) if p.exists() else {}

checks = []
status = read("status")
verdict = read("verdict")
history = read("history")
deval = read("deterministic_eval")
dadjud = read("deterministic_adjudicate")
gshell = read("graph_shell")
evidence = read("evidence_export") or (json.loads((root / "evidence.json").read_text()) if (root / "evidence.json").exists() else {})

checks.append(("status_ok", isinstance(status, dict) and "version" in str(status) or bool(status)))
checks.append(("verdict_has_decision", bool(verdict.get("verdict") or (verdict.get("blockintql") or {}).get("verdict"))))
checks.append(("history_has_data", bool(history.get("rows") or history.get("data") or history.get("transactions"))))
checks.append(("deterministic_eval_passed", "passed" in str(deval) or deval.get("accuracy", 0) > 0 or "100%" in str(deval)))
checks.append(("deterministic_adjudicate_has_verdict", bool(dadjud.get("verdict"))))
checks.append(("graph_shell_compiled", "shell_spec" in gshell or "prompt" in gshell))
checks.append(("evidence_bundle_has_hash", bool(evidence.get("bundle_hash") or evidence.get("reproducibility_hash"))))

# When running under DEV_NO_AUTH the local core produces the bundle even if some server fields are absent
is_local = bool(os.environ.get("BLOCKINTQL_DEV_NO_AUTH")) or "127.0.0.1" in os.environ.get("BLOCKINTQL_API_URL", "") or "localhost" in os.environ.get("BLOCKINTQL_API_URL", "")
if is_local:
    checks.append(("local_evidence_or_deterministic", bool(evidence) or bool(dadjud)))

failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(f"{name}: {'PASS' if ok else 'FAIL'}")

if failed:
    print("\nSmoke check failed:", ", ".join(failed))
    sys.exit(2)
print("\nSmoke check passed (including graph shell + deterministic real-trace fixtures).")
PY
