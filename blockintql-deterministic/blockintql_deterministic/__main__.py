#!/usr/bin/env python3
"""
CLI for the blockintql-deterministic package.

Examples:
  blockintql-deterministic --version
  blockintql-deterministic adjudicate 0x7F19720A857F834887FC9A7bC0a0fBe7Fc7f8102
  blockintql-deterministic adjudicate 0x0000000000000000000000000000000000000000 --provider-json '{"sanctions_hit": true}'
  blockintql-deterministic eval
"""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .core import adjudicate
from .policy import Policy, load_policy


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="blockintql-deterministic",
        description="BlockINTQL deterministic screening core. sonar_consensus_v1 swarm (Sentinel / Cypher / Nova).",
    )
    parser.add_argument("-V", "--version", action="store_true", help="Print version and exit")

    subparsers = parser.add_subparsers(dest="cmd")

    # adjudicate
    p_adj = subparsers.add_parser("adjudicate", help="Run local deterministic adjudication (Sentinel + Cypher FIFO + Nova)")
    p_adj.add_argument("address", help="Subject address or tx hash")
    p_adj.add_argument("--chain", default="ethereum", choices=["ethereum", "bitcoin"], help="Chain (default ethereum)")
    p_adj.add_argument("--provider-json", default=None, help='Inline JSON provider result, e.g. \'{"sanctions_hit": true}\'')
    p_adj.add_argument("--policy", default=None, help="Path to custom policy JSON (optional)")
    p_adj.add_argument("--labels", default=None, help="Path to own_labels JSON (optional)")
    p_adj.add_argument("--json", action="store_true", help="Emit full JSON result instead of human summary")

    # eval (self-contained smoke using the library)
    p_eval = subparsers.add_parser("eval", help="Run a tiny built-in evaluation suite (proves the package works standalone)")
    p_eval.add_argument("--json", action="store_true", help="Emit machine-readable results")

    args = parser.parse_args(argv)

    if args.version:
        print(f"blockintql-deterministic {__version__}")
        return 0

    if args.cmd == "adjudicate":
        provider_result = None
        if args.provider_json:
            try:
                provider_result = json.loads(args.provider_json)
            except Exception as e:
                print(f"ERROR: bad --provider-json: {e}", file=sys.stderr)
                return 2

        policy = None
        if args.policy:
            try:
                with open(args.policy) as f:
                    policy = load_policy(json.load(f))
            except Exception as e:
                print(f"ERROR: could not load policy: {e}", file=sys.stderr)
                return 2

        own_labels = None
        if args.labels:
            try:
                with open(args.labels) as f:
                    own_labels = json.load(f)
            except Exception as e:
                print(f"ERROR: could not load labels: {e}", file=sys.stderr)
                return 2

        try:
            res = adjudicate(
                args.address,
                chain=args.chain,
                provider_result=provider_result,
                policy=policy,
                own_labels=own_labels,
            )
        except Exception as e:
            print(f"ERROR: adjudication failed: {e}", file=sys.stderr)
            return 1

        if args.json:
            print(json.dumps(res, indent=2, default=str))
        else:
            print(f"verdict: {res.get('verdict')}  risk: {res.get('risk_score')}/100  safe: {res.get('safe')}")
            cons = res.get("consensus") or {}
            votes = cons.get("votes") or []
            if votes:
                print("agents:")
                for v in votes:
                    print(f"  - {v.get('agent')}: {v.get('vote')}  ({v.get('reason', '')[:80]})")
            if res.get("evidence_bundle"):
                print("evidence_bundle: present (reproducible audit artifact)")
        return 0

    if args.cmd == "eval":
        # Tiny self-contained suite (no dependency on the full blockintql package)
        cases = [
            {"name": "sanctions", "addr": "0x0000000000000000000000000000000000000000", "prov": {"sanctions_hit": True}, "want": "BLOCK"},
            {"name": "high_risk", "addr": "0x1111111111111111111111111111111111111111", "prov": {"risk_score": 93, "entity_category": "unknown"}, "want": "CAUTION"},
            {"name": "clean_exchange", "addr": "0x2222222222222222222222222222222222222222", "prov": {"entity_category": "exchange", "risk_score": 4}, "want": "CLEAR"},
        ]
        results = []
        for c in cases:
            r = adjudicate(c["addr"], provider_result=c["prov"])
            ok = r.get("verdict") == c["want"]
            results.append({"name": c["name"], "verdict": r.get("verdict"), "expected": c["want"], "match": ok})

        passed = sum(1 for r in results if r["match"])
        total = len(results)
        summary = {"total": total, "passed": passed, "accuracy": round(passed / total, 4) if total else 0, "results": results}

        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            print(f"blockintql-deterministic eval: {passed}/{total} passed (accuracy {summary['accuracy']})")
            for r in results:
                mark = "✓" if r["match"] else "✗"
                print(f"  {mark} {r['name']}: got {r['verdict']} (want {r['expected']})")
        return 0 if passed == total else 1

    # No subcommand: show quick help + version
    print(f"blockintql-deterministic {__version__}")
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
