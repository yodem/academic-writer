"""Shared reading of Word tracked changes (stdlib only, Python 3.9).

Used by ``docx-read-review.py`` (the reviewer's comments and revisions) and by
``docx-editor-diff.py`` (a whole edited paper compared with its original). It knows how to:

* open the three story parts that can carry revisions: the body, the footnotes and the endnotes;
* render a paragraph as it was before the revisions (reject all) and after them (accept all),
  with <i>, <b> and <sup> markup;
* describe formatting revisions (``w:rPrChange`` on a run, ``w:pPrChange`` on a paragraph) as a
  short old-to-new delta, and recognise paragraph-mark insertions and deletions (splits and merges);
* collapse "font switch" churn (thousands of runs whose only change is one font) into a count.
"""
from __future__ import annotations

import collections
import re
import zipfile
from typing import Dict, Iterator, List, Optional, Tuple
from xml.etree import ElementTree as ET

W_NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
W = '{' + W_NS + '}'

# kind -> part file inside the zip
PART_FILES = (('body', 'word/document.xml'),
              ('footnote', 'word/footnotes.xml'),
              ('endnote', 'word/endnotes.xml'))
NOTE_TAG = {'footnote': 'footnote', 'endnote': 'endnote'}
NOTE_REF_TAG = {'footnoteReference': 'footnote', 'endnoteReference': 'endnote'}
NOTE_MARK = {'footnote': '[^{}]', 'endnote': '[^e{}]'}
MARK_RE = re.compile(r'\[\^e?\d+\]')

MARKUP = {'i': ('<i>', '</i>'), 'b': ('<b>', '</b>'), 's': ('<sup>', '</sup>')}
MARKUP_RE = re.compile(r'</?(i|b|sup)>')

REV_TAGS = ('ins', 'del', 'moveFrom', 'moveTo')
TEXT_TAGS = (W + 't', W + 'delText')
# runs whose only change is one of these are layout bookkeeping, never a convention
NOISE = {'+rtl', '-rtl', '+bCs', '-bCs', '+iCs', '-iCs', '+szCs', '-szCs'}


def tag(el) -> str:
    return el.tag.replace(W, 'w:')


def local(el) -> str:
    return el.tag.rsplit('}', 1)[-1]


def load_roots(zf: zipfile.ZipFile) -> Dict[str, ET.Element]:
    """Parsed XML root of each existing story part, keyed 'body' / 'footnote' / 'endnote'."""
    names = set(zf.namelist())
    roots = {}
    for kind, name in PART_FILES:
        if name in names:
            roots[kind] = ET.fromstring(zf.read(name))
    return roots


def body_paragraphs(root) -> List[ET.Element]:
    body = root.find(W + 'body')
    return list(body.iter(W + 'p')) if body is not None else []


def notes(root, kind: str) -> List[Tuple[str, ET.Element]]:
    """(id, element) of each real footnote or endnote, separators skipped, in file order."""
    out = []
    for el in root.findall(W + NOTE_TAG[kind]):
        if el.get(W + 'type') in ('separator', 'continuationSeparator', 'continuationNotice'):
            continue
        out.append((el.get(W + 'id'), el))
    return out


# ---------------------------------------------------------------- paragraph text

def run_flags(r, mode: str) -> str:
    """Italic/bold/superscript of a run as 'i', 'b', 's' letters; 'before' reads the pre-revision rPr."""
    rpr = r.find(W + 'rPr')
    if rpr is None:
        return ''
    src = rpr
    ch = rpr.find(W + 'rPrChange')
    if mode == 'before' and ch is not None:
        src = ch.find(W + 'rPr')
        if src is None:
            return ''
    flags = ''

    def on(name):
        el = src.find(W + name)
        return el is not None and el.get(W + 'val') not in ('0', 'false')

    if on('i'):
        flags += 'i'
    if on('b'):
        flags += 'b'
    va = src.find(W + 'vertAlign')
    if va is not None and va.get(W + 'val') == 'superscript':
        flags += 's'
    return flags


def walk(el, mode: str, out: list, refs: list, state: Optional[dict] = None, flags: str = '') -> None:
    """Append (text, flags) pieces of ``el`` as seen in 'before' (reject all) or 'after' (accept all).

    ``refs`` collects the footnote/endnote references met, as 'footnote:ID' / 'endnote:ID'.
    ``state['page']`` is bumped at every rendered page break so callers can estimate a page.
    """
    t = tag(el)
    if t == 'w:r':
        flags = run_flags(el, mode)
    if t in ('w:ins', 'w:moveTo') and mode == 'before':
        return
    if t in ('w:del', 'w:moveFrom') and mode == 'after':
        return
    if t in ('w:pPr', 'w:rPr', 'w:sectPr', 'w:instrText', 'w:delInstrText'):
        return
    if state is not None and t == 'w:lastRenderedPageBreak':
        state['page'] += 1
    if t in ('w:t', 'w:delText'):
        out.append((el.text or '', flags))
    elif t == 'w:tab':
        out.append('\t')
    elif t == 'w:noBreakHyphen':
        out.append('‑')
    elif t == 'w:softHyphen':
        out.append('­')
    elif t == 'w:sym':
        try:
            out.append(chr(int(el.get(W + 'char', '0020'), 16)))
        except ValueError:
            pass
    elif t == 'w:br' and el.get(W + 'type') != 'page':
        out.append('\n')
    elif local(el) in NOTE_REF_TAG:
        kind = NOTE_REF_TAG[local(el)]
        nid = el.get(W + 'id')
        out.append(NOTE_MARK[kind].format(nid))
        refs.append(kind + ':' + str(nid))
    for child in el:
        walk(child, mode, out, refs, state, flags)


def render(parts: list, markup: bool = True) -> str:
    """Join walk() pieces; merge same-flag neighbours and wrap them in <i>/<b>/<sup> when ``markup``."""
    segs: List[list] = []
    for piece in parts:
        txt, fl = (piece, '') if isinstance(piece, str) else piece
        if segs and segs[-1][1] == fl:
            segs[-1][0] += txt
        else:
            segs.append([txt, fl])
    out = ''
    for txt, fl in segs:
        if not txt:
            continue
        if not markup or not fl or not txt.strip():
            out += txt
            continue
        opener = closer = ''
        for k in fl:
            opener += MARKUP[k][0]
            closer = MARKUP[k][1] + closer
        lead = txt[:len(txt) - len(txt.lstrip())]
        trail = txt[len(txt.rstrip()):]
        out += lead + opener + txt.strip() + closer + trail
    return out


def paragraph_views(p, state: Optional[dict] = None, markup: bool = True) -> Tuple[str, str, List[str]]:
    """(before, after, note references) of a paragraph. State, if given, tracks page breaks (after pass)."""
    after: list = []
    before: list = []
    refs: List[str] = []
    walk(p, 'after', after, refs, state)
    walk(p, 'before', before, [])
    return render(before, markup), render(after, markup), refs


def strip_markup(text: str) -> str:
    return MARKUP_RE.sub('', text)


def has_text_change(p) -> bool:
    """True when the paragraph holds an insertion/deletion/move that touches text, a tab or a note reference."""
    for el in p.iter():
        if local(el) in REV_TAGS:
            for x in el.iter():
                if tag(x) in ('w:t', 'w:delText', 'w:tab') or local(x) in NOTE_REF_TAG:
                    return True
    return False


def paragraph_style(p) -> str:
    ps = p.find(W + 'pPr/' + W + 'pStyle')
    return ps.get(W + 'val') if ps is not None else ''


def is_heading_style(style: str) -> bool:
    return bool(re.match(r'(?i)^(heading\s*\d|title$|כותרת)', style or ''))


# ---------------------------------------------------------------- paragraph marks

def para_mark(p) -> str:
    """'paragraph-mark-inserted (split)', 'paragraph-mark-deleted (merged with next)' or ''."""
    rpr = p.find(W + 'pPr/' + W + 'rPr')
    if rpr is None:
        return ''
    if rpr.find(W + 'ins') is not None:
        return 'paragraph-mark-inserted (split)'
    if rpr.find(W + 'del') is not None:
        return 'paragraph-mark-deleted (merged with next)'
    return ''


def para_mark_meta(p) -> Tuple[str, str]:
    """(author, date) of the paragraph-mark revision, empty when there is none."""
    rpr = p.find(W + 'pPr/' + W + 'rPr')
    if rpr is None:
        return '', ''
    for name in ('ins', 'del'):
        el = rpr.find(W + name)
        if el is not None:
            return el.get(W + 'author', ''), el.get(W + 'date', '')
    return '', ''


# ---------------------------------------------------------------- formatting revisions

def props(rpr, skip=('w:rPrChange', 'w:pPrChange', 'w:ins', 'w:del')) -> Dict[str, dict]:
    """Property name -> attributes of an rPr/pPr element, rsid noise dropped."""
    res: Dict[str, dict] = {}
    if rpr is None:
        return res
    for child in rpr:
        name = tag(child)
        if name in skip:
            continue
        res[name] = {k.replace(W, ''): v for k, v in child.attrib.items() if 'rsid' not in k}
    return res


def fmt(attrs) -> str:
    return '' if not attrs else '(' + ','.join('{}={}'.format(k, v) for k, v in attrs.items()) + ')'


def delta(old: dict, new: dict) -> List[str]:
    """Old-to-new property delta: '+x' added, '-x' removed, '~x(a)->(b)' changed."""
    out = []
    for k in sorted(set(old) | set(new)):
        if k not in old:
            out.append('+{}{}'.format(k[2:], fmt(new[k])))
        elif k not in new:
            out.append('-{}{}'.format(k[2:], fmt(old[k])))
        elif old[k] != new[k]:
            out.append('~{}{}->{}'.format(k[2:], fmt(old[k]), fmt(new[k])))
    return out


def _font_name(attrs: dict) -> str:
    for key in ('ascii', 'hAnsi', 'cs', 'eastAsia', 'asciiTheme', 'hAnsiTheme'):
        if attrs.get(key):
            return attrs[key]
    return ''


def detect_churn_font(paragraphs, minimum: int = 10) -> Optional[str]:
    """The font most runs were switched to, when at least ``minimum`` runs were; else None.

    A document run through a "set everything to font X" pass carries one rPrChange per run. Those
    are not editing decisions, so callers count them once instead of listing each.
    """
    seen: collections.Counter = collections.Counter()
    for p in paragraphs:
        for r in p.iter(W + 'r'):
            rpr = r.find(W + 'rPr')
            ch = rpr.find(W + 'rPrChange') if rpr is not None else None
            if ch is None:
                continue
            old, new = props(ch.find(W + 'rPr')), props(rpr)
            if 'w:rFonts' in new and old.get('w:rFonts') != new['w:rFonts']:
                name = _font_name(new['w:rFonts'])
                if name:
                    seen[name] += 1
    if not seen:
        return None
    name, count = seen.most_common(1)[0]
    return name if count >= minimum else None


def run_format_ops(p, counter: collections.Counter, churn: Optional[str]) -> List[dict]:
    """Per-run formatting revisions of a paragraph, adjacent runs with the same delta merged.

    Each op: {'delta', 'text', 'author', 'date'}. Switches to the churn font and bidi bookkeeping
    (rtl, complex-script size/bold/italic) are dropped; the churn is added to ``counter``.
    """
    ops: List[dict] = []
    for r in p.iter(W + 'r'):
        rpr = r.find(W + 'rPr')
        if rpr is None:
            continue
        ch = rpr.find(W + 'rPrChange')
        if ch is None:
            continue
        dl = delta(props(ch.find(W + 'rPr')), props(rpr))
        sig = []
        for x in dl:
            if churn and x.startswith('+rFonts') and churn in x:
                counter['font set to ' + churn] += 1
                continue
            if churn and x.startswith('~rFonts') and churn in x.split('->')[-1]:
                counter['font changed to ' + churn] += 1
                continue
            if x in NOISE or (x.startswith('~rFonts(') and 'hint' in x):
                continue
            sig.append(x)
        if not sig:
            continue
        txt = ''.join(t.text or '' for t in r.iter() if tag(t) in ('w:t', 'w:delText'))
        key = ' '.join(sig)
        if ops and ops[-1]['delta'] == key:
            ops[-1]['text'] += txt
        else:
            ops.append({'delta': key, 'text': txt, 'author': ch.get(W + 'author', ''),
                        'date': ch.get(W + 'date', '')})
    return [o for o in ops if o['text'].strip()]


def para_format_op(p) -> Optional[dict]:
    """The paragraph-property revision of ``p`` as {'delta', 'author', 'date'}, or None."""
    ppr = p.find(W + 'pPr')
    if ppr is None:
        return None
    ch = ppr.find(W + 'pPrChange')
    if ch is None:
        return None
    skip = ('w:rPr', 'w:pPrChange', 'w:sectPr')
    dl = delta(props(ch.find(W + 'pPr'), skip=skip), props(ppr, skip=skip))
    if not dl:
        return None
    return {'delta': ' '.join(dl), 'author': ch.get(W + 'author', ''), 'date': ch.get(W + 'date', '')}


# ---------------------------------------------------------------- token stream (reader)

def tokens(p) -> Iterator[Tuple[str, object]]:
    """Walk a paragraph in document order, yielding ('rev', element), ('text', str) and
    ('cstart'|'cend', comment id). Revisions are not entered, so text inside them is not 'text'."""
    def rec(el):
        for child in el:
            name = local(child)
            if name in REV_TAGS:
                yield ('rev', child)
            elif name == 'commentRangeStart':
                yield ('cstart', child.get(W + 'id'))
            elif name == 'commentRangeEnd':
                yield ('cend', child.get(W + 'id'))
            elif name == 'commentReference':
                yield ('cref', child.get(W + 'id'))
            elif name == 't':
                yield ('text', child.text or '')
            elif name in ('pPr', 'rPr'):
                continue
            else:
                for x in rec(child):
                    yield x
    return rec(p)


def revision_text(el) -> str:
    return ''.join((x.text or '') for x in el.iter() if x.tag in TEXT_TAGS)
