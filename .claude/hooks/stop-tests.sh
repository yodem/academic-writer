#!/usr/bin/env bash
# Stop gate: when the working tree has changes, run this repo's fast checks before Claude finishes.
# Exit 2 + stderr sends Claude back to fix; stop_hook_active lets it through on the second try (no loop).
input=$(cat)
[ "$(printf '%s' "$input" | jq -r '.stop_hook_active // false' 2>/dev/null)" = "true" ] && exit 0
root=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
cd "$root" || exit 0
[ -z "$(git status --porcelain)" ] && exit 0
TEST_CMD='python3 scripts/version-sync.py --check >/dev/null && bash scripts/check-version-consistency.sh >/dev/null && bash scripts/check-no-private-refs.sh >/dev/null && python3 scripts/check-brand.py --surface all >/dev/null && python3 scripts/gen-brand-tokens.py --check >/dev/null && python3 scripts/gen-about.py --check >/dev/null && npm run typecheck --silent && npm run typecheck:cli --silent'
out=$(bash -c "$TEST_CMD" 2>&1); rc=$?
[ "$rc" -eq 0 ] && exit 0
{ printf 'Stop gate: `%s` failed (exit %s). Fix it before finishing.\n' "$TEST_CMD" "$rc"; printf '%s\n' "$out" | tail -40; } >&2
exit 2
