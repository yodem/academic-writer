#!/usr/bin/env bash
# Smoke gate over the BUILT plugin (plugins/academic-writer), not src/.
# Unit tests import src/ modules directly; three shipping bugs on 2026-09-23 passed them all:
# broken hook quoting (MODULE_NOT_FOUND), an ESM bundle that crashed on launch, and scripts that
# only found thresholds.json in the repo layout. This gate runs what actually ships.
#   bash scripts/smoke-built-plugin.sh          # offline checks
#   bash scripts/smoke-built-plugin.sh --live   # + live proofread recall eval (needs GOOGLE_API_KEY; ~$0.01)
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; P="$ROOT/plugins/academic-writer"; AW="$P/bin/aw"
fail=0; ok(){ echo "ok   $1"; }; bad(){ echo "FAIL $1"; fail=1; }
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT; mkdir -p "$T/data" "$T/proj/.academic-helper"; echo "# profile" > "$T/proj/.academic-helper/profile.md"

[[ -x "$AW" ]] && ok "bin/aw exists" || bad "bin/aw missing"
[[ ! -d "$P/mcp" ]] && ok "no retired MCP server shipped" || bad "plugins/academic-writer/mcp still present"
python3 - "$P" <<'PY' && ok "manifest has no mcpServers" || bad "manifest still declares mcpServers"
import json,sys; sys.exit(1 if "mcpServers" in json.load(open(sys.argv[1]+"/.claude-plugin/plugin.json")) else 0)
PY
out="$("$AW" 2>&1)"; [[ "$out" == *ERROR* && "$out" != *"Dynamic require"* && "$out" != *"at file://"* ]] && ok "aw starts" || bad "aw crashes on launch: ${out:0:200}"
for sub in "ledger show none" "voice bundle" "proofread --run smoke missing.md" "evidence build" "revise classify" "draft --outline missing.json --run smoke" "synthesize --outline missing.json --run smoke" "docx --outline missing.json --run smoke --out /tmp/x.docx" "edit --text-file missing.txt --instruction x --lang he --run smoke" "ocr --input missing.pdf --lang he --run smoke"; do
  # shellcheck disable=SC2086
  o="$("$AW" --data-dir "$T/data" --project-dir "$T/proj" $sub 2>&1)"
  [[ "$o" != *"Dynamic require"* && "$o" != *"at file://"* && "$o" != *"Cannot find module"* ]] && ok "aw $sub loads" || bad "aw $sub: ${o:0:200}"
done
printf 'פסקה ראשונה.\n\nפסקה שנייה.\n' > "$T/a.md"
python3 "$P/scripts/chunk-article.py" --input "$T/a.md" >/dev/null 2>"$T/e" && ok "built chunk-article.py finds config" || bad "chunk-article.py: $(tail -1 "$T/e")"
python3 "$P/scripts/gate.py" --help >/dev/null 2>"$T/e" && ok "built gate.py imports" || bad "gate.py: $(tail -1 "$T/e")"
for s in must-catch.py apply-changes.py citation-guard.py; do
  [[ -f "$P/scripts/$s" ]] || continue
  python3 "$P/scripts/$s" --help >/dev/null 2>"$T/e" && ok "built $s imports" || bad "$s: $(tail -1 "$T/e")"
done
tests=(); for t in test_hook_commands_resolve.py test_aw_binary_runs.py; do [[ -f "$ROOT/tests/$t" ]] && tests+=("$ROOT/tests/$t"); done
python3 -m pytest -q "${tests[@]}" >"$T/e" 2>&1 && ok "hook commands + binary tests (${#tests[@]} files)" || bad "hook/binary tests: $(tail -1 "$T/e")"

# aw docx makes no model calls, so run it for real: a 1-unit project in a path WITH A SPACE (a URL-encoded
# plugin path broke generate-docx on 2026-09-23), checking footnotes and that no markers leak.
DX="$T/docx project"; mkdir -p "$DX/.academic-helper/drafts"
printf '%s\n' '{"thesis":"t","thesisSha256":"x","sections":[{"id":"S1","title":"פרק","claim":"c","approved":true,"units":[{"id":"U1","dependsOn":[],"paragraphs":[{"move":"m","evidenceIds":[],"bridgeTo":""}]}]}]}' > "$DX/.academic-helper/outline.json"
printf 'פסקה ראשונה עם הערה.[^p1]\n\n[^p1]: מחבר, ספר, עמ׳ 3.\n' > "$DX/.academic-helper/drafts/U1.md"
if "$AW" --data-dir "$T/data" --project-dir "$DX" docx --outline "$DX/.academic-helper/outline.json" --run smoke-docx --out "$DX/out.docx" >"$T/e" 2>&1 \
   && python3 - "$DX/out.docx" <<'PY'
import sys, zipfile
z = zipfile.ZipFile(sys.argv[1]); d = z.read("word/document.xml").decode()
sys.exit(0 if "w:footnoteReference" in d and "[^" not in d else 1)
PY
then ok "aw docx builds a real .docx (path with space, native footnote)"; else bad "aw docx: $(tail -2 "$T/e")"; fi

if [[ "${1:-}" == "--live" ]]; then
  if [[ -z "${GOOGLE_API_KEY:-}" ]]; then bad "--live needs GOOGLE_API_KEY"; else
    F="$ROOT/evals/proofread-recall/fixture"; mkdir -p "$T/data/voice" "$T/out"; cp "$F/article.md" "$T/proj/article.md"
    [[ -f "$F/style-words.json" ]] && cp "$F/style-words.json" "$T/data/voice/style-words.json"
    [[ -f "$F/terms.json" ]] && cp "$F/terms.json" "$T/proj/.academic-helper/terms.json"
    "$AW" --data-dir "$T/data" --project-dir "$T/proj" proofread --run smoke-live --only mechanical --out "$T/out" "$T/proj/article.md" >/dev/null 2>"$T/e" || bad "live proofread: $(tail -1 "$T/e")"
    python3 "$ROOT/evals/graders/applied_recall.py" "$T/out/proofed.md" "$F/expected.json" && ok "live recall meets targets" || bad "live recall below targets"
  fi
fi
[[ $fail -eq 0 ]] && echo "SMOKE PASS" || echo "SMOKE FAIL"; exit $fail
