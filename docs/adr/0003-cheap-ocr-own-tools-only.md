# 0003. OCR reads with Claude first; model calls only through the researcher's own tools

Status: accepted (shipped 0.22.3). Source: docs/plans/2026-11-16-ocr-cheap-engines.md (local, gitignored),
commit 8e15db4, CLAUDE.md anti-patterns.

## Context
OCR cost money when Gemini read pages with thinking on; a stray project script also called a pro model.

## Decision
`aw ocr` reads scans with Claude on the subscription first, falls back to `gemini-3.8-flash` with thinking low only
for pages Claude cannot read, and has a per-run cost gate; a stronger reader needs `--confirm-cost`. Library and
eval code call no model except the researcher's own `claude`/`codex`; Gemini only for PageIndex summaries and OCR,
with the key given only to that child process.

## Rejected options
- Gemini 2.5 Flash without thinking: about 1.2% from the Claude text and scrambled glossary columns, against 0.25%.
- Re-measuring Sonnet as the Claude reader: Opus on the subscription costs no money.

## Consequences
- Paid pages are counted from reservations written before each request; one `aw ocr` per run id.
- Model routes live in `src/thresholds.json` (`models` block).
