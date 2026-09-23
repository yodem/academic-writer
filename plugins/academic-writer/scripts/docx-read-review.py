#!/usr/bin/env python3
"""Extract Word comments and tracked revisions from a DOCX."""
import argparse
import json
import re
import zipfile
from xml.etree import ElementTree as ET

NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
Q = '{' + NS['w'] + '}'

def text(node, deleted=False):
    tags = ('delText', 't') if deleted else ('t', 'delText')
    return ''.join((e.text or '') for tag in tags for e in node.iter(Q + tag))

def read(path):
    with zipfile.ZipFile(path) as doc:
        root = ET.fromstring(doc.read('word/document.xml'))
        comments = {}
        try:
            cr = ET.fromstring(doc.read('word/comments.xml'))
            for c in cr.findall('w:comment', NS):
                comments[c.get(Q+'id', '')] = {'text': text(c), 'author': c.get(Q+'author', ''), 'date': c.get(Q+'date', '')}
        except KeyError:
            pass
        items = []
        body = root.find('w:body', NS)
        paragraphs = [e for e in body.iter() if e.tag == Q + 'p'] if body is not None else []
        for paragraph in paragraphs:
            full = text(paragraph).strip()
            starts = {e.get(Q+'id') for e in paragraph.iter(Q+'commentRangeStart')}
            for cid in starts:
                c = comments.get(cid, {})
                items.append({'id': 'comment-' + str(cid), 'kind': 'comment', 'anchorText': full, 'text': c.get('text', ''), 'author': c.get('author', ''), 'date': c.get('date', '')})
            revs = []
            for el in paragraph.iter():
                local = el.tag.rsplit('}', 1)[-1]
                if local in ('ins', 'del', 'moveFrom', 'moveTo'):
                    val = text(el, local in ('del', 'moveFrom')).strip()
                    if val:
                        revs.append((local, val, el.get(Q+'id', ''), el.get(Q+'author', ''), el.get(Q+'date', '')))
            index = 0
            while index < len(revs):
                kind, val, cid, author, date = revs[index]
                if kind == 'moveFrom' and index + 1 < len(revs) and revs[index+1][0] == 'moveTo' and revs[index+1][2] == cid:
                    nxt = revs[index+1]
                    items.append({'id': 'revision-' + cid, 'kind': 'move', 'anchorText': val, 'text': nxt[1], 'author': author or nxt[3], 'date': date or nxt[4]})
                    index += 2
                    continue
                if kind == 'del' and index + 1 < len(revs) and revs[index+1][0] == 'ins':
                    nxt = revs[index+1]
                    items.append({'id': 'revision-' + cid, 'kind': 'replace', 'anchorText': val, 'text': nxt[1], 'author': author or nxt[3], 'date': date or nxt[4]})
                    index += 2
                    continue
                mapping = {'ins': 'insert', 'del': 'delete', 'moveFrom': 'move', 'moveTo': 'move'}
                items.append({'id': 'revision-' + cid + '-' + str(index), 'kind': mapping[kind], 'anchorText': val, 'text': val, 'author': author, 'date': date})
                index += 1
        return {'items': items}

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('file')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    result = read(args.file)
    print(json.dumps(result, ensure_ascii=False) if args.json else json.dumps(result, ensure_ascii=False, indent=2))
