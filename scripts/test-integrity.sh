#!/usr/bin/env bash
# usage: test-integrity.sh <base-ref>
# Compares the test runner's own test list on <base-ref> and HEAD (core: scripts/test_integrity.py).
# CI passes PR_BODY_FILE, PR_LABELS_FILE and PR_LABEL_EVENTS_FILE as file paths; PR text never enters a shell string.
set -euo pipefail
BASE="${1:?usage: test-integrity.sh <base-ref>}"
HEAD_TREE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CORE="${TI_CORE:-$HEAD_TREE/scripts/test_integrity.py}"
CONFIG="${TI_CONFIG:-$HEAD_TREE/scripts/test-integrity.json}"
git -C "$HEAD_TREE" rev-parse --verify --quiet "$BASE^{commit}" >/dev/null || { echo "test-integrity: base ref '$BASE' not found" >&2; exit 2; }
TMP="$(mktemp -d)"
cleanup() { git -C "$HEAD_TREE" worktree remove --force "$TMP/base" >/dev/null 2>&1 || true; rm -rf "$TMP"; }
trap cleanup EXIT
git -C "$HEAD_TREE" worktree add -q --detach "$TMP/base" "$BASE"
args=(run --config "$CONFIG" --base-tree "$TMP/base" --head-tree "$HEAD_TREE" --base-ref "$BASE")
[ -n "${PR_BODY_FILE:-}" ] && args+=(--pr-body-file "$PR_BODY_FILE")
[ -n "${PR_LABELS_FILE:-}" ] && args+=(--labels-file "$PR_LABELS_FILE")
[ -n "${PR_LABEL_EVENTS_FILE:-}" ] && args+=(--label-events-file "$PR_LABEL_EVENTS_FILE")
set +e
python3 "$CORE" "${args[@]}"
rc=$?
exit "$rc"
