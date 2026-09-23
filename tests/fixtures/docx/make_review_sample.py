"""Build a tiny DOCX review fixture from raw OOXML."""
from zipfile import ZipFile, ZIP_DEFLATED
from pathlib import Path

ROOT = Path(__file__).parent
W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
XML = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="{W}" xmlns:r="{R}"><w:body>
<w:p><w:r><w:t>A </w:t></w:r><w:commentRangeStart w:id="0"/><w:r><w:t>commented</w:t></w:r><w:commentRangeEnd w:id="0"/><w:r><w:commentReference w:id="0"/></w:r></w:p>
<w:p><w:commentRangeStart w:id="1"/><w:r><w:t>second note</w:t></w:r><w:commentRangeEnd w:id="1"/><w:r><w:commentReference w:id="1"/></w:r></w:p>
<w:p><w:del w:id="10" w:author="academic-writer"><w:r><w:delText>old</w:delText></w:r></w:del><w:ins w:id="11" w:author="academic-writer"><w:r><w:t>new</w:t></w:r></w:ins></w:p>
<w:p><w:del w:id="12" w:author="academic-writer"><w:r><w:delText>removed paragraph</w:delText></w:r></w:del></w:p>
<w:p><w:moveFrom w:id="13" w:author="academic-writer"><w:r><w:delText>moved words</w:delText></w:r></w:moveFrom><w:moveTo w:id="13" w:author="academic-writer"><w:r><w:t>moved words</w:t></w:r></w:moveTo></w:p>
<w:sectPr/></w:body></w:document>'''
COMMENTS = f'''<?xml version="1.0"?><w:comments xmlns:w="{W}"><w:comment w:id="0" w:author="Researcher" w:date="2026-09-23T00:00:00Z"><w:p><w:r><w:t>Clarify this</w:t></w:r></w:p></w:comment><w:comment w:id="1" w:author="Researcher"><w:p><w:r><w:t>Check wording</w:t></w:r></w:p></w:comment></w:comments>'''
RELS = f'''<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments" Target="comments.xml"/></Relationships>'''
if __name__ == '__main__':
    with ZipFile(ROOT / 'review-sample.docx', 'w', ZIP_DEFLATED) as z:
        z.writestr('word/document.xml', XML)
        z.writestr('word/comments.xml', COMMENTS)
        z.writestr('word/_rels/document.xml.rels', RELS)
        z.writestr('[Content_Types].xml', '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/comments.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"/></Types>')
