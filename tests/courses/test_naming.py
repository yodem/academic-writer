import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "src/scripts/courses"))
import naming


ARTICLE = {"authors": ["Test, Alpha"], "year": "1990", "title": "History and Rhetoric in the Prophets",
           "journal": "Test Journal", "volume": "12", "issue": "3", "pages": "45–67"}
BOOK = {"authors": ["Smith, Anna"], "year": "2001", "title": "Yirmiyahu Studies",
        "place": "Jerusalem", "publisher": "Test Press"}


def test_article_bibliography_is_chicago_author_date():
    assert naming.chicago_bibliography(ARTICLE) == (
        'Test, Alpha. 1990. "History and Rhetoric in the Prophets." Test Journal 12 (3): 45–67.')


def test_book_bibliography_is_chicago_author_date():
    assert naming.chicago_bibliography(BOOK) == "Smith, Anna. 2001. Yirmiyahu Studies. Jerusalem: Test Press."


def test_display_name_drops_trailing_period():
    assert naming.display_name(BOOK) == "Smith, Anna. 2001. Yirmiyahu Studies. Jerusalem: Test Press"


def test_hebrew_metadata_stays_hebrew():
    meta = {"authors": ["כהן, דוד"], "year": "1999", "title": "ספר בדיקה", "place": "תל אביב", "publisher": "הוצאה"}
    assert naming.chicago_bibliography(meta) == "כהן, דוד. 1999. ספר בדיקה. תל אביב: הוצאה."


def test_stem_fallback_without_citation_sets_needs_citation():
    source = {"name": "05bd5cad-hoffman-2001-yirmiyahu.md"}
    meta = naming.meta_from_source(source)
    assert meta["needs_citation"] is True
    assert naming.display_name(meta) == "hoffman 2001 yirmiyahu"
    assert naming.drive_filename(meta, ".md", set()) == "hoffman 2001 yirmiyahu.md"


def test_missing_author_is_not_guessed():
    meta = naming.meta_from_source({"name": "abc12345-some_reading.pdf", "title": "Some Reading"})
    assert meta["needs_citation"] is True
    assert naming.display_name(meta) == "some reading"


def test_ref_citation_is_used_as_is():
    ref = {"citation": 'Test, Alpha. 1990. "History." Test Journal 1 (1): 1–2.'}
    meta = naming.meta_from_ref(ref)
    assert meta["needs_citation"] is False
    assert naming.display_name(meta) == 'Test, Alpha. 1990. "History." Test Journal 1 (1): 1–2'


def test_source_ref_citation_is_read():
    meta = naming.meta_from_source({"ref": {"citation": "Smith, Anna. 2001. Yirmiyahu Studies. Jerusalem: Test Press."}})
    assert meta["needs_citation"] is False
    assert naming.display_name(meta) == "Smith, Anna. 2001. Yirmiyahu Studies. Jerusalem: Test Press"


def test_drive_filename_collision():
    taken = set()
    first = naming.drive_filename(BOOK, ".pdf", taken)
    taken.add(first)
    second = naming.drive_filename(BOOK, ".pdf", taken)
    assert first == "Smith, Anna. 2001. Yirmiyahu Studies. Jerusalem: Test Press.pdf"
    assert second == "Smith, Anna. 2001. Yirmiyahu Studies. Jerusalem: Test Press (2).pdf"


def test_drive_filename_sanitise():
    meta = {"authors": ["Test, Alpha"], "year": "2005", "title": "Ritual/Law: a study", "journal": "J", "pages": "1-2"}
    name = naming.drive_filename(meta, ".pdf", set())
    assert "/" not in name and name.count("-") >= 1
    assert name.startswith("Test, Alpha. 2005.")
    assert name.endswith(".pdf")


def test_drive_filename_long_title_is_capped_on_word_boundary_and_keeps_year():
    meta = {"authors": ["Test, Alpha"], "year": "2010", "title": " ".join(["word"] * 80)}
    name = naming.drive_filename(meta, ".pdf", set())
    assert len(name) <= 200
    assert "2010" in name
    stem = name[:-len(".pdf")]
    assert stem.split(" ")[-1] == "word" or stem.endswith("word")
