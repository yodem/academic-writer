#!/usr/bin/env python3
"""Turn a Word file a professional editor returned into stable-ID edit operations.

Three steps, each deterministic and without any model call:

  extract   EDITED.docx [--original ORIGINAL.docx]
            Reads every tracked change in the body, the footnotes and the endnotes and writes
            <work>/extract/{units,ops,global}.json plus <work>/full-before.md and full-after.md.
            Text ops are a word-level diff between the paragraph with all changes rejected
            (BEFORE, the author's text) and accepted (AFTER, the editor's text). Formatting
            revisions and paragraph splits/merges are ops too; pure font-switch churn is
            collapsed into one count; wholly deleted and wholly inserted paragraphs are paired by
            fuzzy match; look-alike characters that changed (gershayim vs ", maqaf vs -, dashes)
            are named. With --original, the BEFORE text must equal the original file, else the
            baseline check reports where it differs.

  chunk     Splits the ops for analysis agents into <work>/chunks/: balanced text chunks of about
            110 ops that keep a paragraph and its footnotes together, one layout chunk
            (formatting and splits/merges), and auto-classified.json (blank-paragraph marks).

  coverage  Checks that every op id is classified exactly once across <work>/analysis/*.json and
            auto-classified.json. Exits non-zero on any missing, duplicated or unknown id.

  merge     Combines the synthesis agent's rules (<work>/synthesis/rules.json) with the skeptics'
            verdicts (<work>/synthesis/verdicts.json) and, optionally, the author's decisions into
            <work>/verified-catalogue.json and .md. Only the skeptic-verified wording of a rule is
            ever offered as rule text; the synthesis wording is kept as `original_rule` for audit.

Op ids (op-0001, op-0002, ...) follow the order extract finds the ops, so the same input always
gives the same ids. Python 3.9, standard library only.
"""
import argparse
import collections
import difflib
import hashlib
import json
import os
import re
import sys
import zipfile
from xml.etree import ElementTree as ET

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lib'))
import docx_revisions as dr  # noqa: E402

W = dr.W
DEFAULT_TARGET = 110
TEXT_KINDS = ('text', 'paragraph-inserted', 'paragraph-deleted', 'paragraph-rewrite-or-move')
LAYOUT_KINDS = ('paragraph-format', 'run-format', 'paragraph-mark')
AUTO_CATEGORY = 'layout-blank-paragraph'
SECTION_LIMIT = 90
PAIR_THRESHOLD = 0.45

UNI = {'״': 'HEB GERSHAYIM ״', '"': 'ASCII DOUBLE QUOTE "', '׳': 'HEB GERESH ׳',
       "'": "ASCII APOSTROPHE '", '־': 'HEB MAQAF ־', '-': 'HYPHEN-MINUS -',
       '–': 'EN DASH –', '—': 'EM DASH —', '“': 'LEFT CURLY QUOTE “',
       '”': 'RIGHT CURLY QUOTE ”', '’': 'RIGHT SINGLE QUOTE ’',
       '‘': 'LEFT SINGLE QUOTE ‘', ' ': 'NBSP', ' ': 'SPACE', '‏': 'RLM',
       '‎': 'LRM', '„': 'LOW DOUBLE QUOTE „', '‑': 'NON-BREAKING HYPHEN'}


# ------------------------------------------------------------------ text diff

def char_note(a, b):
    """Name the characters that differ when a short diff is about look-alike punctuation."""
    if len(a) > 40 or len(b) > 40:
        return None
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    notes = []

    def name(chars):
        return ', '.join(UNI.get(c, 'U+%04X %s' % (ord(c), c)) for c in chars) or '∅'

    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == 'equal':
            continue
        x, y = a[i1:i2], b[j1:j2]
        if all(c.isalnum() for c in x + y):
            continue
        if all(ch in UNI for ch in x + y) or (op == 'replace' and len(x) == len(y) == 1):
            notes.append('{}: [{}] -> [{}]'.format(op, name(x), name(y)))
    return '; '.join(notes) or None


def wdiff(a, b):
    """Word-level diff of two strings: a list of op dicts with a little surrounding context."""
    aw = re.findall(r'\S+|\s+', a)
    bw = re.findall(r'\S+|\s+', b)
    ops = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, aw, bw, autojunk=False).get_opcodes():
        if op != 'equal':
            ops.append({'op': op, 'before': ''.join(aw[i1:i2]), 'after': ''.join(bw[j1:j2]),
                        'chars': char_note(''.join(aw[i1:i2]), ''.join(bw[j1:j2])),
                        'ctx_before': ''.join(aw[max(0, i1 - 14):i1])[-90:],
                        'ctx_after': ''.join(aw[i2:i2 + 14])[:90]})
    return ops


def plain_lines(root, kind='body'):
    """Accepted-text lines of every paragraph of a body part, markup and note markers removed."""
    lines = []
    for p in dr.body_paragraphs(root):
        lines.append(dr.strip_markup(dr.paragraph_views(p, markup=False)[1]))
    return lines


def note_texts(root, kind):
    """Reject-all text of each note (paragraphs joined by newline), in file order."""
    out = []
    for _, el in dr.notes(root, kind):
        out.append('\n'.join(dr.paragraph_views(p, markup=False)[0] for p in el.iter(W + 'p')))
    return out


# ------------------------------------------------------------------ extract

def read_units(zf, churn_arg, churn_min):
    roots = dr.load_roots(zf)
    if 'body' not in roots:
        raise SystemExit('ERROR: no word/document.xml in the edited file')
    all_p = dr.body_paragraphs(roots['body'])
    for kind in ('footnote', 'endnote'):
        if kind in roots:
            for _, el in dr.notes(roots[kind], kind):
                all_p += list(el.iter(W + 'p'))
    if churn_arg == 'none':
        churn = None
    elif churn_arg:
        churn = churn_arg
    else:
        churn = dr.detect_churn_font(all_p, churn_min)
    counter = collections.Counter()
    state = {'page': 1}
    paras = []
    section = '(front matter)'
    for idx, p in enumerate(dr.body_paragraphs(roots['body'])):
        page = state['page']
        before, after, refs = dr.paragraph_views(p, state)
        style = dr.paragraph_style(p)
        if dr.is_heading_style(style) and after.strip():
            section = dr.MARK_RE.sub('', dr.strip_markup(after)).strip()[:SECTION_LIMIT] or section
        pf = dr.para_format_op(p)
        paras.append({'part': 'body', 'idx': idx, 'page': page, 'style': style, 'section': section,
                      'before': before, 'after': after, 'fnrefs': refs,
                      'text_changed': dr.has_text_change(p), 'para_mark': dr.para_mark(p),
                      'run_fmt': [{'delta': o['delta'], 'text': o['text']}
                                  for o in dr.run_format_ops(p, counter, churn)],
                      'para_fmt': pf['delta'] if pf else None})
    cited = {}
    for p in paras:
        for ref in p['fnrefs']:
            cited.setdefault(ref, (p['page'], p['idx'], p['section']))
    notes = []
    for kind in ('footnote', 'endnote'):
        if kind not in roots:
            continue
        for nid, el in dr.notes(roots[kind], kind):
            bs, as_, rf, pf_, marks, changed = [], [], [], [], [], False
            for p in el.iter(W + 'p'):
                before, after, _ = dr.paragraph_views(p)
                as_.append(after)
                bs.append(before)
                rf += [{'delta': o['delta'], 'text': o['text']} for o in dr.run_format_ops(p, counter, churn)]
                pf = dr.para_format_op(p)
                if pf:
                    pf_.append(pf['delta'])
                if dr.para_mark(p):
                    marks.append(dr.para_mark(p))
                changed = changed or dr.has_text_change(p)
            key = '{}:{}'.format(kind, nid)
            page, anchor, section_ = cited.get(key, (None, None, '(not cited in the body)'))
            notes.append({'part': kind, 'id': nid, 'unit': key, 'page': page, 'anchor_para': anchor,
                          'section': section_, 'before': '\n'.join(bs), 'after': '\n'.join(as_),
                          'text_changed': changed, 'run_fmt': rf, 'para_fmt': '; '.join(pf_) or None,
                          'para_mark': '; '.join(marks)})
    return roots, paras, notes, counter, churn


def pair_paragraphs(paras):
    """Pair each wholly deleted paragraph with its most similar wholly inserted one (rewrite or move)."""
    dels = [p for p in paras if p['before'].strip() and not p['after'].strip()]
    inss = [p for p in paras if p['after'].strip() and not p['before'].strip()]
    used = set()
    for d in dels:
        best, score = None, 0.0
        d_words = set(re.findall(r'\w{3,}', d['before']))
        for i in inss:
            if i['idx'] in used:
                continue
            s = difflib.SequenceMatcher(None, d['before'], i['after'], autojunk=False).ratio()
            # cheap token overlap boost for reordered entries (bibliographies)
            shared = d_words & set(re.findall(r'\w{3,}', i['after']))
            s = max(s, len(shared) / max(1, len(d_words)))
            if s > score:
                best, score = i, s
        if best is not None and score >= PAIR_THRESHOLD:
            used.add(best['idx'])
            d['paired_with'] = best['idx']
            best['paired_with'] = d['idx']
            d['pair_score'] = round(score, 2)


def build_ops(paras, notes):
    ops = []

    def add(kind, unit, **kw):
        ops.append(dict(kw, id='op-{:04d}'.format(len(ops) + 1), kind=kind, unit=unit))

    byidx = {p['idx']: p for p in paras}
    for p in paras:
        unit = 'body:{}'.format(p['idx'])
        if 'paired_with' in p and p['before'].strip() and not p['after'].strip():
            other = byidx[p['paired_with']]
            add('paragraph-rewrite-or-move', unit, page=p['page'], before=p['before'], after=other['after'],
                note='deleted para {} paired with inserted para {} (similarity {})'.format(
                    p['idx'], other['idx'], p['pair_score']),
                diff=wdiff(p['before'], other['after']))
        elif 'paired_with' in p:
            pass  # the inserted half of a pair, already emitted with the deleted half
        elif p['before'] != p['after']:
            if not p['after'].strip():
                add('paragraph-deleted', unit, page=p['page'], before=p['before'], after='')
            elif not p['before'].strip():
                add('paragraph-inserted', unit, page=p['page'], before='', after=p['after'])
            else:
                for x in wdiff(p['before'], p['after']):
                    add('text', unit, page=p['page'], **x)
        if p['para_mark']:
            add('paragraph-mark', unit, page=p['page'], note=p['para_mark'], text=p['after'][:120])
        if p['para_fmt']:
            add('paragraph-format', unit, page=p['page'], delta=p['para_fmt'], style=p['style'],
                text=p['after'][:120])
        for r in p['run_fmt']:
            add('run-format', unit, page=p['page'], delta=r['delta'], text=r['text'][:200])
    for n in notes:
        unit = n['unit']
        if n['before'] != n['after']:
            for x in wdiff(n['before'], n['after']):
                add('text', unit, page=n['page'], **x)
        if n['para_mark']:
            add('paragraph-mark', unit, page=n['page'], note=n['para_mark'])
        if n['para_fmt']:
            add('paragraph-format', unit, page=n['page'], delta=n['para_fmt'])
        for r in n['run_fmt']:
            add('run-format', unit, page=n['page'], delta=r['delta'], text=r['text'][:200])
    return ops


def package_facts(zf):
    """Page setup facts from the last section properties of the body."""
    root = ET.fromstring(zf.read('word/document.xml'))
    sect = None
    for el in root.iter(W + 'sectPr'):
        sect = el
    facts = {}
    if sect is not None:
        for name in ('pgNumType', 'pgSz', 'pgMar', 'titlePg', 'cols'):
            el = sect.find(W + name)
            if el is not None:
                facts[name] = {k.replace(W, ''): v for k, v in sorted(el.attrib.items())}
    return facts


def untracked_part_differences(edited, original):
    """Names of word/ parts (styles, settings, headers, footers...) that differ between the two files.

    These changes carry no revision mark, so an editor can change them silently. Story parts, relationship files
    and embedded fonts are skipped.
    """
    skip = {'word/document.xml', 'word/footnotes.xml', 'word/endnotes.xml', 'word/comments.xml'}
    out = []
    on, oo = set(edited.namelist()), set(original.namelist())
    for name in sorted(on | oo):
        if not name.startswith('word/') or name in skip or name.endswith('.rels') or name.startswith('word/fonts/'):
            continue
        if name not in on or name not in oo:
            out.append(name + (' (only in edited)' if name in on else ' (only in original)'))
        elif hashlib.sha256(edited.read(name)).digest() != hashlib.sha256(original.read(name)).digest():
            out.append(name)
    return out


def baseline_check(roots, paras, notes, original_zf):
    """Compare the reject-all text with the original file. Returns (body diffs, note diffs, cmp notes)."""
    oroots = dr.load_roots(original_zf)
    orig = [l for l in plain_lines(oroots['body']) if l.strip()]
    rej, carry = [], ''
    for p in paras:  # rejecting an inserted paragraph mark merges the paragraph with the next one
        text = carry + dr.strip_markup(p['before'])
        carry = text if p['para_mark'].startswith('paragraph-mark-inserted') else ''
        if not carry and text.strip():
            rej.append(text)
    if carry.strip():
        rej.append(carry)
    clean = lambda lines: dr.MARK_RE.sub('', '\n'.join(lines))  # noqa: E731
    body = wdiff(clean(orig), clean(rej))
    note_diffs = []
    for kind in ('footnote', 'endnote'):
        if kind not in oroots:
            continue
        o_notes = [t for t in note_texts(oroots[kind], kind) if t.strip()]
        e_notes = [dr.strip_markup(n['before']) for n in notes if n['part'] == kind and n['before'].strip()]
        # a paragraph split inside a note differs from the original only by whitespace
        squash = lambda texts: re.sub(r'\s+', ' ', ' '.join(texts)).strip()  # noqa: E731
        note_diffs += wdiff(squash(o_notes), squash(e_notes))
    return body, note_diffs


def write_json(path, data):
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
        fh.write('\n')


def cmd_extract(args):
    work = args.work
    out = os.path.join(work, 'extract')
    os.makedirs(out, exist_ok=True)
    with zipfile.ZipFile(args.edited) as zf:
        roots, paras, notes, counter, churn = read_units(zf, args.churn_font, args.churn_min)
        pair_paragraphs(paras)
        ops = build_ops(paras, notes)
        facts = package_facts(zf)
        glob = {'global_format': dict(counter), 'churn_font': churn,
                'edited_page_setup': facts, 'baseline_checked': False,
                'baseline_diff_count': None, 'baseline_diffs_vs_original': [],
                'baseline_note_diff_count': None, 'baseline_note_diffs_vs_original': [],
                'untracked_part_differences': []}
        base = base_notes = None
        if args.original:
            with zipfile.ZipFile(args.original) as oz:
                base, base_notes = baseline_check(roots, paras, notes, oz)
                glob['original_page_setup'] = package_facts(oz)
                glob['untracked_part_differences'] = untracked_part_differences(zf, oz)
            glob.update({'baseline_checked': True, 'baseline_diff_count': len(base),
                         'baseline_diffs_vs_original': base[:200],
                         'baseline_note_diff_count': len(base_notes),
                         'baseline_note_diffs_vs_original': base_notes[:200]})
    write_json(os.path.join(out, 'units.json'), {'paragraphs': paras, 'notes': notes})
    write_json(os.path.join(out, 'ops.json'), ops)
    write_json(os.path.join(out, 'global.json'), glob)
    for name, field in (('full-before.md', 'before'), ('full-after.md', 'after')):
        with open(os.path.join(work, name), 'w', encoding='utf-8') as fh:
            for p in paras:
                if p[field].strip():
                    fh.write('[body:{}] {}\n\n'.format(p['idx'], p[field]))
            for n in notes:
                if n[field].strip():
                    fh.write('[{}] {}\n\n'.format(n['unit'], n[field]))
    kinds = collections.Counter(o['kind'] for o in ops)
    print('ops {} {}'.format(len(ops), dict(sorted(kinds.items()))))
    print('global {}'.format(dict(counter)))
    if base is None:
        print('baseline: not checked (pass --original to compare with the original file)')
    else:
        print('baseline diffs vs original, body: {}, notes: {}'.format(len(base), len(base_notes)))
        for x in (base + base_notes)[:15]:
            print('  {} {!r} -> {!r}'.format(x['op'], x['before'][:80], x['after'][:80]))
    if glob['untracked_part_differences']:
        print('parts changed without tracking: ' + ', '.join(glob['untracked_part_differences']))
    print('wrote ' + out)
    if args.strict and (base or base_notes):
        return 1
    return 0


# ------------------------------------------------------------------ chunk

def load_extract(work):
    out = os.path.join(work, 'extract')
    try:
        with open(os.path.join(out, 'ops.json'), encoding='utf-8') as fh:
            ops = json.load(fh)
        with open(os.path.join(out, 'units.json'), encoding='utf-8') as fh:
            units = json.load(fh)
        with open(os.path.join(out, 'global.json'), encoding='utf-8') as fh:
            glob = json.load(fh)
    except (OSError, ValueError) as exc:
        raise SystemExit('ERROR: cannot read {} ({}); run `extract` first'.format(out, exc))
    return ops, units, glob


def is_auto(op):
    """A paragraph mark on a body paragraph with no text: a blank line added or removed."""
    return (op['kind'] == 'paragraph-mark' and op['unit'].startswith('body:')
            and 'text' in op and not op['text'].strip())


def unit_groups(units, ops_by_unit):
    """Body paragraphs in document order, each followed by the notes it cites; notes that are
    cited nowhere come last. Every group is (list of unit keys, count of text ops)."""
    notes_by_anchor = collections.OrderedDict()
    orphans = []
    for n in units['notes']:
        if n['anchor_para'] is None:
            orphans.append(n['unit'])
        else:
            notes_by_anchor.setdefault(n['anchor_para'], []).append(n['unit'])
    groups = []
    for p in units['paragraphs']:
        keys = ['body:{}'.format(p['idx'])] + notes_by_anchor.get(p['idx'], [])
        groups.append(keys)
    if orphans:
        groups.append(orphans)
    out = []
    for keys in groups:
        count = sum(1 for k in keys for o in ops_by_unit.get(k, []) if o['kind'] in TEXT_KINDS)
        if count:
            out.append((keys, count))
    return out


def balance(groups, target):
    """Assign groups to n chunks of about ``target`` ops each, never splitting a group."""
    total = sum(c for _, c in groups)
    n = max(1, int(round(total / float(target))))
    size = total / float(n)
    chunks = [[] for _ in range(n)]
    done = 0.0
    for keys, count in groups:
        slot = min(n - 1, int((done + count / 2.0) / size))
        chunks[slot].append((keys, count))
        done += count
    return [c for c in chunks if c]


def quote(text):
    return '\n'.join('> ' + line for line in (text.split('\n') if text else ['']))


def op_line(o):
    ctx = '⟨…{}⟦HERE⟧{}…⟩'.format(
        (o.get('ctx_before') or '').replace('\n', '⏎'), (o.get('ctx_after') or '').replace('\n', '⏎'))
    if o['kind'] == 'text':
        chars = '  chars: ' + o['chars'] if o.get('chars') else ''
        return '- **{}** {}: «{}» → «{}»{}  {}'.format(
            o['id'], o['op'], o['before'], o['after'], chars, ctx)
    head = '- **{}** {}: {}'.format(o['id'], o['kind'], o.get('note', ''))
    return '{}\n  BEFORE: {}\n  AFTER: {}'.format(head, o.get('before', ''), o.get('after', ''))


def unit_record(units, key):
    if key.startswith('body:'):
        return units['paragraphs'][int(key.split(':')[1])]
    for n in units['notes']:
        if n['unit'] == key:
            return n
    raise KeyError(key)


def write_text_chunk(path, label, index, total, keys, units, ops_by_unit):
    lines = ['# Text-edit chunk {}/{}'.format(index, total), '',
             'Units in document order. For each unit: full BEFORE (author) and AFTER (editor) text, then '
             'every op with its stable id. Inline formatting is shown as <i>…</i>, <b>…</b>, '
             '<sup>…</sup>. `chars:` names look-alike characters that changed. A note is shown '
             'right after the paragraph that cites it.', '']
    ids = []
    for key in keys:
        uops = [o for o in ops_by_unit.get(key, []) if o['kind'] in TEXT_KINDS]
        if not uops:
            continue
        rec = unit_record(units, key)
        lines += ['', '---', '## {} — page≈{} — section: {}'.format(
            key, rec.get('page'), rec.get('section') or '(none)'), '',
            'BEFORE:', quote(rec['before']), '', 'AFTER:', quote(rec['after']), '', 'OPS:']
        for o in uops:
            lines.append(op_line(o))
            ids.append(o['id'])
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines) + '\n')
    return ids


def write_layout_chunk(path, layout_ops, auto_ops, units, glob):
    pages = collections.Counter(o.get('page') for o in auto_ops)
    lines = ['# Layout / formatting chunk', '',
             'Delta strings read OLD to NEW: `+x` the editor added property x, `-x` removed it, '
             '`~x(a)->(b)` changed it. `paragraph-mark` is a paragraph split (inserted mark) or merge '
             '(deleted mark).', '',
             'Global: {} (runs whose only change was switching to the dominant font; collapsed).'.format(
                 json.dumps(glob.get('global_format', {}), ensure_ascii=False)), '']
    if glob.get('baseline_checked'):
        lines += ['Page setup, original: {}'.format(json.dumps(glob.get('original_page_setup', {}))),
                  'Page setup, edited: {}'.format(json.dumps(glob.get('edited_page_setup', {}))),
                  'Package parts that differ without tracking (compare them yourself): {}'.format(
                      ', '.join(glob.get('untracked_part_differences', [])) or 'none'), '']
    else:
        lines += ['Page setup, edited: {}'.format(json.dumps(glob.get('edited_page_setup', {}))), '']
    lines += ['Also {} empty paragraph marks (blank lines added or removed) were auto-classified '
              'into auto-classified.json; by page: {}'.format(
                  len(auto_ops), json.dumps({str(k): v for k, v in sorted(pages.items(), key=lambda kv: (kv[0] is None, kv[0]))})), '']
    for o in layout_ops:
        rec = unit_record(units, o['unit'])
        detail = o.get('delta') or o.get('note', '')
        lines.append('- **{}** {} [{} page≈{} section: {}] {} — style={} — text: «{}»'.format(
            o['id'], o['kind'], o['unit'], o.get('page'), rec.get('section') or '(none)', detail,
            o.get('style') or rec.get('style', ''), o.get('text', '')))
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines) + '\n')


def cmd_chunk(args):
    work = args.work
    ops, units, glob = load_extract(work)
    out = os.path.join(work, 'chunks')
    os.makedirs(out, exist_ok=True)
    for name in os.listdir(out):  # stale chunks from an earlier run would break coverage
        if name.endswith(('.md', '.ids.json')) or name in ('auto-classified.json', 'manifest.json'):
            os.remove(os.path.join(out, name))
    ops_by_unit = collections.OrderedDict()
    for o in ops:
        ops_by_unit.setdefault(o['unit'], []).append(o)
    auto_ops = [o for o in ops if is_auto(o)]
    layout_ops = [o for o in ops if o['kind'] in LAYOUT_KINDS and not is_auto(o)]
    groups = unit_groups(units, ops_by_unit)
    chunks = balance(groups, args.target_ops)
    manifest = []
    placed = []
    for i, chunk in enumerate(chunks, 1):
        name = 'text-{:02d}'.format(i)
        keys = [k for g, _ in chunk for k in g]
        ids = write_text_chunk(os.path.join(out, name + '.md'), name, i, len(chunks), keys, units, ops_by_unit)
        write_json(os.path.join(out, name + '.ids.json'), ids)
        placed += ids
        manifest.append({'name': name, 'ops': len(ids)})
    write_layout_chunk(os.path.join(out, 'layout.md'), layout_ops, auto_ops, units, glob)
    write_json(os.path.join(out, 'layout.ids.json'), [o['id'] for o in layout_ops])
    manifest.append({'name': 'layout', 'ops': len(layout_ops)})
    auto = [{'id': o['id'], 'category': AUTO_CATEGORY,
             'rule_candidate': 'blank paragraph ' + ('inserted' if 'inserted' in o['note'] else 'removed'),
             'auto': True, 'page': o.get('page')} for o in auto_ops]
    write_json(os.path.join(out, 'auto-classified.json'), auto)
    covered = set(placed) | {o['id'] for o in layout_ops} | {o['id'] for o in auto_ops}
    lost = [o['id'] for o in ops if o['id'] not in covered]
    write_json(os.path.join(out, 'manifest.json'),
               {'total_ops': len(ops), 'auto_classified': len(auto), 'chunks': manifest, 'unplaced': lost})
    print('chunks: ' + ', '.join('{}={}'.format(m['name'], m['ops']) for m in manifest)
          + ', auto-classified={}'.format(len(auto)))
    if lost:
        print('ERROR: {} ops not placed in any chunk: {}'.format(len(lost), lost[:10]))
        return 1
    return 0


# ------------------------------------------------------------------ coverage

def cmd_coverage(args):
    work = args.work
    ops, _, _ = load_extract(work)
    expected = [o['id'] for o in ops]
    seen = collections.defaultdict(list)
    problems = []
    adir = os.path.join(work, 'analysis')
    files = sorted(f for f in os.listdir(adir) if f.endswith('.json')) if os.path.isdir(adir) else []
    if not files:
        problems.append('no analysis/*.json files in ' + adir)
    for f in files:
        try:
            with open(os.path.join(adir, f), encoding='utf-8') as fh:
                rows = json.load(fh)
        except (OSError, ValueError) as exc:
            problems.append('{}: not valid JSON ({})'.format(f, exc))
            continue
        if not isinstance(rows, list):
            problems.append('{}: expected a JSON array of {{"id", ...}} objects'.format(f))
            continue
        for row in rows:
            rid = row.get('id') if isinstance(row, dict) else None
            if not rid:
                problems.append('{}: entry without an id'.format(f))
            else:
                seen[rid].append(f)
    auto_path = os.path.join(work, 'chunks', 'auto-classified.json')
    if os.path.exists(auto_path):
        with open(auto_path, encoding='utf-8') as fh:
            for row in json.load(fh):
                seen[row['id']].append('auto-classified.json')
    known = set(expected)
    missing = [i for i in expected if i not in seen]
    duplicated = {i: v for i, v in seen.items() if len(v) > 1}
    unknown = sorted(i for i in seen if i not in known)
    result = {'total_ops': len(expected), 'classified': len(known & set(seen)),
              'missing': missing, 'duplicated': duplicated, 'unknown': unknown, 'problems': problems}
    result['ok'] = not (missing or duplicated or unknown or problems)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=1))
    else:
        print('{}/{} ops classified'.format(result['classified'], result['total_ops']))
        if missing:
            print('MISSING ({}): {}'.format(len(missing), ', '.join(missing[:30]) + (' ...' if len(missing) > 30 else '')))
        if duplicated:
            print('DUPLICATED ({}): {}'.format(len(duplicated), ', '.join(
                '{} in {}'.format(i, '+'.join(v)) for i, v in list(duplicated.items())[:15])))
        if unknown:
            print('UNKNOWN ids ({}): {}'.format(len(unknown), ', '.join(unknown[:30])))
        for p in problems:
            print('PROBLEM: ' + p)
        print('coverage OK' if result['ok'] else 'coverage FAILED')
    return 0 if result['ok'] else 1


# ------------------------------------------------------------------ merge

USABLE = {'confirmed': 'verified', 'narrow': 'verified', 'reclassify': 'verified'}


def read_json(path, what):
    try:
        with open(path, encoding='utf-8') as fh:
            return json.load(fh)
    except (OSError, ValueError) as exc:
        raise SystemExit('ERROR: cannot read {} ({}): {}'.format(what, path, exc))


def merge_rules(rules, verdicts, decisions):
    """Return (catalogue, problems). A rule is usable only with a skeptic verdict of confirmed,
    narrow or reclassify; narrow and reclassify need the restated rule (`corrected_rule`)."""
    by_id = {}
    problems = []
    for v in verdicts:
        if v.get('id') in by_id:
            problems.append('duplicate verdict for ' + str(v.get('id')))
        by_id[v.get('id')] = v
    known = {r.get('id') for r in rules}
    for rid in sorted(set(by_id) - known, key=str):
        problems.append('verdict for unknown rule ' + str(rid))
    catalogue = []
    for r in rules:
        v = by_id.get(r['id'])
        row = {k: r.get(k) for k in ('id', 'group', 'title', 'tier', 'evidence_count', 'op_ids',
                                     'examples', 'consistency', 'plugin_target', 'regex_hint', 'conflicts')
               if k in r}
        row['original_rule'] = r.get('rule', '')
        if v is None:
            row.update(status='unverified', verdict=None, verified_rule=None)
            problems.append('no verdict for ' + r['id'])
        else:
            verdict = v.get('verdict')
            row.update(verdict=verdict, skeptic_reason=v.get('reason', ''),
                       applied_count=v.get('applied_count'), left_unchanged_count=v.get('left_unchanged_count'),
                       false_positive_risk=v.get('false_positive_risk', ''))
            if verdict == 'refuted':
                row.update(status='refuted', verified_rule=None)
            elif verdict == 'confirmed':
                row.update(status='verified', verified_rule=r.get('rule', ''))
            elif verdict in ('narrow', 'reclassify') and (v.get('corrected_rule') or '').strip():
                row.update(status='verified', verified_rule=v['corrected_rule'].strip())
            else:
                row.update(status='needs-restatement', verified_rule=None)
                problems.append('{}: verdict {!r} without corrected_rule'.format(r['id'], verdict))
        d = decisions.get(r['id'])
        if d is not None:
            if row['status'] != 'verified':
                problems.append('{}: decision recorded for a rule that is {}'.format(r['id'], row['status']))
            row['decision'] = d
        catalogue.append(row)
    return catalogue, problems


def cmd_merge(args):
    work = args.work
    sdir = os.path.join(work, 'synthesis')
    rules = read_json(os.path.join(sdir, 'rules.json'), 'synthesis rules')
    verdicts = read_json(os.path.join(sdir, 'verdicts.json'), 'skeptic verdicts')
    decisions = {}
    if args.decisions:
        decisions = read_json(args.decisions, 'author decisions')
    catalogue, problems = merge_rules(rules, verdicts, decisions)
    write_json(os.path.join(work, 'verified-catalogue.json'), catalogue)
    counts = collections.Counter(r['status'] for r in catalogue)
    lines = ['# Verified rule catalogue', '',
             'Only the skeptic-verified wording is shown. Status counts: ' + json.dumps(dict(counts)), '']
    for r in catalogue:
        if r['status'] != 'verified':
            continue
        lines += ['## {} \u2014 {} ({}, {})'.format(r['id'], r.get('title', ''), r.get('group', ''), r.get('tier', '')),
                  '', r['verified_rule'], '',
                  'Verdict: {}. Applied {}, left unchanged {}. {}'.format(
                      r['verdict'], r.get('applied_count'), r.get('left_unchanged_count'), r.get('skeptic_reason', '')),
                  'False-positive risk: ' + (r.get('false_positive_risk') or 'not assessed')]
        if 'decision' in r:
            lines.append('Author decision: ' + json.dumps(r['decision'], ensure_ascii=False))
        lines.append('')
    with open(os.path.join(work, 'verified-catalogue.md'), 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines) + '\n')
    print('rules {}: {}'.format(len(catalogue), dict(counts)))
    for p in problems:
        print('PROBLEM: ' + p)
    return 1 if problems and args.strict else 0


# ------------------------------------------------------------------ cli

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='cmd', required=True)
    work_help = 'working folder holding extract/, chunks/ and analysis/ (default: ./editor-review)'
    ex = sub.add_parser('extract', help='tracked changes -> units.json, ops.json, global.json')
    ex.add_argument('edited', help='the .docx the editor returned')
    ex.add_argument('--original', help='the .docx before editing; the reject-all text must equal it')
    ex.add_argument('--work', default='editor-review', help=work_help)
    ex.add_argument('--churn-font', help="font name to collapse font-switch churn into one count, or 'none' "
                                         '(default: the font most runs were switched to)')
    ex.add_argument('--churn-min', type=int, default=10,
                    help='fewest runs switched to one font before it counts as churn (default 10)')
    ex.add_argument('--strict', action='store_true', help='exit 1 when the baseline check finds differences')
    ex.set_defaults(func=cmd_extract)
    ch = sub.add_parser('chunk', help='split ops into balanced text chunks, a layout chunk and auto-classified marks')
    ch.add_argument('--work', default='editor-review', help=work_help)
    ch.add_argument('--target-ops', type=int, default=DEFAULT_TARGET, help='ops per text chunk (default 110)')
    ch.set_defaults(func=cmd_chunk)
    co = sub.add_parser('coverage', help='every op id classified exactly once; exit 1 otherwise')
    co.add_argument('--work', default='editor-review', help=work_help)
    co.add_argument('--json', action='store_true', help='print the result as JSON')
    co.set_defaults(func=cmd_coverage)
    mg = sub.add_parser('merge', help='rules + skeptic verdicts (+ author decisions) -> verified-catalogue')
    mg.add_argument('--work', default='editor-review', help=work_help)
    mg.add_argument('--decisions', help="JSON object {rule id: {...}} with the author's decisions")
    mg.add_argument('--strict', action='store_true', help='exit 1 on any rule without a usable verdict')
    mg.set_defaults(func=cmd_merge)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
