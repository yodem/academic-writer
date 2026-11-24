#!/usr/bin/env bash
# Fails when the change against the base deletes or moves test files, or removes test cases or
# assertions overall, unless a commit message (or the PR body, via $PR_BODY) says
# "tests-removed: <reason>".
# Usage: scripts/test-integrity.sh [base-ref]   (default origin/main)
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
base="${1:-origin/main}"
git rev-parse --verify -q "$base^{commit}" >/dev/null || { echo "test-integrity: base '$base' not found" >&2; exit 2; }

# Waivers: only commits that are in HEAD and not in base (two-dot), plus the PR body.
if printf '%s\n%s\n' "${PR_BODY:-}" "$(git log --format=%B "$base..HEAD")" | grep -qiE 'tests-removed:[[:space:]]*[^[:space:]]'; then
  echo "test-integrity: 'tests-removed:' reason found, skipping"; exit 0
fi

is_test='(^|/)(tests?|__tests__|e2e)/|(^|/)test_[^/]*\.py$|\.(test|spec)\.[cm]?[jt]sx?$|_test\.py$'
# Cases and assertions. Skipped, todo and only variants are not counted, so turning a test into one
# of them reads as a removal. Optional async/await prefixes are allowed.
case_re='(async[[:space:]]+)?def[[:space:]]+test_|(await[[:space:]]+)?(t\.)?(it|test)(\.(concurrent|each))?\(|assert[[:space:](.]|expect\(|self\.assert'
problems=""

# --no-renames: a moved test shows as delete plus add, so it needs a waiver (or stays put).
deleted=""
while IFS= read -r -d '' f; do
  if printf '%s' "$f" | grep -qE "$is_test"; then deleted+="$f"$'\n'; fi
done < <(git diff --no-renames --diff-filter=D --name-only -z "$base...HEAD")
[ -n "$deleted" ] && problems+="deleted or moved test files:"$'\n'"$deleted"

minus=0; plus=0
while IFS= read -r -d '' f; do
  printf '%s' "$f" | grep -qE "$is_test" || continue
  d=$(git diff --no-renames -U0 "$base...HEAD" -- "$f")
  m=$(printf '%s\n' "$d" | grep -E "^-[[:space:]]*($case_re)" | grep -vc '^---' || true)
  p=$(printf '%s\n' "$d" | grep -E "^\+[[:space:]]*($case_re)" | grep -vc '^+++' || true)
  minus=$((minus + m)); plus=$((plus + p))
done < <(git diff --no-renames --diff-filter=M --name-only -z "$base...HEAD")
[ "$minus" -gt "$plus" ] && problems+="modified test files lose test or assertion lines overall: -$minus / +$plus"$'\n'

if [ -n "$problems" ]; then
  printf 'test-integrity: FAIL\n%s\nAdd "tests-removed: <reason>" to the PR body or a commit message if intended.\n' "$problems"
  exit 1
fi
echo "test-integrity: OK ($base...HEAD)"
