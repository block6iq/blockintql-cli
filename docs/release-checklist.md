# BlockINTQL CLI Release Checklist

Use this checklist when publishing a new installable CLI release to PyPI and npm.

## Versioning

1. Update the Python package version in `blockintql/__init__.py`.
2. Update the JavaScript package version in `integrations/javascript/package.json`.
3. Confirm README examples match the current CLI surface.

## Verification

1. Run:

```bash
PYTHONPYCACHEPREFIX=/tmp/pycache python3 -m py_compile blockintql/cli.py
python3 -m blockintql.cli --help
python3 -m blockintql.cli ask --help
python3 -m blockintql.cli workspace --help
python3 -m blockintql.cli workspace review --help
python3 -m blockintql.cli workspace conversation --help
```

2. Optional live smoke tests against the active API:

```bash
blockintql status
blockintql ask "Open a deeper stablecoin investigation workspace for this wallet" \
  --address 0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045 \
  --budget-credits 12
```

## Python Package Release

1. Build the distribution:

```bash
python3 setup.py sdist bdist_wheel
```

2. Publish with your standard PyPI credentials/tooling.

3. Verify install:

```bash
python3 -m pip install --upgrade blockintql==1.2.0
blockintql --help
```

## npm Package Release

1. Change into the package directory:

```bash
cd integrations/javascript
```

2. Publish with your standard npm credentials/tooling.

3. Verify the published package version and install path.

## Post-Release

1. Tag the release in git.
2. Update any install docs or landing pages that reference the old version.
3. Confirm the release branch and default branch both reflect the shipped version.
