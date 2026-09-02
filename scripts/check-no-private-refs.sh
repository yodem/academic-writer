#!/usr/bin/env bash
# Fail if a tracked, published file carries a personal identifier.
#
# github.com/yodem/academic-writer is PUBLIC. During the 0.7.0 work, documentation
# and prompt files accumulated the maintainer's absolute home path, paths to private
# local plan and wiki files, and the filename of an unpublished article alongside the
# journal that rejected it. None of that belongs in a public plugin.
#
# Deterministic by design: regex denylists over `git ls-files`, no model in the loop.
# Wired into the release workflow and into pytest via tests/test_no_private_refs.py.
#
# Two tiers, deliberately. SHIPPED files (src/, plugins/, manifests/) are what a user
# installs and are held to the strict list. PUBLISHED docs (docs/, tests/, scripts/,
# .github/, root md) are held to the identity list only — CandleKeep item ids are a
# pre-existing provenance convention in this repo's own docs/reviews and
# docs/superpowers plans, and stripping them would rewrite the maintainer's prior
# documentation choices rather than fix a leak. Ids are therefore NOT denied here;
# whether to scrub them is the maintainer's call, not this script's.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

SHIPPED_RE='^(src/|plugins/|manifests/|features\.json)'
PUBLISHED_RE='^(docs/|tests/|scripts/|\.github/|CLAUDE\.md|README\.md|CHANGELOG\.md)'

# Applied to BOTH tiers. Field separator is '::' — never '|', which is also the
# regex alternation operator (an earlier version of this script silently ran only
# the first alternative of each pattern because of exactly that collision).
IDENTITY_DENY=(
  '/Users/[A-Za-z]::absolute macOS home path (leaks the maintainer name and local layout)'
  '/home/[A-Za-z]::absolute Linux home path (leaks the maintainer name and local layout)'
  '\.claude/plans/::path to a private local plan file'
  'claude-obsidian::path to the private personal wiki vault'
  'bikoret-musarit::filename of an unpublished article'
)

# Applied to SHIPPED files only — stricter, because these are installed by users.
SHIPPED_ONLY_DENY=(
  '\bcm[a-z0-9]{22,}\b::CandleKeep item id in a shipped file (cite the title, not the id)'
  '[Mm]ikdashim::name of an unrelated private project in a shipped file (describe the failure, not the project)'
)

# Paths that must never be TRACKED at all: machine-local session/harness state and
# the maintainer's own drafts. They carry home paths, session ids and personal
# content, and a shareable plugin repo has no use for any of them. Untracked
# 2026-09-02; this list stops them creeping back via `git add -A`.
TRACKED_PATH_DENY=(
  '^\.claude/(state|memory|agents|context|orchestration)/::machine-local harness state'
  '^\.claude/HANDOFF\.md$::machine-local session handoff'
  '^\.instance/::machine-local session id'
  '^\.removal-log/::one-off local migration log'
  '^past-articles/::the maintainer'"'"'s own article corpus'
  '^logs/::local run logs'
  '^pitch-::the maintainer'"'"'s own pitch drafts'
)

status=0

run_tier() {
  local scope_re="$1"; shift
  # This script and its test necessarily CONTAIN the denied patterns — they are the
  # definition of them. Excluding them is not a loophole: nothing else may match.
  local files; files="$(git ls-files | grep -E "$scope_re" \
      | grep -v node_modules \
      | grep -vE '^(scripts/check-no-private-refs\.sh|tests/test_no_private_refs\.py)$' || true)"
  [[ -z "$files" ]] && return 0
  local entry pattern reason hits
  for entry in "$@"; do
    pattern="${entry%%::*}"
    reason="${entry##*::}"
    hits="$(printf '%s\n' "$files" | tr '\n' '\0' | xargs -0 grep -InE -- "$pattern" 2>/dev/null || true)"
    if [[ -n "$hits" ]]; then
      echo "FAIL: $reason"
      printf '%s\n' "$hits" | cut -c1-160 | sed 's/^/    /' | head -12
      echo ""
      status=1
    fi
  done
}

run_tier "$SHIPPED_RE"   "${IDENTITY_DENY[@]}" "${SHIPPED_ONLY_DENY[@]}"
run_tier "$PUBLISHED_RE" "${IDENTITY_DENY[@]}"

# Tracked-path tier: a content grep cannot catch a file that should not be in the
# index at all.
all_tracked="$(git ls-files || true)"
for entry in "${TRACKED_PATH_DENY[@]}"; do
  pattern="${entry%%::*}"
  reason="${entry##*::}"
  hits="$(printf '%s\n' "$all_tracked" | grep -E "$pattern" || true)"
  if [[ -n "$hits" ]]; then
    echo "FAIL: tracked file that should be gitignored — $reason"
    printf '%s\n' "$hits" | sed 's/^/    /' | head -8
    echo "    fix: git rm -r --cached <path>   (the files stay on disk)"
    echo ""
    status=1
  fi
done

if [[ $status -eq 0 ]]; then
  echo "✓ check-no-private-refs: no personal identifiers in shipped or published paths"
else
  echo "check-no-private-refs: keep the technical rationale, drop the identity."
  echo "  '~6,600-token Hebrew article' not a filename; 'the project plan' not a"
  echo "  private path; the book's title not its library id."
fi
exit $status
