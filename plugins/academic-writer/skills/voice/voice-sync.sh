#!/bin/bash
# Thin bridge to `aw voice {push|pull}`. Preferred form passes the plugin data dir and project dir
# explicitly (Bash gets no plugin env vars, docs/refactor/runtime-facts.md):
#   voice-sync.sh push|pull "${CLAUDE_PLUGIN_DATA}" "$PWD"
# The legacy one-argument form (voice-sync.sh pull) is still used by the SessionStart voice-pull hook
# and several skills; it falls back to the documented data dir and the current directory.
set -euo pipefail

if [[ $# -lt 1 || ( "$1" != "push" && "$1" != "pull" ) ]]; then
  echo "usage: $0 {push|pull} [<plugin-data-dir> [<project-dir>]]" >&2
  exit 2
fi
action=$1
data_dir=${2:-${CLAUDE_PLUGIN_DATA:-$HOME/.claude/plugins/data/academic-writer-academic-writer}}
project_dir=${3:-$PWD}
plugin_root="$(cd "$(dirname "$0")/../.." && pwd)"
aw="$plugin_root/bin/aw"
if [[ ! -x "$aw" ]]; then
  echo "voice-sync: aw CLI not found at $aw (run from the built plugin)" >&2
  exit 3
fi
exec "$aw" --data-dir "$data_dir" --project-dir "$project_dir" voice "$action"
