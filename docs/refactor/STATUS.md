# academic-writer refactor: STATUS (2026-09-23, Mac lead)

**Branch:** `refactor/aw-step-engine` on origin, prepared as **0.14.0**. **Not merged to `main`, not released.**

## Tasks
| Task | State | Evidence |
|---|---|---|
| T1 runtime facts | accepted, merged | `docs/refactor/runtime-facts.md` (8 observed facts) |
| T2 construction fixes | accepted, merged | documented frontmatter keys, `omitClaudeMd` (about 20k tokens saved per subagent), no phantom agents |
| T3 measurement + eval | accepted, merged | `scripts/measure-run.py`, adversarial Hebrew fixture, context-anchored grader |
| T4 0.11.0 prep + install migration | accepted, merged | one user-scope install; 7 per-project installs removed (`docs/refactor/install-migration.md`) |
| T5 `aw` CLI core | accepted, merged | Gemini client with schema/finishReason checks, budgets, ledger, SessionStart key bridge |
| T6 judge providers | accepted, merged | isolated Pi/OpenRouter judge; Jev `decide()` (live call verified) |
| T7 proofread code core | accepted, merged | must-catch 14/14 on the fixture; geresh-aware guard; windowed anchoring |
| T8 proofread on `aw` | accepted, merged | live: names/terms 1.00, style 1.00, inside-quote 0, typo 0.77; 0 Claude tokens |
| T10 shared voice store | accepted, merged | the store in plugin data; `voice-sync.sh` backward-compatible |
| T11 evidence deep read | accepted, merged | verbatim-checked passages, cross-project source cache |
| T12 `/revise` docx loop | accepted, merged | reader exact on 3 real reviewed docx (every inserted/deleted character recovered) |
| T14 intent + outline v2 | accepted, merged (dev-server lead) | `gate.py outline-v2`, `aw decide` |
| T15a/T15b draft/synth/edit/ocr + MCP retirement | merged (lead-verified; split after ALE init) | live 2-unit draft: all gates pass, passage-id citations, predecessor bridge; live `aw edit` |
| F1 follow-ups, F2 rehearsal fixes | merged | F1: setup docs on `aw`, schemas shipped, wrong-word pass removed. F2: see the rehearsal section |
| T9/T13/T16 measure + release | **0.14.0 prepared, not released** | version-sync 6/6 agree; pytest 459; test:cli 55; smoke gate PASS (offline); `--live` FAILs only on typo 0.77 |

## /write rehearsal on real sources (2026-09-23, after the release hold)
A full live run of the new `/write` path, with the author's real kabalah thesis ("אשכנזי מאמץ את עקרונות הפיזיקה האריסטוטלית… אך את המעבר מן האין אל היש… בסוד קבלי") and two real CandleKeep sources: Ashkenazi's Kabbalah commentary as the core text, plus Sefer Yetzirah. The author's co-author approvals were simulated (thesis and section claims taken from the finished article).
- **Evidence** (`aw evidence build`): 25 verbatim-checked passages (the core text densely covered, including the opening dilemma), real titles and authors, the core text marked primary. About 113k input / 5k output Gemini tokens, ~45 s.
- **Draft** (`aw draft`), 7 units in dependency order with the intro and conclusion last: 2,552 words in about 75–92 s, ~31k in / 5k out Gemini tokens, **0 Claude tokens**. All gates pass after the fixes below. The style gate caught a banned phrase; `aw draft --unit … --feedback-file` redrafted that unit clean.
- **Synthesis** (`aw synthesize`): proposed 3 transition edits and applied 2; repeated paragraph openers dropped from 9 to 3.
- **Prose:** argues the thesis, gives each quotation its own analysis, and bridges units as planned. Remaining: "אני טוען כי" / "אינו רק X אלא Y" are overused. That is expected with the rehearsal's 2-exemplar test voice store; the author's real store (12–20 picked exemplars) is the fix. Verify it in the T16 pilot.
- **Defects the rehearsal found and fixed** (F2, all with tests), none of which a unit test had caught:
  - Gemini `RECITATION` abort on classical quotes. Quotes are now inserted by code from `⟦Q:id⟧` placeholders, verbatim by construction.
  - Model-chosen passage ids changed and collided on every rebuild. They are now stable content ids, and rebuilds merge.
  - The outline schema rejected the `role` field the drafter relies on.
  - Citations failed without a `sources.json`, and footnotes were model glosses; they are now rendered by code.
  - The quote gate misread acronym gershayim and inserted quotes; word bounds counted inserted quotes.
  - Synthesis saw the units in filename order and had no outline.

## /proofread measured through the REAL skill (headless, built plugin, 2026-09-23)
`claude -p --plugin-dir plugins/academic-writer "/academic-writer:proofread article.md --only mechanical"` on the 1,244-word fixture: 66.7 s, 53 changes, change-contract gate PASS, source untouched. **Claude usage: 304,229 tokens in total** (Sonnet, forked skill; `measure-run.py`, the same method as the 98.1M baseline). Recall is identical to the direct CLI runs (typo 0.77, names/terms 1.00, style 1.00, inside-quote 0). Scaled to the kabalah article's 2,338 words that is about 0.6M, against a ≤5M target: **the cost target is met with a wide margin** (the old path cost 98.1M). Fixed on the way: `--only mechanical|language` no longer bills the editorial memo.

## /write W6 in code: `aw docx` (F3, merged)
The main session no longer assembles the article: `aw docx` reads the drafts in outline order, turns `[^KEY]` markers into native Word footnotes rendered from evidence metadata, and runs `generate-docx.py`. The live rehearsal produced a real DOCX: 5 sections, 14 paragraphs, 8 footnotes, RTL, no leaked markers or placeholders. The live run caught one defect (a URL-encoded plugin path broke on the repo's space); the smoke gate now builds a real `.docx` in a path with a space on every run.

## `/revise` classify, live on the author's real reviewed draft (kabalah, 2026-09-23)
43 items (16 comments, 10 replacements, 17 inserts and deletes) classified in 96 s: 27 text_edit, 14 argument, 1 voice_signal ("אני לא אוהב את השימוש במילה הזאת בכלל", correct), 1 plugin_defect. Two misfiles show the author-confirmation step is needed: "דרוש הסבר" was filed as plugin_defect (it is content), and "אתה אמור להשתמש בתרגום של מקבילי לא של אבן תיבון" was filed as argument (it is a plugin source-choice defect). Worth adding: the reviewer's identity (supervisor vs author) as a classifier input, and a "source/translation choice" hint for plugin_defect.

## Needs the author
1. **Typo recall 0.77 vs 0.85:** Gemini flash misses real-word errors. Options: (a) accept; (b) a stronger model for the wrong_word class; (c) relax the apply gate for verified medium-risk wrong_word fixes.
2. **Release:** merge `refactor/aw-step-engine` to `main`, push, then `claude plugin marketplace update academic-writer` and `claude plugin update academic-writer@academic-writer`. This also approves the MCP server retirement.
3. **T16 pilot:** write one real paper with `/write` in a fresh session and measure it with `scripts/measure-run.py` against the target (≤40M Claude tokens). Run `/revise` on your Word comments afterwards.
4. **Dev server:** install and log in to Codex, add `GOOGLE_API_KEY` to the shell environment, install hspell.

## Follow-ups (small)
- `src/skills/setup/references/troubleshooting.md` still mentions the MCP server in later sections.
- `scripts/build-plugins.sh` does not ship `src/schemas/`; gate.py uses drift-tested copies.
- The wrong-word second finder pass (`proofread.wrongWordPass`) measured no gain; remove it or keep it off.
