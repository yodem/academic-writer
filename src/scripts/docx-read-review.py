#!/usr/bin/env python3
"""Extract Word comments and tracked revisions from a DOCX.

Reads the body, the footnotes and the endnotes. Every item keeps the original shape
``{id, kind, anchorText, text, author, date}`` that ``aw revise classify`` consumes, and adds:

* ``part`` (body, footnote or endnote), ``location`` (for example ``body:12`` or ``footnote:3``),
  ``paragraphIndex`` and ``section`` (the nearest heading above);
* ``paragraphBefore`` and ``paragraphAfter``: the whole paragraph with every revision rejected and
  accepted, so a replacement is never read without its sentence;
* for a note, ``citedIn``: the body paragraph that cites it.

Kinds: ``comment``, ``insert``, ``delete``, ``replace``, ``move`` and, new, ``format`` (a run's
bold, italic, size or font changed), ``paragraph-format`` (alignment, spacing, indentation) and
``paragraph-mark`` (a paragraph was split or two were merged). Pure font-switch churn and blank
paragraph marks are counted in ``summary`` instead of listed.
"""
import argparse
import collections
import json
import os
import sys
import zipfile
from xml.etree import ElementTree as ET

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lib'))
import docx_revisions as dr  # noqa: E402

W = dr.W
HEADING_LIMIT = 120
MAPPING = {'ins': 'insert', 'del': 'delete', 'moveFrom': 'move', 'moveTo': 'move'}


def _comments(doc):
    comments = {}
    try:
        root = ET.fromstring(doc.read('word/comments.xml'))
    except KeyError:
        return comments
    for c in root.findall(W + 'comment'):
        comments[c.get(W + 'id', '')] = {
            'text': ''.join((e.text or '') for e in c.iter() if e.tag in dr.TEXT_TAGS),
            'author': c.get(W + 'author', ''), 'date': c.get(W + 'date', '')}
    return comments


class Reader:
    def __init__(self, doc):
        self.roots = dr.load_roots(doc)
        self.comments = _comments(doc)
        self.items = []
        self.seen_comments = set()
        self.counts = collections.Counter()
        self.churn_counter = collections.Counter()
        self.cited_in = {}
        self.sections = {}
        paragraphs = []
        for kind, root in self.roots.items():
            if kind == 'body':
                paragraphs += dr.body_paragraphs(root)
            else:
                for _, el in dr.notes(root, kind):
                    paragraphs += list(el.iter(W + 'p'))
        self.churn = dr.detect_churn_font(paragraphs)

    def paragraph(self, part, key, index, p, section):
        """Turn one paragraph into items. ``key`` is body:N, footnote:ID or endnote:ID."""
        before, after, refs = dr.paragraph_views(p)
        if part == 'body':
            for ref in refs:
                self.cited_in.setdefault(ref, index)
        context = {'part': part, 'location': key if part != 'body' else 'body:' + str(index),
                   'paragraphIndex': index, 'section': section,
                   'paragraphBefore': before, 'paragraphAfter': after}
        if part != 'body' and key in self.cited_in:
            context['citedIn'] = 'body:' + str(self.cited_in[key])
        plain_before = dr.MARK_RE.sub('', dr.strip_markup(before)).strip()
        plain_after = dr.MARK_RE.sub('', dr.strip_markup(after)).strip()
        # body ids stay as they always were; notes are prefixed because w:id repeats across parts
        prefix = '' if part == 'body' else key.replace(':', '-') + '-'
        tail = str(index)

        def add(item_id, kind, anchor, text, author, date):
            item = {'id': item_id, 'kind': kind, 'anchorText': anchor, 'text': text,
                    'author': author, 'date': date}
            item.update(context)
            self.items.append(item)
            return item

        # one pass over the paragraph in document order: comment ranges and revisions
        open_at, text_in, revs = [], {}, []
        for tok, val in dr.tokens(p):
            if tok == 'cstart':
                open_at.append(val)
                text_in.setdefault(val, '')
            elif tok == 'cend':
                if val in open_at:
                    open_at.remove(val)
            elif tok == 'cref':
                text_in.setdefault(val, '')
            elif tok == 'text':
                for cid in open_at:
                    text_in[cid] += val
                if val.strip():
                    revs.append(('text', None))
            elif tok == 'rev':
                body = dr.revision_text(val)
                if body.strip():
                    revs.append((dr.local(val), val))
                    for cid in open_at:
                        text_in[cid] += body

        # comments: reported once, where the range opens; the anchor is the whole paragraph
        for cid, ranged in text_in.items():
            if cid in self.seen_comments or cid not in self.comments:
                continue
            self.seen_comments.add(cid)
            c = self.comments[cid]
            item = add(prefix + 'comment-' + str(cid), 'comment', plain_after, c['text'],
                       c['author'], c['date'])
            item['commentedText'] = ranged.strip()

        # insertions, deletions, moves; a deletion directly followed by an insertion is a replace
        pos = 0
        while pos < len(revs):
            local, el = revs[pos]
            if el is None:
                pos += 1
                continue
            val = dr.revision_text(el).strip()
            cid = el.get(W + 'id', '')
            author, date = el.get(W + 'author', ''), el.get(W + 'date', '')
            nxt = revs[pos + 1] if pos + 1 < len(revs) else (None, None)
            if local == 'moveFrom' and nxt[0] == 'moveTo' and nxt[1].get(W + 'id', '') == cid:
                nel = nxt[1]
                add(prefix + 'revision-' + cid, 'move', val, dr.revision_text(nel).strip(),
                    author or nel.get(W + 'author', ''), date or nel.get(W + 'date', ''))
                pos += 2
                continue
            if local == 'del' and nxt[0] == 'ins':
                nel = nxt[1]
                add(prefix + 'revision-' + cid, 'replace', val, dr.revision_text(nel).strip(),
                    author or nel.get(W + 'author', ''), date or nel.get(W + 'date', ''))
                pos += 2
                continue
            add(prefix + 'revision-' + cid + '-' + str(pos), MAPPING[local], val, val, author, date)
            pos += 1

        # formatting revisions, split and merge
        for n, op in enumerate(dr.run_format_ops(p, self.churn_counter, self.churn)):
            add('{}format-{}-{}'.format(prefix, tail, n), 'format', op['text'].strip(), op['delta'],
                op['author'], op['date'])
        pf = dr.para_format_op(p)
        if pf:
            add('{}paragraph-format-{}'.format(prefix, tail), 'paragraph-format', plain_after[:200],
                pf['delta'], pf['author'], pf['date'])
        mark = dr.para_mark(p)
        if mark:
            if plain_after or plain_before:
                author, date = dr.para_mark_meta(p)
                add('{}paragraph-mark-{}'.format(prefix, tail), 'paragraph-mark', plain_after[:200],
                    'split' if 'inserted' in mark else 'merge', author, date)
            else:
                self.counts['blankParagraphMarks'] += 1

    def run(self):
        body = self.roots.get('body')
        if body is not None:
            section = ''
            for index, p in enumerate(dr.body_paragraphs(body)):
                if dr.is_heading_style(dr.paragraph_style(p)):
                    heading = dr.strip_markup(dr.paragraph_views(p, markup=False)[1]).strip()
                    section = heading[:HEADING_LIMIT] or section
                self.sections[index] = section
                self.paragraph('body', 'body:' + str(index), index, p, section)
        for kind in ('footnote', 'endnote'):
            root = self.roots.get(kind)
            if root is None:
                continue
            for nid, el in dr.notes(root, kind):
                key = '{}:{}'.format(kind, nid)
                anchor = self.cited_in.get(key)
                section = self.sections.get(anchor, '')
                for index, p in enumerate(el.iter(W + 'p')):
                    self.paragraph(kind, key, index, p, section)
        summary = {'fontChurn': dict(self.churn_counter)}
        summary.update(self.counts)
        summary['byKind'] = dict(collections.Counter(i['kind'] for i in self.items))
        return {'items': self.items, 'summary': summary}


def read(path):
    with zipfile.ZipFile(path) as doc:
        return Reader(doc).run()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('file')
    parser.add_argument('--json', action='store_true', help='compact one-line JSON')
    args = parser.parse_args()
    result = read(args.file)
    print(json.dumps(result, ensure_ascii=False) if args.json else json.dumps(result, ensure_ascii=False, indent=2))
