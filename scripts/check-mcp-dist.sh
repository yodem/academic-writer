#!/usr/bin/env bash
# check-mcp-dist.sh
#
# CI gate guarding against the CONNECTION_CLOSED regression: the published
# plugin marketplace ships only what's committed to git (no install/build
# lifecycle hook exists — see plugins/academic-writer/hooks/hooks.json), and
# from v0.6.2 through v0.7.0 the bundled Gemini MCP server's dist/index.js was
# gitignored and never shipped. A freshly-installed plugin's gemini-api MCP
# server then crashed on first connect with `Cannot find module
# .../dist/index.js`, silently degrading section-writer/synthesizer to their
# in-context fallback path across 5 live project installs on this machine
# before it was noticed.
#
# esbuild.config.mjs now bundles @modelcontextprotocol/sdk and @google/genai
# INTO dist/index.js (`external: []`, plus a `createRequire(import.meta.url)`
# banner shim so google-auth-library's internal dynamic `require()` calls
# still resolve under ESM output) — so dist/index.js is fully self-contained
# and needs nothing from node_modules at runtime.
#
# This script proves that self-containment directly: it copies ONLY
# dist/index.js (plus the runtime-loaded scripts/ directory — gemini_ocr's
# Python helpers, resolved relative to dist/index.js's own location, see
# src/tools/gemini_ocr_deps.ts) out of the repo into an isolated temp
# directory with NO node_modules anywhere in its ancestry (so it can't
# accidentally pass by resolving a dependency from this dev repo's own root
# node_modules or a parent directory), then starts the server there the same
# way Claude Code does. An MCP stdio server with no client attached exits
# cleanly once stdin hits EOF (exit 0) or keeps waiting until the timeout
# fires (exit 124) — both are success. A module-resolution crash exits 1 and
# writes to stderr — that is exactly the shipped-bug signature and is a hard
# failure here.
#
# Exit 0 -> dist/index.js is present and starts clean, self-contained, with no
#           node_modules anywhere in its ancestry
# Exit 1 -> missing dist/index.js, or it crashes on start
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MCP_DIR="$PROJECT_ROOT/plugins/academic-writer/mcp/gemini-server"

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

fail() {
  echo -e "${RED}✗ check-mcp-dist: $1${NC}" >&2
  exit 1
}

[[ -f "$MCP_DIR/dist/index.js" ]] || fail "missing $MCP_DIR/dist/index.js (run \`npm run build\` / \`bash scripts/build-mcp.sh\` first)"

command -v node &>/dev/null || fail "node is required for this check"

TMP_CHECK="$(mktemp -d)"
trap 'rm -rf "$TMP_CHECK"' EXIT

mkdir -p "$TMP_CHECK/dist"
cp "$MCP_DIR/dist/index.js" "$TMP_CHECK/dist/index.js"

# gemini_ocr's Python helpers are not bundled (esbuild only bundles JS/TS) and
# are resolved at runtime relative to dist/index.js's own location
# (path.resolve(dirname(fileURLToPath(import.meta.url)), '..', 'scripts') —
# see src/tools/gemini_ocr_deps.ts), i.e. as a sibling of dist/. Mirror that
# layout here so this check reflects the real installed shape.
if [[ -d "$MCP_DIR/scripts" ]]; then
  cp -R "$MCP_DIR/scripts" "$TMP_CHECK/scripts"
fi

# Deliberately no node_modules anywhere under $TMP_CHECK or its ancestors —
# that absence is the thing this check exists to prove.
( cd "$TMP_CHECK" && timeout 5 node dist/index.js < /dev/null > "$TMP_CHECK/stdout.log" 2> "$TMP_CHECK/stderr.log" )
EC=$?

# 0  = stdin hit EOF and the process exited cleanly (no real MCP client attached
#      here — this is expected and fine)
# 124 = timeout fired, meaning the server was still alive waiting on stdin
#      (this is the shape a real client sees — also fine)
# anything else = it crashed on startup
if [[ "$EC" != "0" && "$EC" != "124" ]]; then
  fail "dist/index.js failed to start (exit $EC). stderr:
$(cat "$TMP_CHECK/stderr.log")"
fi

if [[ -s "$TMP_CHECK/stderr.log" ]]; then
  fail "dist/index.js printed to stderr on startup (unexpected — a clean start is silent):
$(cat "$TMP_CHECK/stderr.log")"
fi

echo -e "${GREEN}✓ check-mcp-dist: dist/index.js starts cleanly self-contained, with no node_modules anywhere in its ancestry${NC}"
exit 0
