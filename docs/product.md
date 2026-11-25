# Product: Academic Writer

Drafted by Claude, 2026-11-24, from README, CLAUDE.md, CHANGELOG and commits; Yotam answered the bootstrap questions on 2026-11-25.

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
- Yotam first, other Humanities researchers second (Yotam, 2026-11-25).

## Why
- Drafts must keep the researcher's voice and never invent a citation: the auditor is the hard gate on every
  paragraph. Source: CLAUDE.md "Pipeline pattern".
- The goal is saving a researcher time on mechanical work, never replacing their argument; the researcher
  approves the thesis and outline and reviews the Word draft.

## Success
- Every cited claim traces to `sources.json` and passes external verification (the auditor VERDICT per paragraph).
- Numeric quality gates live only in `src/thresholds.json` and are enforced by code and tests.
- Success is a submitted article written with it; its main purpose (Yotam, 2026-11-25).
- Metric: revision rounds per article, as few as possible, as the voice model improves over time. Other skills in the
  plugin may get their own metrics later; none exist yet.

## Non-goals
- No team or multi-user workflows. Source: CLAUDE.md first lines.
- No PageIndex Cloud and no PageIndex API key; no cognetivy. Source: CLAUDE.md anti-patterns.
- No model calls from library or eval code except through the researcher's own `claude`/`codex`, and Gemini for
  PageIndex summaries and OCR. Source: CLAUDE.md anti-patterns.
- No writes outside the project folder, `${CLAUDE_PLUGIN_DATA}` and the researcher's chosen home folder.
- No hosted service, no accounts, no analytics. Hebrew and English only. Humanities only.

## Quality bar
- Strict TypeScript (no `any`), deterministic pytest suite, CLI tests, structural tests, brand gate, privacy gate
  (`scripts/check-no-private-refs.sh`), a version-consistency gate. Source: CLAUDE.md, .github/workflows/ci.yml.
- Hebrew RTL first; light and dark themes; user-facing text for non-technical researchers.
- Cost: OCR and model routing keep paid calls minimal (Claude on the subscription first, cheap Gemini fallback).
- A drafted article passes when an editor would not find an unsupported citation.
