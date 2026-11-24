#!/usr/bin/env bash
# Fails when the change against the base deletes test files or removes test cases or
# assertions, unless the PR body or a commit message carries "tests-removed: <reason>".
# Usage: scripts/test-integrity.sh [base-ref]   (default origin/main)
# PR body: pass it in $PR_BODY (CI does); commit messages are read from git.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
base="${1:-origin/main}"
range="$base...HEAD"

if printf '%s\n%s\n' "${PR_BODY:-}" "$(git log --format=%B "$range")" | grep -qiE 'tests-removed:[[:space:]]*[^[:space:]]'; then
  echo "test-integrity: 'tests-removed:' reason found, skipping"; exit 0
fi

is_test='(^|/)(tests?|__tests__|e2e)/|(^|/)test_[^/]*\.py$|\.(test|spec)\.[cm]?[jt]sx?$|_test\.py$'
problems=""

deleted=$(git diff --diff-filter=D --name-only "$range" | grep -E "$is_test" || true)
[ -n "$deleted" ] && problems+="deleted test files:"$'\n'"$deleted"$'\n'

# Modified test files: flag a file that loses more test-case/assertion lines than it gains.
case_re='(def test_|(it|test|describe)(\.(only|skip|each))?\(|assert[[:space:](.]|expect\(|self\.assert)'
net=""
for f in $(git diff --diff-filter=M --name-only "$range" | grep -E "$is_test" || true); do
  d=$(git diff -U0 "$range" -- "$f")
  minus=$(printf '%s\n' "$d" | grep -E "^-[[:space:]]*${case_re}" | grep -vc '^---' || true)
  plus=$(printf '%s\n' "$d" | grep -E "^\+[[:space:]]*${case_re}" | grep -vc '^+++' || true)
  [ "$minus" -gt "$plus" ] && net+="$f: -$minus / +$plus test or assertion lines"$'\n'
done
[ -n "$net" ] && problems+="removed tests or assertions:"$'\n'"$net"

if [ -n "$problems" ]; then
  printf 'test-integrity: FAIL\n%s\nAdd "tests-removed: <reason>" to the PR body or a commit message if intended.\n' "$problems"
  exit 1
fi
echo "test-integrity: OK ($range)"
