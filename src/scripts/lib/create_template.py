"""
Create a Word template with footnotes infrastructure.
Run this ONCE to create the template that you'll use for document generation.

Usage:
    python create_template.py [output_path]

Example:
    python create_template.py footnote_template.docx
"""

from docx import Document
from lxml import etree
import zipfile
import os
import shutil
import sys


def create_template_with_footnotes(template_path="footnote_template.docx"):
    """Create a template document with footnotes infrastructure."""

    # First create a basic document
    doc = Document()
    doc.add_paragraph("Template paragraph")

    # Save it temporarily
    temp_path = template_path + ".temp"
    doc.save(temp_path)

    # Extract the docx
    extract_dir = temp_path + "_extracted"
    with zipfile.ZipFile(temp_path, 'r') as zip_ref:
        zip_ref.extractall(extract_dir)

    word_dir = os.path.join(extract_dir, "word")
    w_ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

    # Create footnotes.xml - CRITICAL: declare all namespaces referenced in mc:Ignorable
    footnotes_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:footnotes xmlns:wpc="http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas"
             xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"
             xmlns:o="urn:schemas-microsoft-com:office:office"
             xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
             xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"
             xmlns:v="urn:schemas-microsoft-com:vml"
             xmlns:wp14="http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing"
             xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
             xmlns:w10="urn:schemas-microsoft-com:office:word"
             xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
             xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml"
             xmlns:wne="http://schemas.microsoft.com/office/word/2006/wordml"
             mc:Ignorable="w14 wp14">
    <w:footnote w:type="separator" w:id="-1">
        <w:p><w:pPr><w:spacing w:after="0" w:line="240" w:lineRule="auto"/></w:pPr>
            <w:r><w:separator/></w:r></w:p>
    </w:footnote>
    <w:footnote w:type="continuationSeparator" w:id="0">
        <w:p><w:pPr><w:spacing w:after="0" w:line="240" w:lineRule="auto"/></w:pPr>
            <w:r><w:continuationSeparator/></w:r></w:p>
    </w:footnote>
</w:footnotes>'''
    with open(os.path.join(word_dir, "footnotes.xml"), "w", encoding="utf-8") as f:
        f.write(footnotes_xml)

    # Create endnotes.xml (Word expects this when footnotes exist)
    endnotes_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:endnotes xmlns:wpc="http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas"
            xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"
            xmlns:o="urn:schemas-microsoft-com:office:office"
            xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
            xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"
            xmlns:v="urn:schemas-microsoft-com:vml"
            xmlns:wp14="http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing"
            xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
            xmlns:w10="urn:schemas-microsoft-com:office:word"
            xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
            xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml"
            xmlns:wne="http://schemas.microsoft.com/office/word/2006/wordml"
            mc:Ignorable="w14 wp14">
    <w:endnote w:type="separator" w:id="-1">
        <w:p><w:pPr><w:spacing w:after="0" w:line="240" w:lineRule="auto"/></w:pPr>
            <w:r><w:separator/></w:r></w:p>
    </w:endnote>
    <w:endnote w:type="continuationSeparator" w:id="0">
        <w:p><w:pPr><w:spacing w:after="0" w:line="240" w:lineRule="auto"/></w:pPr>
            <w:r><w:continuationSeparator/></w:r></w:p>
    </w:endnote>
</w:endnotes>'''
    with open(os.path.join(word_dir, "endnotes.xml"), "w", encoding="utf-8") as f:
        f.write(endnotes_xml)

    # Update [Content_Types].xml
    content_types_path = os.path.join(extract_dir, "[Content_Types].xml")
    tree = etree.parse(content_types_path)
    root = tree.getroot()
    ct_ns = "http://schemas.openxmlformats.org/package/2006/content-types"

    # Add footnotes and endnotes overrides
    for part, content_type in [
        ("/word/footnotes.xml", "application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml"),
        ("/word/endnotes.xml", "application/vnd.openxmlformats-officedocument.wordprocessingml.endnotes+xml")
    ]:
        override = etree.SubElement(root, "{%s}Override" % ct_ns)
        override.set("PartName", part)
        override.set("ContentType", content_type)
    tree.write(content_types_path, xml_declaration=True, encoding="UTF-8", standalone="yes")

    # Update styles.xml - add FootnoteReference and FootnoteText styles
    styles_path = os.path.join(word_dir, "styles.xml")
    styles_tree = etree.parse(styles_path)
    styles_root = styles_tree.getroot()

    # Add FootnoteReference style
    fn_ref_style = etree.SubElement(styles_root, "{%s}style" % w_ns)
    fn_ref_style.set("{%s}type" % w_ns, "character")
    fn_ref_style.set("{%s}styleId" % w_ns, "FootnoteReference")
    etree.SubElement(fn_ref_style, "{%s}name" % w_ns).set("{%s}val" % w_ns, "footnote reference")
    etree.SubElement(fn_ref_style, "{%s}basedOn" % w_ns).set("{%s}val" % w_ns, "DefaultParagraphFont")
    fn_ref_rPr = etree.SubElement(fn_ref_style, "{%s}rPr" % w_ns)
    etree.SubElement(fn_ref_rPr, "{%s}vertAlign" % w_ns).set("{%s}val" % w_ns, "superscript")

    # Add FootnoteText style
    fn_text_style = etree.SubElement(styles_root, "{%s}style" % w_ns)
    fn_text_style.set("{%s}type" % w_ns, "paragraph")
    fn_text_style.set("{%s}styleId" % w_ns, "FootnoteText")
    etree.SubElement(fn_text_style, "{%s}name" % w_ns).set("{%s}val" % w_ns, "footnote text")
    etree.SubElement(fn_text_style, "{%s}basedOn" % w_ns).set("{%s}val" % w_ns, "Normal")
    fn_text_pPr = etree.SubElement(fn_text_style, "{%s}pPr" % w_ns)
    spacing = etree.SubElement(fn_text_pPr, "{%s}spacing" % w_ns)
    spacing.set("{%s}after" % w_ns, "0")
    spacing.set("{%s}line" % w_ns, "240")
    spacing.set("{%s}lineRule" % w_ns, "auto")
    fn_text_rPr = etree.SubElement(fn_text_style, "{%s}rPr" % w_ns)
    etree.SubElement(fn_text_rPr, "{%s}sz" % w_ns).set("{%s}val" % w_ns, "20")
    etree.SubElement(fn_text_rPr, "{%s}szCs" % w_ns).set("{%s}val" % w_ns, "20")

    styles_tree.write(styles_path, xml_declaration=True, encoding="UTF-8", standalone="yes")

    # Update document.xml.rels - add footnotes and endnotes relationships
    rels_path = os.path.join(word_dir, "_rels", "document.xml.rels")
    rels_tree = etree.parse(rels_path)
    rels_root = rels_tree.getroot()
    rel_ns = "http://schemas.openxmlformats.org/package/2006/relationships"

    existing_ids = [int(el.get("Id")[3:]) for el in rels_root if el.get("Id", "").startswith("rId")]
    next_id = max(existing_ids) + 1 if existing_ids else 1

    for target, rel_type in [
        ("footnotes.xml", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/footnotes"),
        ("endnotes.xml", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/endnotes")
    ]:
        rel = etree.SubElement(rels_root, "{%s}Relationship" % rel_ns)
        rel.set("Id", f"rId{next_id}")
        rel.set("Type", rel_type)
        rel.set("Target", target)
        next_id += 1

    rels_tree.write(rels_path, xml_declaration=True, encoding="UTF-8", standalone="yes")

    # Update settings.xml - add footnotePr and endnotePr
    settings_path = os.path.join(word_dir, "settings.xml")
    settings_tree = etree.parse(settings_path)
    settings_root = settings_tree.getroot()

    footnotePr = etree.Element("{%s}footnotePr" % w_ns)
    etree.SubElement(footnotePr, "{%s}footnote" % w_ns).set("{%s}id" % w_ns, "-1")
    etree.SubElement(footnotePr, "{%s}footnote" % w_ns).set("{%s}id" % w_ns, "0")

    endnotePr = etree.Element("{%s}endnotePr" % w_ns)
    etree.SubElement(endnotePr, "{%s}endnote" % w_ns).set("{%s}id" % w_ns, "-1")
    etree.SubElement(endnotePr, "{%s}endnote" % w_ns).set("{%s}id" % w_ns, "0")

    # Insert after characterSpacingControl or at beginning
    insert_idx = 0
    for i, elem in enumerate(settings_root):
        if 'characterSpacingControl' in elem.tag:
            insert_idx = i + 1
            break
    settings_root.insert(insert_idx, footnotePr)
    settings_root.insert(insert_idx + 1, endnotePr)

    settings_tree.write(settings_path, xml_declaration=True, encoding="UTF-8", standalone="yes")

    # Repack the docx
    with zipfile.ZipFile(template_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root_dir, dirs, files in os.walk(extract_dir):
            for file in files:
                file_path = os.path.join(root_dir, file)
                arcname = os.path.relpath(file_path, extract_dir)
                zipf.write(file_path, arcname)

    # Clean up
    os.remove(temp_path)
    shutil.rmtree(extract_dir)

    print(f"Template created: {template_path}")
    return template_path


if __name__ == "__main__":
    output_path = sys.argv[1] if len(sys.argv) > 1 else "footnote_template.docx"
    create_template_with_footnotes(output_path)
