#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Building Python distribution..."
cd "$ROOT"
python3 setup.py sdist bdist_wheel

echo
echo "Building npm package tarball..."
cd "$ROOT/integrations/javascript"
NPM_CONFIG_CACHE="${NPM_CONFIG_CACHE:-/tmp/.npm-cache}" npm pack --silent

echo
echo "Artifacts ready:"
cd "$ROOT"
ls -1 dist
cd "$ROOT/integrations/javascript"
ls -1 *.tgz
