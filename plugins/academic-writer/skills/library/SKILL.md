---
name: library
description: "One entry point for getting sources into the author's library and for judging it, run one phase at a time. Use when the author wants to upload a single article or chapter to Trove with its printed page numbers (ingest), upload a whole book, a multi-volume set, an EPUB or a scanned PDF with a navigable table of contents (ingest-book), turn a scan or photographed page into text (ocr), download the cited pages of a Kotar book as one PDF (kotar-fetch), or compare Trove and PageIndex on their own article (library-eval)."
user-invocable: true
argument-hint: "<phase> [args]"
allowed-tools: [Bash, Read, Write, Glob, AskUserQuestion]
metadata: {author: "Yotam Fromm", version: "0.1.0"}
---

# Academic Writer: the source library

This skill is a router. Pick one phase, read its file, and follow it. Load one phase file at a time; a phase may hand off to a sibling phase as rule 5 says.

## Phases

| Phase | When to use | File |
|---|---|---|
| `ingest` | Upload one article, paper or chapter to Trove with printed page numbers, a hinted table of contents and a citation guide | `phases/ingest.md` |
| `ingest-book` | Upload a whole book (100+ pages, multi-volume, EPUB or scanned PDF) with a nested navigable table of contents, or repair a flat one | `phases/ingest-book.md` |
| `ocr` | Turn a scanned PDF, photo or screenshot (or a folder of them) into plain text: `<file or folder>` | `phases/ocr.md` |
| `kotar-fetch` | Download the cited pages of a Kotar book as one PDF in printed-page order, for the author's own study | `phases/kotar-fetch.md` |
| `library-eval` | Compare Trove and PageIndex on the author's own article, judging anonymised A/B pairs | `phases/library-eval.md` |

## How to run

1. If the first word of the arguments is a phase in the table, that is the phase. Everything after it is the phase's arguments. This rule wins over every rule below.
2. No arguments at all (a bare `/academic-writer:library`): there is no default phase. Print the table and stop.
3. The arguments are a single bare word that is not in the table: print the table and stop.
4. Anything else is a request in the author's words, whose first word is not a phase: infer the phase from the request (a whole book or `.epub` is `ingest-book`, one article or chapter is `ingest`). If two phases fit, ask the author which one. Do not guess.
5. Read exactly one file, `${CLAUDE_SKILL_DIR}/phases/<phase>.md`, and follow it as if it were this skill's body. The one exception: when that phase names a sibling phase file of this router to continue with, read that file too, only at that point. The paths inside it that start with `${CLAUDE_SKILL_DIR}` or `${CLAUDE_PLUGIN_ROOT}` are already correct.

## Shared by the phases

`references/` holds what several phases read: the reading-page template, the existing-item and PageIndex indexing procedures, the ToC mechanism, the EPUB notes, the OCR engines and the judging page. A phase names the one it needs.
