#!/usr/bin/env python3
"""
build_crosswalk.py — Map every page of the *uploaded* combined book to its
Trove page number, per volume.

Why this exists (the core gotcha):
- Trove numbers pages sequentially from 1 (page 1 = your reading guide,
  page 2 = the first content page, ...). It also SKIPS source pages that
  cleaned to nothing, so the Trove page number != stored page number !=
  printed page number. You cannot eyeball this — you must derive it from
  the actual uploaded file.
- The ToC you'll attach later needs each entry's Trove page. This script
  produces the exact stored-number -> Trove map by enumerating the H1 page
  boundaries of the combined markdown, split per volume.

How volumes are detected:
- Each `# ` line starts a Trove page. A page whose header matches the
  page-label pattern ("<label> <number>") contributes "<number> -> <trove>".
- A new volume is detected when the stored number sequence RESETS (drops back
  to a small value), which is what happens at each volume's page 1. Volume
  divider pages (headers that don't match the page-label) are reported too.

Usage:
  python build_crosswalk.py COMBINED.md --out crosswalk.json \
      [--page-label "עמוד מקורי"]

Output JSON:
  {"total_ck_pages": N,
   "volumes": [
      {"volume": 1, "ck_first_content": 2, "stored_min": 1, "stored_max": 139,
       "stored_to_ck": {"1": 2, "2": 3, ...}}, ...],
   "dividers": [{"ck": 129, "title": "..."}, ...]}

To turn a PRINTED page number into a Trove page (the ToC speaks in printed
pages):
  1) Find this volume's offset once: pick a known ToC entry, e.g. "chapter
     starts printed p.15", read Trove pages until you find that content, say
     Trove page 13. Then stored_number = printed + (stored_of_anchor -
     printed_of_anchor).
  2) ck = stored_to_ck[str(printed + offset)]; interpolate if that exact stored
     number was skipped (see build_toc_enrich.py, which does this for you).

Always verify 2-3 anchors (first chapter, a famous mid-book section, the index)
against live content with `trove items read <id>:<ck>` before trusting the map.
"""
import argparse
import json
import re
import sys


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('combined')
    ap.add_argument('--page-label', default='עמוד מקורי')
    ap.add_argument('--out', required=True,
                    help='output JSON path (the caller chooses a safe location)')
    args = ap.parse_args(argv)

    try:
        with open(args.combined, encoding='utf-8') as f:
            content = f.read()
    except OSError as exc:
        print(f'error: cannot read {args.combined}: {exc}', file=sys.stderr)
        return 1

    try:
        pages = re.split(r'\n(?=# )', content)
        label_re = re.compile(r'^#\s+' + re.escape(args.page_label) + r'\s+(\d+)')

        volumes, dividers = [], []
        cur = None
        last_stored = None
        for ck, page in enumerate(pages, 1):
            head = page.split('\n', 1)[0]
            m = label_re.match(head)
            if not m:
                # non-content header: reading guide (ck 1) or a volume divider
                if ck != 1:
                    dividers.append({'ck': ck, 'title': head.lstrip('# ').strip()})
                continue
            stored = int(m.group(1))
            if cur is None or (last_stored is not None and stored < last_stored):
                cur = {'volume': len(volumes) + 1, 'ck_first_content': ck,
                       'stored_min': stored, 'stored_max': stored,
                       'stored_to_ck': {}}
                volumes.append(cur)
            cur['stored_to_ck'][str(stored)] = ck
            cur['stored_max'] = max(cur['stored_max'], stored)
            cur['stored_min'] = min(cur['stored_min'], stored)
            last_stored = stored

        result = {'total_ck_pages': len(pages), 'volumes': volumes,
                  'dividers': dividers}
        with open(args.out, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=1)
    except (OSError, ValueError) as exc:
        print(f'error: crosswalk failed: {exc}', file=sys.stderr)
        return 1

    print(f'Total pages: {len(pages)}')
    for v in volumes:
        print(f"  Vol {v['volume']}: stored {v['stored_min']}..{v['stored_max']} "
              f"-> CK {v['ck_first_content']}..{max(v['stored_to_ck'].values())} "
              f"({len(v['stored_to_ck'])} mapped)")
    for d in dividers:
        print(f"  divider @ CK {d['ck']}: {d['title']}")
    print(f'Saved {args.out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
