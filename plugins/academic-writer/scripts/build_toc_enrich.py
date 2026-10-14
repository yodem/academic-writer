#!/usr/bin/env python3
"""
build_toc_enrich.py — Assemble the navigable Trove ToC
and (optionally) apply it.

THE CENTRAL LESSON of this skill: Trove's sidebar/outline is driven by ToC
METADATA, set with `trove items enrich <id> --toc '[{"title","page","level"}]'`.
It is NOT built from markdown headings inside a page. If you cram the whole
table of contents into page 1 as ## / ### headings, every entry just links
back to page 1 — useless. The fix is this metadata, where each entry carries
the real Trove page it should jump to and a level (1-5) for nesting.

This script turns ToC-structure JSON (printed pages, with a mandatory ``hint``
field appended to each displayed title as ``title - hint``) + a crosswalk
(stored -> Trove page) into that metadata array, mapping each printed page to
its Trove page (interpolating when a stored page was skipped) and assigning a
nesting level by entry type. The entries JSON is what you write from the
`aw ocr` transcription of the book's ToC pages: a list of
``{"type", "label", "title", "page", "hint"}`` objects, one per ToC row, with
``page`` the PRINTED page and ``hint`` up to 3 sentences describing the
entry's content.

Inputs (via --config CONFIG.json):
  {
    "reading_guide_title": "מדריך קריאה ותוכן עניינים",   # the level-1 page-1 entry
    "appendix_prefix": "נספח",                            # optional, prefixes appendix labels
    "volumes": [
      {"title": "כרך א — ...",           # level-1 volume entry
       "divider_ck": 2,                  # Trove page the volume entry points to
       "offset": 2,                      # stored_number = printed + offset (find via anchors)
       "ocr": "/path/to/toc_entries_v1.json",  # your entries JSON for this volume
       "xwalk_volume": 1}                # which crosswalk volume to use (by "volume" field)
    ]
  }
  --crosswalk crosswalk.json   (output of build_crosswalk.py)
  --out toc_enrich.json
  --apply BOOK_ID              (optional: runs `trove items enrich --toc`)

Type -> level:
  volume=1, unit=2, section=3, subsection=4, subsubsection=5,
  appendix/frontmatter/endmatter=3.

Known harmless CLI quirk: with non-ASCII descriptions, `trove items enrich --toc`
prints "✓ Enriched" and THEN panics on a char-boundary while truncating the
description for display. The ToC is already written; ignore the panic and
verify with `trove items toc <id>`.
"""
import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

LEVEL = {'volume': 1, 'unit': 2, 'section': 3, 'subsection': 4,
         'subsubsection': 5, 'appendix': 3, 'frontmatter': 3, 'endmatter': 3}


def interp_ck(stored, stored_to_ck):
    """Trove page for a stored number, interpolating if that exact page was skipped."""
    key = str(stored)
    if key in stored_to_ck:
        return stored_to_ck[key]
    try:
        nums = sorted(int(k) for k in stored_to_ck)
    except ValueError as exc:
        raise SystemExit(
            f'error: crosswalk stored keys must be integers: {exc}') from exc
    below = [n for n in nums if n <= stored]
    above = [n for n in nums if n >= stored]
    if below and above:
        lo, hi = below[-1], above[0]
        if lo == hi:
            return stored_to_ck[str(lo)]
        lo_ck, hi_ck = stored_to_ck[str(lo)], stored_to_ck[str(hi)]
        frac = (stored - lo) / (hi - lo)
        return round(lo_ck + frac * (hi_ck - lo_ck))
    if below:
        return stored_to_ck[str(below[-1])]
    if above:
        return stored_to_ck[str(above[0])]
    return None


def display(entry, appendix_prefix):
    t = (entry.get('title') or '').strip()
    label = (entry.get('label') or '').strip().rstrip('.')
    typ = entry.get('type', '')
    if not t and label:
        t = label  # some rows carry their text in the label slot
        label = ''
    if not t:
        return None
    if typ == 'unit':
        return f'{label}: {t}' if label and not t.startswith(label) else t
    if typ == 'appendix' and label:
        pref = (appendix_prefix + ' ') if appendix_prefix else ''
        return f'{pref}{label}: {t}'
    if label:
        sep = '. ' if '.' not in label else ' '
        return f'{label}{sep}{t}'
    return t


def build_toc(cfg, xwalk):
    xwalk_by_vol = {v['volume']: v['stored_to_ck'] for v in xwalk['volumes']}
    appendix_prefix = cfg.get('appendix_prefix', '')

    toc = [{'title': cfg.get('reading_guide_title', 'Reading Guide & Contents'),
            'page': 1, 'level': 1}]

    for vol in cfg['volumes']:
        try:
            stored_to_ck = xwalk_by_vol[vol['xwalk_volume']]
            offset = vol.get('offset', 0)
            toc.append({'title': vol['title'], 'page': vol['divider_ck'], 'level': 1})
            with open(vol['ocr'], encoding='utf-8') as f:
                entries = json.load(f)
            for e in entries:
                page = e.get('page')
                if page is None:
                    continue
                ck = interp_ck(int(page) + offset, stored_to_ck)
                if ck is None:
                    continue
                disp = display(e, appendix_prefix)
                if not disp:
                    continue
                hint = (e.get('hint') or '').strip()
                if hint:
                    disp = f'{disp} - {hint}'
                toc.append({'title': disp, 'page': int(ck),
                            'level': LEVEL.get(e.get('type', ''), 3)})
        except (KeyError, ValueError, json.JSONDecodeError) as exc:
            print(f"error: volume '{vol.get('title', '?')}' has bad data: {exc}",
                  file=sys.stderr)
            raise SystemExit(1) from exc
    return toc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', required=True)
    ap.add_argument('--crosswalk', required=True)
    ap.add_argument('--out', required=True,
                    help='output JSON path (the caller chooses a safe location)')
    ap.add_argument('--apply', metavar='BOOK_ID', default=None)
    args = ap.parse_args(argv)

    try:
        cfg = json.loads(Path(args.config).read_text(encoding='utf-8'))
        xwalk = json.loads(Path(args.crosswalk).read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        print(f'error: cannot read config or crosswalk: {exc}', file=sys.stderr)
        return 1

    toc = build_toc(cfg, xwalk)

    try:
        with open(args.out, 'w', encoding='utf-8') as f:
            json.dump(toc, f, ensure_ascii=False)
    except OSError as exc:
        print(f'error: cannot write {args.out}: {exc}', file=sys.stderr)
        return 1
    print(f'{len(toc)} ToC entries -> {args.out}')
    print('levels:', dict(sorted(Counter(x['level'] for x in toc).items())))

    if args.apply:
        print(f'Applying to {args.apply} ...')
        r = subprocess.run(
            ['trove', 'items', 'enrich', args.apply, '--toc',
             Path(args.out).read_text(encoding='utf-8'), '--no-session'],
            capture_output=True, text=True)
        # The CLI prints ✓ then may panic on a Hebrew description-truncation bug.
        if '✓' in r.stdout or 'Enriched' in r.stdout:
            print('✓ Enriched (ignore any char-boundary panic that follows).')
        else:
            print('stdout:', r.stdout[-500:])
            print('stderr:', r.stderr[-500:])
        print('Verify with:  trove items toc', args.apply, '--no-session')
    return 0


if __name__ == '__main__':
    sys.exit(main())
