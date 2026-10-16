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
# aw library: no library.json means Trove only; status makes no Trove call, and the report on an empty project reads no ledger.
o="$("$AW" --data-dir "$T/data" --project-dir "$T/proj" library status 2>&1)"
[[ "$o" == *'"route":"trove"'* && "$o" == *'"configured":false'* ]] && ok "aw library status (no library.json: Trove only)" || bad "aw library status: ${o:0:200}"
o="$("$AW" --data-dir "$T/data" --project-dir "$T/proj" library report 2>&1)"
[[ "$o" == *"Library report"* && "$o" == *"No lookups are recorded yet"* && "$o" != *"Dynamic require"* ]] && ok "aw library report on an empty project" || bad "aw library report: ${o:0:200}"
[[ ! -e "$T/proj/.academic-helper/retrieval.jsonl" ]] && ok "an empty report writes no ledger" || bad "report created retrieval.jsonl"
# PageIndex built in: a dry-run install only describes itself (no folder, no pip, no network), the evaluation says in plain words
# that it has no plan yet, and pilib starts from the plugin's own copy of its source (it is also what `aw library index` probes).
o="$("$AW" --data-dir "$T/data" --project-dir "$T/proj" library install --dry-run 2>&1)"
[[ "$o" == *'"dry_run":true'* && "$o" == *'"steps"'* && "$o" != *"Dynamic require"* && "$o" != *"Cannot find module"* ]] && [[ ! -e "$T/data/pageindex" ]] \
  && ok "aw library install --dry-run (describes the install, writes nothing)" || bad "aw library install --dry-run: ${o:0:200}"
o="$("$AW" --data-dir "$T/data" --project-dir "$T/proj" library eval status --eval smoke-none 2>&1)"
[[ "$o" == *"no plan for smoke-none"* && "$o" != *"Dynamic require"* && "$o" != *"Cannot find module"* ]] && ok "aw library eval status (no plan yet, plain message)" || bad "aw library eval status: ${o:0:200}"
[[ ! -e "$T/proj/.academic-helper/library-eval" ]] && ok "eval status writes nothing" || bad "eval status created library-eval/"
if [[ -d "$P/scripts/pageindex/pilib" ]]; then
  PYTHONPATH="$P/scripts/pageindex" AW_LIBRARY="$T/pilib-library" python3 -m pilib --help >/dev/null 2>"$T/e" && ok "built pilib --help" || bad "pilib --help: $(tail -1 "$T/e")"
  PYTHONPATH="$P/scripts/pageindex" AW_LIBRARY="$T/pilib-library" python3 -m pilib index-trove --help >/dev/null 2>"$T/e" && ok "built pilib index-trove --help (the probe aw library index runs)" || bad "pilib index-trove --help: $(tail -1 "$T/e")"
  # --help never imports pilib.native (it loads lazily), so a shipped artifact missing a module would pass the lines above.
  # Import EVERY module the shipped pilib folder holds, from that folder only, then index a two-page book offline (hints, no
  # model, no network) and read a page back: this fails when a module or a file the helper needs did not ship.
  PYTHONPATH="$P/scripts/pageindex" AW_LIBRARY="$T/pilib-library" python3 - "$P/scripts/pageindex" >"$T/e" 2>&1 <<'PY' && ok "built pilib imports every shipped module (native, library, index, ...)" || bad "built pilib import: $(tail -1 "$T/e")"
import importlib, pkgutil, sys
import pilib, pilib.native, pilib.library
shipped = sys.argv[1]
if not pilib.__file__.startswith(shipped):
    sys.exit("pilib came from %s, not the shipped folder" % pilib.__file__)
names = [m.name for m in pkgutil.iter_modules(pilib.__path__)]
if not {"native", "library", "index", "summarize", "config", "meter"} <= set(names):
    sys.exit("shipped pilib is missing modules: have %s" % names)
for name in names:
    importlib.import_module("pilib." + name)
PY
  printf '# Page 1\n\nIntro text.\n\n# Page 2\n\nSecond page text.\n' > "$T/rt.md"
  printf '[{"title":"Intro","page":1,"level":1},{"title":"Second","page":2,"level":1}]' > "$T/rt-toc.json"
  if PYTHONPATH="$P/scripts/pageindex" AW_LIBRARY="$T/pilib-library" python3 -m pilib index-md --pages "$T/rt.md" --toc "$T/rt-toc.json" --book-id smoke --title Smoke --summaries hints >"$T/idx.json" 2>"$T/e" \
     && PYTHONPATH="$P/scripts/pageindex" AW_LIBRARY="$T/pilib-library" python3 -m pilib read smoke 2 --json >"$T/rd.json" 2>>"$T/e" \
     && python3 - "$T/idx.json" "$T/rd.json" <<'PY'
import json, sys
idx = json.load(open(sys.argv[1])); rd = json.load(open(sys.argv[2]))
ok = idx.get("ok") is True and idx.get("n_pages") == 2 and idx.get("nodes") == 2 and idx.get("calls") == 0
ok = ok and rd.get("book_id") == "smoke" and [p.get("page") for p in rd.get("pages", [])] == [2] and "Second page text." in rd["pages"][0]["content"]
sys.exit(0 if ok else 1)
PY
  then ok "built pilib index-md + read --json round trip (offline, temp library)"; else bad "built pilib round trip: $(tail -1 "$T/e") $(head -c 200 "$T/idx.json" 2>/dev/null)"; fi
  [[ -f "$P/scripts/pageindex/PINNED.json" ]] && ok "built PINNED.json ships" || bad "scripts/pageindex/PINNED.json missing from the built plugin"
else bad "scripts/pageindex/pilib missing from the built plugin"; fi
printf 'פסקה ראשונה.\n\nפסקה שנייה.\n' > "$T/a.md"
python3 "$P/scripts/chunk-article.py" --input "$T/a.md" >/dev/null 2>"$T/e" && ok "built chunk-article.py finds config" || bad "chunk-article.py: $(tail -1 "$T/e")"
python3 "$P/scripts/gate.py" --help >/dev/null 2>"$T/e" && ok "built gate.py imports" || bad "gate.py: $(tail -1 "$T/e")"
for s in must-catch.py apply-changes.py citation-guard.py; do
  [[ -f "$P/scripts/$s" ]] || continue
  python3 "$P/scripts/$s" --help >/dev/null 2>"$T/e" && ok "built $s imports" || bad "$s: $(tail -1 "$T/e")"
done
tests=(); for t in test_hook_commands_resolve.py test_aw_binary_runs.py test_library_e2e.py; do [[ -f "$ROOT/tests/$t" ]] && tests+=("$ROOT/tests/$t"); done
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
