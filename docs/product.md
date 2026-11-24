# Product: Academic Writer

Draft by Claude, 2026-11-24, from README, CLAUDE.md, CHANGELOG and commits. Every `inferred:` line needs Yotam's answer.

## What
A Claude Code plugin that takes a Humanities researcher from a rough topic to a footnoted Word (.docx) article in
Hebrew or English: reads the researcher's chosen sources, settles a thesis and outline, drafts in the researcher's own
voice, checks every citation against the sources, then folds Word comments and tracked changes back into the text.
Sources: README.md, CLAUDE.md.

## For whom
- A single Humanities researcher (Jewish studies is the working domain) on a local machine, with no technical
  background. Plain words, ask before any install, Windows covered. Source: CLAUDE.md conventions, CHANGELOG 0.23.0.
- Since 0.18 the home folder also serves students (terms, courses, readings, deadlines) and lecturers/researchers.
  Source: CHANGELOG, src/scripts/home.py.
- inferred: the primary user is Yotam himself, with other researchers as secondary users (the repo is public and
  MIT-licensed, the site is bilingual).

## Why
- Drafts must keep the researcher's voice and never invent a citation: the auditor is the hard gate on every
  paragraph. Source: CLAUDE.md "Pipeline pattern".
- inferred: the goal is saving a researcher time on mechanical work, not replacing their argument; the researcher
  approves the thesis and outline and reviews the Word draft.

## Success
- Every cited claim traces to `sources.json` and passes external verification (the auditor VERDICT per paragraph).
- Numeric quality gates live only in `src/thresholds.json` and are enforced by code and tests.
- inferred: no usage metric exists; success is the researcher submitting an article they stand behind.

## Non-goals
- No team or multi-user workflows. Source: CLAUDE.md first lines.
- No PageIndex Cloud and no PageIndex API key; no cognetivy. Source: CLAUDE.md anti-patterns.
- No model calls from library or eval code except through the researcher's own `claude`/`codex`, and Gemini for
  PageIndex summaries and OCR. Source: CLAUDE.md anti-patterns.
- No writes outside the project folder, `${CLAUDE_PLUGIN_DATA}` and the researcher's chosen home folder.
- inferred: no hosted service, no accounts, no analytics.

## Quality bar
- Strict TypeScript (no `any`), deterministic pytest suite, CLI tests, structural tests, brand gate, privacy gate
  (`scripts/check-no-private-refs.sh`), a version-consistency gate. Source: CLAUDE.md, .github/workflows/ci.yml.
- Hebrew RTL first; light and dark themes; user-facing text for non-technical researchers.
- Cost: OCR and model routing keep paid calls minimal (Claude on the subscription first, cheap Gemini fallback).
- inferred: the bar for a drafted article is "an editor would not find an unsupported citation".
