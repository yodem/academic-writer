#!/bin/sh
# guard.sh: every Academic Writer hook runs through this file, so a computer without Node.js gets one
# plain sentence a session instead of "node: command not found" on every hook.
#
# Usage (from hooks.json):  sh "${CLAUDE_PLUGIN_ROOT}/hooks/bin/guard.sh" <hook-name>
#   <hook-name> like lifecycle/session-env  -> node run-hook.mjs <hook-name>   (stdin passed through)
#   <hook-name> ending in .sh               -> bash <plugin root>/<hook-name>  (stdin passed through)
#
# Why "sh" and why this shape: Claude Code on Windows runs a command hook in Git Bash when Git for
# Windows is installed, and in PowerShell only when it is not ("The `command` string is passed to a
# shell: `sh -c` on macOS and Linux, Git Bash on Windows, or PowerShell when Git Bash isn't
# installed", https://code.claude.com/docs/en/hooks). The Bash tool uses Git Bash the same way
# (https://code.claude.com/docs/en/setup, "Set up on Windows"). This file is POSIX sh and is run as
# `sh guard.sh` because the executable bit does not survive a Windows checkout. Git for Windows is
# therefore a prerequisite of this plugin (setup installs it first); Node.js is checked here.
#
# Without node: print one line per session and exit 0 (a hook must never fail a session over this).
# The once-per-session marker is keyed on session_id from the stdin JSON, read with sed (no node, no python),
# and claimed with mkdir, which is atomic: when several hooks start at once, only the one whose mkdir succeeds prints.

ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"

# stdin is never read on a path that has a program to hand it to: a producer that leaves it open must not block the guard.
# A .sh hook (voice-migrate.sh) needs bash and Python, not node, so it keeps working without node.
case "$1" in
  *.sh) if command -v bash >/dev/null 2>&1; then exec bash "$ROOT/$1"; fi ;;
esac

if command -v node >/dev/null 2>&1; then
  exec node "$ROOT/hooks/bin/run-hook.mjs" "$@"   # run-hook.mjs has its own 2-second stdin timer
fi

# No node: read stdin only to learn the session_id, for at most ~2 seconds (a producer may leave it open).
input=""
if [ ! -t 0 ]; then
  tmpf="${TMPDIR:-/tmp}/aw-guard-$$"
  exec 3<&0
  dd bs=65536 count=1 <&3 >"$tmpf" 2>/dev/null &
  rpid=$!
  ( sleep 2; kill "$rpid" 2>/dev/null ) >/dev/null 2>&1 &
  kpid=$!
  wait "$rpid" 2>/dev/null
  kill "$kpid" 2>/dev/null
  exec 3<&-
  input=$(cat "$tmpf" 2>/dev/null)
  rm -f "$tmpf"
fi

sid=$(printf '%s' "$input" | sed -n 's/.*"session_id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n 1 | tr -c 'A-Za-z0-9_\n-' '_')
[ -n "$sid" ] || sid="ppid-$PPID"
dir="${CLAUDE_PLUGIN_DATA:-${TMPDIR:-/tmp}}"
marker="$dir/node-missing-$sid"
msg="Academic Writer needs Node.js: run /academic-writer:setup"
if ! mkdir -p "$dir" 2>/dev/null; then
  echo "$msg"   # nowhere to keep a marker: say it every time rather than never
elif mkdir "$marker" 2>/dev/null; then
  echo "$msg"
fi
exit 0
