#!/bin/bash
# voice-sync.sh — pull/push AUTHOR_VOICE.md to/from CandleKeep
# Usage: voice-sync.sh {pull|push|status}
# Env:
#   VOICE_PROJECT_ROOT — overrides $(pwd) for testing
#   VOICE_WRITER_NAME  — overrides author_key resolution; primarily for testing
#
# CandleKeep CLI surface used here (verified against `ck items --help`):
#   ck items list --json          -> {"items":[{id,title,...}]}   (NOT a bare array)
#   ck items get   <ID>           -> document markdown on stdout
#   ck items import <FILE> --title <T> --json   -> creates a new book
#   ck items put   <ID> -f <FILE>               -> replaces document content
# There is no `ck books` subcommand. The previous version called one, and wrapped
# every call in `2>/dev/null || echo "...local-only mode"`, so a hard CLI error
# was reported as a missing/unsupported CandleKeep install. Failures now print
# the real stderr and exit non-zero; only a genuinely absent `ck` is local-only.

set -euo pipefail

action=${1:-status}
root="${VOICE_PROJECT_ROOT:-$(pwd)}"
profile="$root/AUTHOR_VOICE.md"
voice_dir="$root/.voice"
id_cache="$voice_dir/.candlekeep-id"
profile_md="$root/.academic-helper/profile.md"

# Resolve author_key. Primary source: .academic-helper/profile.md YAML frontmatter.
# VOICE_WRITER_NAME is an env override kept for testing only — the canonical path is profile.md.
# No silent fallback: if neither source yields a value, fail loudly and exit.
author_key="${VOICE_WRITER_NAME:-}"
if [[ -z "$author_key" ]]; then
  if [[ -f "$profile_md" ]]; then
    author_key=$(grep -E '^author_key:' "$profile_md" 2>/dev/null \
      | sed -E 's/^author_key:[[:space:]]*//' | tr -d '"' || true)
  fi
fi

if [[ -z "$author_key" ]]; then
  # Secondary source: book.yaml (sibling hebrew-book-producer projects). Also fails loudly if empty.
  if [[ -f "$root/book.yaml" ]]; then
    author_key=$(grep -E '^author:' "$root/book.yaml" 2>/dev/null \
      | sed -E 's/^author:[[:space:]]*"?([^"]*)"?$/\1/' || true)
  fi
fi

if [[ -z "$author_key" ]]; then
  echo "voice-sync: author_key not found in .academic-helper/profile.md — run /academic-writer:init to set it" >&2
  exit 1
fi

title="Voice Profile — $author_key"

if ! command -v ck >/dev/null 2>&1; then
  echo "voice-sync: ck not available — local-only mode"
  exit 0
fi

# `ck` resolves on PATH but may still be unrunnable (a shim whose interpreter is
# missing, a stub). Exit 127 from the binary itself means "command not found" —
# that, and ONLY that, is local-only mode. Every other non-zero exit is a real
# CandleKeep error and must be reported as one. `items --help` is a local clap
# help path: no network, unlike `ck --version`.
set +e
ck items --help >/dev/null 2>&1
_ck_probe=$?
set -e
if [[ $_ck_probe -eq 127 ]]; then
  echo "voice-sync: ck is on PATH but not runnable (exit 127) — local-only mode"
  exit 0
fi

# Run a ck command, capturing stdout. On failure, surface the REAL stderr and
# fail — never rewrite a CLI error into "ck unavailable".
ck_run() {
  local err out status
  err=$(mktemp)
  set +e
  out=$(ck "$@" 2>"$err")
  status=$?
  set -e
  if [[ $status -ne 0 ]]; then
    echo "voice-sync: \`ck $*\` failed (exit $status): $(tr '\n' ' ' < "$err")" >&2
    rm -f "$err"
    return $status
  fi
  rm -f "$err"
  printf '%s' "$out"
}

# Extract an item id from a ck --json payload, tolerating the shapes ck uses
# ({"id":...}, {"item":{"id":...}}, {"items":[...]}, or a bare list).
_parse_id_by_title() {
  VOICE_TITLE="$title" python3 -c "
import sys, json, os
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
t = os.environ['VOICE_TITLE']
items = d.get('items') if isinstance(d, dict) else d
if not isinstance(items, list):
    sys.exit(0)
for b in items:
    if isinstance(b, dict) and b.get('title') == t:
        print(b.get('id', ''))
        sys.exit(0)
"
}

_parse_created_id() {
  python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
if isinstance(d, dict):
    for key in ('id', 'itemId', 'documentId'):
        if isinstance(d.get(key), str):
            print(d[key]); sys.exit(0)
    for key in ('item', 'document', 'book'):
        inner = d.get(key)
        if isinstance(inner, dict) and isinstance(inner.get('id'), str):
            print(inner['id']); sys.exit(0)
"
}

cache_id() {
  mkdir -p "$voice_dir"
  printf '%s' "$1" > "$id_cache"
}

# Resolve the CandleKeep item id for this author's voice profile: cached id
# first, then a title lookup against the library (so a repaired push binds to
# an existing "Voice Profile — <author_key>" book instead of duplicating it).
ensure_id() {
  if [[ -s "$id_cache" ]]; then
    cat "$id_cache"
    return 0
  fi
  local listing id
  listing=$(ck_run items list --json) || return 1
  id=$(printf '%s' "$listing" | _parse_id_by_title)
  if [[ -n "$id" ]]; then
    cache_id "$id"
  fi
  printf '%s' "$id"
}

require_profile() {
  if [[ ! -f "$profile" ]]; then
    echo "voice-sync $action: $profile does not exist — run /academic-writer:voice first" >&2
    exit 1
  fi
}

case "$action" in
  status)
    if [[ -s "$id_cache" ]]; then
      echo "voice-sync status: cached id=$(cat "$id_cache"), title=$title"
    else
      echo "voice-sync status: no cached candlekeep id"
    fi
    ;;
  pull)
    id=$(ensure_id)
    if [[ -z "$id" ]]; then
      echo "voice-sync pull: no remote book titled \"$title\" yet (run push to create)"
      exit 0
    fi
    # Clean up the temp file if the pull is interrupted (e.g. SessionStart hook timeout).
    trap 'rm -f "$profile.tmp" 2>/dev/null' EXIT
    ck_run items get "$id" > "$profile.tmp"
    if [[ ! -s "$profile.tmp" ]]; then
      echo "voice-sync pull: remote book id=$id returned empty content; kept local" >&2
      rm -f "$profile.tmp"
      exit 1
    fi
    # Last-write-wins by `> Updated` stamp comparison
    local_stamp=$(grep -m1 '^> Updated' "$profile" 2>/dev/null | sed -E 's/^> Updated ([0-9-]+).*/\1/' || echo "0")
    remote_stamp=$(grep -m1 '^> Updated' "$profile.tmp" 2>/dev/null | sed -E 's/^> Updated ([0-9-]+).*/\1/' || echo "0")
    if [[ "$remote_stamp" > "$local_stamp" ]]; then
      mv "$profile.tmp" "$profile"
      echo "voice-sync pull: remote ($remote_stamp) overwrote local ($local_stamp)"
    else
      rm -f "$profile.tmp"
      echo "voice-sync pull: local ($local_stamp) is newer or equal to remote ($remote_stamp); kept local"
    fi
    ;;
  push)
    require_profile
    id=$(ensure_id)
    if [[ -z "$id" ]]; then
      created=$(ck_run items import "$profile" --title "$title" --json)
      id=$(printf '%s' "$created" | _parse_created_id)
      if [[ -z "$id" ]]; then
        echo "voice-sync push: \`ck items import\` succeeded but returned no item id; payload was: $(printf '%s' "$created" | tr '\n' ' ' | cut -c1-300)" >&2
        exit 1
      fi
      cache_id "$id"
      echo "voice-sync push: created remote book id=$id"
    else
      ck_run items put "$id" -f "$profile" >/dev/null
      echo "voice-sync push: updated remote book id=$id"
    fi
    ;;
  *)
    echo "usage: $0 {pull|push|status}" >&2
    exit 2
    ;;
esac
