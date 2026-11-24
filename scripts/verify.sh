#!/usr/bin/env bash
# The single verify entry point: CI runs exactly this on every PR and push to main.
# Stages: lint (repo static gates), type check, tests, build. Stops at the first failure.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

step() { printf '\n==> %s\n' "$*"; }

step "install: hooks and CLI dependencies"
(cd src/hooks && npm ci --silent)
(cd src/cli && npm ci --silent)
if [ -f requirements-dev.txt ] && [ "${VERIFY_SKIP_PIP:-0}" != 1 ]; then
  python3 -m pip install --quiet -r requirements-dev.txt
fi

step "lint: version, private refs, brand and generated files"
python3 scripts/version-sync.py --check
bash scripts/check-version-consistency.sh
bash scripts/check-no-private-refs.sh
python3 scripts/check-brand.py --surface all
python3 scripts/gen-brand-tokens.py --check
python3 scripts/gen-about.py --check

step "type check: hooks and aw CLI"
npm run typecheck
npm run typecheck:cli

step "build: hooks bundle (the pytest suite drives the compiled bundle)"
npm run build:hooks

step "tests: pytest and aw CLI"
python3 -m pytest tests/ -q
npm run test:cli

step "build: plugin"
npm run build

printf '\nverify: OK\n'
