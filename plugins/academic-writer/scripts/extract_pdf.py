#!/usr/bin/env python3
"""
extract_pdf.py — Extract a scanned/large academic PDF into a Trove-ready
markdown file: one `# <page-label> N` H1 per source page, with DRM watermarks
and Unicode bidi markers stripped.

Why this exists:
- The Read tool fails on PDFs over ~100MB, and even smaller scanned books are
  cleaner to process as text. `pdftotext -layout` preserves column/line layout
  and separates pages with form-feed (\\f), which we split on.
- Scanned library PDFs are usually littered with per-page DRM watermarks
  ("File #... belongs to ...", long "__-_-_" rules, the borrower's email/name)
  and, for RTL languages, invisible Unicode bidi control characters. Both must
  be removed or they pollute every page and break agentic search.

Each `# ` H1 becomes one Trove (formerly CandleKeep) page, so the page label +
number you choose here is what the crosswalk and ToC builders key off later.

Usage:
  python extract_pdf.py INPUT.pdf OUTPUT.md \
      [--page-label "עמוד מקורי"]      # default; H1 becomes "# עמוד מקורי 17"
      [--first N] [--last N]           # optional page range
      [--extra-watermark "substr" ...] # extra literal substrings to drop
      [--drop-solo "Name" ...]         # drop lines equal to these (e.g. a
                                       # borrower name split across lines)
      [--keep-empty]                   # keep pages that clean to nothing

The number in the H1 is the PDF page index (1-based, within the selected range
offset by --first). That index is exact and is what build_crosswalk.py reads.
Mapping it to the book's *printed* page number happens later (see SKILL.md).
"""
import argparse
import contextlib
import os
import re
import subprocess
import sys
import tempfile

# Unicode bidi / zero-width controls that scanned RTL text embeds.
BIDI = ['‪', '‫', '‬', '‭', '‮',
        '‎', '‏', '​', '﻿', '⁦', '⁧', '⁨', '⁩']

# Default watermark fingerprints. These are LITERAL substrings; a line containing
# any of them is dropped entirely. Extend with --extra-watermark for your scan.
DEFAULT_WATERMARKS = [
    'belongs to', 'do not distribute', '__-_-_', 'CBBHCDEJJ',
    'atgmail.com', '@gmail.com',
]


def clean_page(text, watermarks, drop_solo):
    for ch in BIDI:
        text = text.replace(ch, '')
    out = []
    for line in text.split('\n'):
        if any(w in line for w in watermarks):
            continue
        if line.strip() in drop_solo:
            continue
        out.append(line.rstrip())
    cleaned = '\n'.join(out)
    # collapse 3+ blank lines to a single blank line
    return re.sub(r'\n{3,}', '\n\n', cleaned).strip()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('pdf')
    ap.add_argument('out')
    ap.add_argument('--page-label', default='עמוד מקורי',
                    help='Text before the page number in each H1 (default Hebrew "original page").')
    ap.add_argument('--first', type=int, default=None)
    ap.add_argument('--last', type=int, default=None)
    ap.add_argument('--extra-watermark', action='append', default=[])
    ap.add_argument('--drop-solo', action='append', default=[],
                    help='Lines equal to one of these (after strip) are dropped '
                         '(e.g. a borrower name split across lines).')
    ap.add_argument('--keep-empty', action='store_true')
    args = ap.parse_args(argv)

    if not os.path.exists(args.pdf):
        print(f'error: no such file: {args.pdf}', file=sys.stderr)
        return 1

    cmd = ['pdftotext', '-layout']
    if args.first:
        cmd += ['-f', str(args.first)]
    if args.last:
        cmd += ['-l', str(args.last)]
    with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as tf:
        tmp = tf.name
    cmd += [args.pdf, tmp]
    try:
        subprocess.run(cmd, check=True)
        with open(tmp, encoding='utf-8', errors='replace') as f:
            raw = f.read()
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f'error: pdftotext failed: {exc}', file=sys.stderr)
        return 1
    finally:
        contextlib.suppress(OSError)
        os.unlink(tmp)
    pages = raw.split('\f')

    watermarks = DEFAULT_WATERMARKS + args.extra_watermark
    base = (args.first or 1)
    md = []
    kept = 0
    for i, page in enumerate(pages):
        body = clean_page(page, watermarks, set(args.drop_solo))
        if not body and not args.keep_empty:
            continue
        n = base + i
        md.append(f'# {args.page_label} {n}\n\n{body}')
        kept += 1

    try:
        with open(args.out, 'w', encoding='utf-8') as f:
            f.write('\n\n'.join(md) + '\n')
    except OSError as exc:
        print(f'error: cannot write {args.out}: {exc}', file=sys.stderr)
        return 1
    print(f'Wrote {args.out}: {kept}/{len(pages)} pages kept '
          f'(label "{args.page_label}", numbers {base}..{base + len(pages) - 1}).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
