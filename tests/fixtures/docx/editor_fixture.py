"""Build a small SYNTHETIC pair of Word files: an author's original and the copy an editor returned.

Nothing here comes from a real paper. The edited copy carries, in raw WordprocessingML:
a replaced word, a bold run added (w:rPrChange), a paragraph-format change (w:pPrChange), a
paragraph split (inserted paragraph mark), a blank paragraph added, a look-alike quote change,
twelve runs whose only change is a font switch (churn), and a footnote with an insertion, a
deletion and an italic formatting revision.
"""
import io
import zipfile

from docx import Document

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
A = 'w:author="Editor A" w:date="2026-10-01T10:00:00Z"'
NS = 'xmlns:w="{}"'.format(W)
CHURN_RUNS = 12


def _t(text):
    return '<w:t xml:space="preserve">{}</w:t>'.format(text)


def _run(text, rpr=''):
    return '<w:r>{}{}</w:r>'.format('<w:rPr>{}</w:rPr>'.format(rpr) if rpr else '', _t(text))


def _body(edited):
    ref = '<w:r><w:footnoteReference w:id="1"/></w:r>'
    p = []
    p.append('<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr>{}</w:p>'.format(_run('Introduction')))
    if edited:
        p.append('<w:p>{}<w:del w:id="1" {a}><w:r><w:delText>quick</w:delText></w:r></w:del>'
                 '<w:ins w:id="2" {a}>{}</w:ins>{}{}</w:p>'.format(
                     _run('The '), _run('swift'), _run(' fox jumps'), ref, a=A))
        p.append('<w:p>{}<w:r><w:rPr><w:b/><w:rPrChange w:id="3" {a}><w:rPr/></w:rPrChange></w:rPr>{}</w:r>{}</w:p>'.format(
            _run('This is '), _t('important'), _run(' text.'), a=A))
        p.append('<w:p><w:pPr><w:jc w:val="center"/><w:pPrChange w:id="4" {a}><w:pPr/></w:pPrChange></w:pPr>{}</w:p>'.format(
            _run('Centered line'), a=A))
        p.append('<w:p><w:pPr><w:rPr><w:ins w:id="5" {a}/></w:rPr></w:pPr>{}</w:p>'.format(_run('First half '), a=A))
        p.append('<w:p>{}</w:p>'.format(_run('second half.')))
        p.append('<w:p><w:pPr><w:rPr><w:ins w:id="6" {a}/></w:rPr></w:pPr></w:p>'.format(a=A))
        p.append('<w:p>{}<w:del w:id="7" {a}><w:r><w:delText>"</w:delText></w:r></w:del>'
                 '<w:ins w:id="8" {a}>{}</w:ins>{}</w:p>'.format(_run('ab'), _run('״'), _run('cd'), a=A))
        churn = ''.join(
            '<w:r><w:rPr><w:rFonts w:ascii="David" w:hAnsi="David"/><w:rPrChange w:id="{}" {}><w:rPr/></w:rPrChange></w:rPr>{}</w:r>'.format(
                20 + n, A, _t('w{} '.format(n))) for n in range(CHURN_RUNS))
        p.append('<w:p>{}</w:p>'.format(churn))
    else:
        p.append('<w:p>{}{}</w:p>'.format(_run('The quick fox jumps'), ref))
        p.append('<w:p>{}</w:p>'.format(_run('This is important text.')))
        p.append('<w:p>{}</w:p>'.format(_run('Centered line')))
        p.append('<w:p>{}</w:p>'.format(_run('First half second half.')))
        p.append('<w:p>{}</w:p>'.format(_run('ab"cd')))
        p.append('<w:p>{}</w:p>'.format(''.join(_run('w{} '.format(n)) for n in range(CHURN_RUNS))))
    return '<w:body>{}<w:sectPr/></w:body>'.format(''.join(p))


def _footnotes(edited):
    sep = ('<w:footnote w:type="separator" w:id="-1"><w:p><w:r><w:separator/></w:r></w:p></w:footnote>'
           '<w:footnote w:type="continuationSeparator" w:id="0"><w:p><w:r><w:continuationSeparator/></w:r></w:p></w:footnote>')
    mark = '<w:r><w:footnoteRef/></w:r>'
    if edited:
        text = ('{}<w:del w:id="30" {a}><w:r><w:delText>p. 4</w:delText></w:r></w:del>'
                '<w:ins w:id="31" {a}>{}</w:ins>'
                '<w:r><w:rPr><w:i/><w:rPrChange w:id="32" {a}><w:rPr/></w:rPrChange></w:rPr>{}</w:r>').format(
                    _run(' See Smith, '), _run('pp. 4-5'), _t(' Journal'), a=A)
    else:
        text = _run(' See Smith, p. 4') + _run(' Journal')
    note = '<w:footnote w:id="1"><w:p>{}{}</w:p></w:footnote>'.format(mark, text)
    return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:footnotes {}>{}{}</w:footnotes>'.format(NS, sep, note)


def build(path, edited):
    """Write the edited (True) or original (False) synthetic file to ``path``."""
    base = io.BytesIO()
    Document().save(base)
    zin = zipfile.ZipFile(io.BytesIO(base.getvalue()))
    document = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {}>{}</w:document>'.format(
        NS, _body(edited))
    with zipfile.ZipFile(str(path), 'w', zipfile.ZIP_DEFLATED) as out:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == 'word/document.xml':
                data = document.encode('utf-8')
            elif item.filename == '[Content_Types].xml':
                data = data.replace(b'</Types>', b'<Override PartName="/word/footnotes.xml" ContentType='
                                    b'"application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml"/></Types>')
            elif item.filename == 'word/_rels/document.xml.rels':
                data = data.replace(b'</Relationships>', b'<Relationship Id="rIdFn1" Type="http://schemas.openxmlformats.org/'
                                    b'officeDocument/2006/relationships/footnotes" Target="footnotes.xml"/></Relationships>')
            out.writestr(item, data)
        out.writestr('word/footnotes.xml', _footnotes(edited))
    return path
