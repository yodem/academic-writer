"""Extract text on request (`refs.py extract-queue`). Nothing in the course flows extracts text by itself.

A student ticks downloaded sources or readings on the dashboard and picks a method; the dashboard writes one job to
REG/queue/extract/<timestamp>-<course>.json:

    {"course": "cohen", "items": [{"kind": "source" | "ref", "key": "<sha8 | ref key>", "method": "auto"}], "created_at": "..."}

This module is the deterministic half of that job. It never calls a model and never OCRs.

- `plan(job, reg)` decides per item: `python` (a docx, or a PDF whose pages all have a text layer), `claude-vision`
  (a scan or an image; Claude reads the pages as pictures), or `external` (the student named `gemini-ocr` or
  `tesseract`). A PDF with a text layer on only some pages is `python` for those pages and hands the rest to Claude.
- `run_text_layer(path, ...)` does the python extraction: python-docx (pandoc if it is missing) for a docx; pymupdf for a
  PDF, per page, keeping the printed page number. Hebrew is never read with pdftotext, which garbles right-to-left text.
- A quality gate checks every Hebrew page (final letters at the start of a word, runs of single letters, glyph junk,
  a Latin page in a Hebrew document). A page that fails goes to Claude vision with the reason recorded.

Output: REG/extracted/<course>/<kind>-<key>.md (one `## עמוד` heading per page) and a `.json` next to it with the
method, the pages and the fallback pages. A page that needs Claude becomes a file in REG/queue/extract/handoff/ that
the nightly run's Claude step reads (see src/skills/courses/SKILL.md). Python 3.9 compatible.
"""
from __future__ import annotations

import fcntl
import json
import re
import shutil
import subprocess
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

METHODS = ("auto", "claude-vision", "gemini-ocr", "tesseract")
KINDS = ("source", "ref")
TEXT_PAGE_MIN_CHARS = 20          # fewer characters than this on a PDF page means "no text layer"
DOCX_SUFFIXES = (".docx", ".pptx")
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".heic")
MAX_ATTEMPTS = 3

HEB = re.compile(r"[א-ת]")
LATIN = re.compile(r"[A-Za-z]")
FINALS = set("ךםןףץ")
BIDI_CONTROLS = re.compile("[‎‏‪-‮⁦-⁩﻿]")
NIQQUD = re.compile("[֑-ׇ]")
PRIVATE_USE = re.compile("[-�]")
SAFE = re.compile(r"[^\w.\-]+", re.UNICODE)


class ExtractError(Exception):
    """A failure printed as one line."""


# --- paths ----------------------------------------------------------------------------------------

def _safe(key: str) -> str:
    return SAFE.sub("_", str(key)).strip("._") or "item"


def extracted_path(reg: Path, slug: str, kind: str, key: str) -> Path:
    """Where the extracted text of one item lives. Its existence is what the dashboard calls "has extracted text"."""
    return reg / "extracted" / slug / f"{kind}-{_safe(key)}.md"


def handoff_dir(reg: Path) -> Path:
    return reg / "queue" / "extract" / "handoff"


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _stamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def resolve_item(reg: Path, slug: str, kind: str, key: str) -> Optional[Path]:
    """The downloaded file behind a source (course.json `sources[].file`, matched by sha prefix) or a ref (`download_path`)."""
    if kind == "source":
        course = _read_json(reg / f"{slug}.json", {})
        for src in course.get("sources") or []:
            if isinstance(src, dict) and key and (str(src.get("sha8") or "") == key or str(src.get("sha256") or "").startswith(key)):
                return Path(str(src["file"])) if src.get("file") else None
    elif kind == "ref":
        for ref in (_read_json(reg / "refs" / f"{slug}.json", {}).get("refs") or []):
            if isinstance(ref, dict) and ref.get("key") == key and ref.get("download_path"):
                return Path(str(ref["download_path"])).expanduser()
    return None


def has_extracted_text(reg: Path, slug: str, kind: str, key: str) -> bool:
    return extracted_path(reg, slug, kind, key).is_file()


# --- text normalisation and the Hebrew gate -------------------------------------------------------

def normalise(text: str) -> str:
    """Presentation forms to plain letters, bidi controls and soft hyphens dropped, line ends tidied."""
    text = unicodedata.normalize("NFKC", text)
    text = BIDI_CONTROLS.sub("", text).replace("­", "")
    return "\n".join(line.rstrip() for line in text.splitlines()).strip()


def _hebrew_tokens(text: str) -> List[str]:
    return [t for t in (NIQQUD.sub("", w) for w in re.split(r"[\s\u05be\-\u2013\u2014/]+", text)) if HEB.search(t)]


def page_quality(text: str, *, expect_hebrew: bool = False) -> Tuple[bool, str]:
    """(ok, reason) for one page of extracted text. A simple sanity check, not a language model.

    Fails on: no characters; glyph junk (private-use or replacement characters, `(cid:N)`); a Hebrew final letter
    (ך ם ן ף ץ) at the start or in the middle of a word, which is what visual-order (reversed) text looks like; a high share of
    one-letter Hebrew tokens (isolated letters); and a page of Latin letters with no vowels when the document is Hebrew."""
    body = text.strip()
    if len(body) < TEXT_PAGE_MIN_CHARS:
        return False, "no-text-layer"
    if "(cid:" in body or len(PRIVATE_USE.findall(body)) > 0.03 * len(body):
        return False, "garbled-glyphs"
    tokens = _hebrew_tokens(body)
    heb, latin = len(HEB.findall(body)), len(LATIN.findall(body))
    if tokens:
        with_final = [t for t in tokens if FINALS & set(t)]
        bad = [t for t in with_final if any(c in FINALS for c in re.sub(r"[^א-ת]", "", t)[:-1])]
        if len(with_final) >= 3 and len(bad) / len(with_final) > 0.25:
            return False, "reversed-hebrew"
        single = [t for t in tokens if len(re.sub(r"[^א-ת]", "", t)) == 1]
        if len(tokens) >= 20 and len(single) / len(tokens) > 0.30:
            return False, "isolated-letters"
    if expect_hebrew and heb + latin >= 30 and heb / (heb + latin) < 0.15:
        words = [w for w in re.findall(r"[A-Za-z]{3,}", body)]
        odd = [w for w in words if not re.search(r"[aeiouyAEIOUY]", w)]
        if words and len(odd) / len(words) > 0.4:
            return False, "latin-junk"
    return True, "ok"


def printed_page_number(text: str) -> Optional[str]:
    """A bare 1-4 digit line at the top or bottom of the page (or `- 12 -`): the number printed on the page."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for line in (lines[-1:] + lines[:1]):
        m = re.fullmatch(r"[-–—\s]*(\d{1,4})[-–—\s]*", line)
        if m:
            return m.group(1)
    return None


# --- python extraction ----------------------------------------------------------------------------

def _import(name: str):
    try:
        return __import__(name)
    except ImportError:
        return None


def _block_order(blocks: Dict[int, List[float]], width: float, hebrew: bool, height: Optional[float] = None) -> List[int]:
    """Reading order of text blocks. The page is read as two columns only with real evidence: narrow blocks (under 60%
    of the page width) entirely in each half that sit side by side (their vertical ranges overlap). Inside
    that shared stretch a Hebrew page reads the right column first, any other page the left one, each top to bottom.
    Everything else (titles, centred lines, footnotes below the columns, full-width paragraphs) stays in plain
    top-to-bottom order and splits the stretch into bands. Without that evidence the whole page is top to bottom."""
    mid, tol = width / 2.0, width * 0.02
    # top to bottom; blocks starting at the same height follow the reading direction
    by_y = sorted(blocks, key=lambda b: (round(blocks[b][1]), -blocks[b][2] if hebrew else blocks[b][0]))

    def narrow(b: int) -> bool:
        return (blocks[b][2] - blocks[b][0]) < width * 0.6

    def beside(b: int, c: int) -> bool:  # their vertical ranges overlap
        return min(blocks[b][3], blocks[c][3]) > max(blocks[b][1], blocks[c][1])

    right_all = [b for b in by_y if blocks[b][0] >= mid - tol and narrow(b)]
    left_all = [b for b in by_y if blocks[b][2] <= mid + tol and narrow(b)]
    # a block is column text only when a block on the other side sits beside it (footnotes under the columns do not)
    right = [b for b in right_all if any(beside(b, c) for c in left_all)]
    left = [b for b in left_all if any(beside(b, c) for c in right_all)]
    tall = (height or max([blocks[b][3] for b in blocks] + [1.0])) * 0.10
    if (not right or not left or sum(blocks[b][3] - blocks[b][1] for b in right) < tall
            or sum(blocks[b][3] - blocks[b][1] for b in left) < tall):
        return by_y  # a running header (title one side, page number the other) is not two columns
    top = max(min(blocks[b][1] for b in right), min(blocks[b][1] for b in left))
    bottom = min(max(blocks[b][3] for b in right), max(blocks[b][3] for b in left))
    if bottom <= top:
        return by_y  # the two sides never sit next to each other: not columns
    side = {}
    for b in by_y:
        centre = (blocks[b][1] + blocks[b][3]) / 2.0
        inside = top - tol <= centre <= bottom + tol
        side[b] = ("right" if b in right else "left" if b in left else "full") if inside else "full"
    first, second = ("right", "left") if hebrew else ("left", "right")
    order: List[int] = []
    band: List[int] = []
    for b in by_y + [None]:
        if b is None or side[b] == "full":
            order += [x for x in band if side[x] == first] + [x for x in band if side[x] == second]
            band = []
            if b is not None:
                order.append(b)
        else:
            band.append(b)
    return order


def _page_text_rtl(page: Any) -> str:
    """One page in logical order. Within a line, pymupdf's word order is used (sorting by x would scramble
    right-to-left lines); lines keep their block's order; blocks are put in column reading order (`_block_order`),
    because a two-column page's content stream can hold the left column first."""
    words = page.get_text("words")  # x0, y0, x1, y1, word, block_no, line_no, word_no
    lines: Dict[Tuple[int, int], List[Tuple[int, str]]] = {}
    boxes: Dict[int, List[float]] = {}
    for w in words:
        b, k = int(w[5]), (int(w[5]), int(w[6]))
        lines.setdefault(k, []).append((int(w[7]), str(w[4])))
        box = boxes.setdefault(b, [w[0], w[1], w[2], w[3]])
        box[0], box[1], box[2], box[3] = min(box[0], w[0]), min(box[1], w[1]), max(box[2], w[2]), max(box[3], w[3])
    hebrew = len(HEB.findall(" ".join(str(w[4]) for w in words))) > len(re.findall(r"[A-Za-z]", " ".join(str(w[4]) for w in words)))
    rank = {b: i for i, b in enumerate(_block_order(boxes, float(page.rect.width), hebrew, float(page.rect.height)))}
    keys = sorted(lines, key=lambda k: (rank[k[0]], k[1]))
    return normalise("\n".join(" ".join(t for _, t in sorted(lines[k])) for k in keys))


def pdf_page_texts(path: Path) -> List[Dict[str, Any]]:
    """[{page, label, text}] per PDF page with pymupdf. Raises ExtractError when pymupdf is not installed."""
    fitz = _import("fitz")
    if fitz is None:
        raise ExtractError("pymupdf is not installed (pip install pymupdf)")
    out: List[Dict[str, Any]] = []
    with fitz.open(str(path)) as doc:
        for i, page in enumerate(doc, start=1):
            try:
                label = page.get_label() or None
            except Exception:
                label = None
            out.append({"page": i, "label": label, "text": _page_text_rtl(page)})
    return out


def inspect(path: Path) -> Dict[str, Any]:
    """Cheap look at a file: its type and, for a PDF, which pages have a text layer."""
    suffix = path.suffix.lower()
    if suffix in DOCX_SUFFIXES:
        return {"type": "docx"}
    if suffix in IMAGE_SUFFIXES:
        return {"type": "image"}
    if suffix == ".pdf":
        try:
            pages = pdf_page_texts(path)
        except ExtractError as exc:
            return {"type": "pdf", "error": str(exc)}
        except Exception as exc:  # a broken or encrypted PDF
            return {"type": "pdf", "error": f"unreadable pdf: {exc}"}
        text_pages = [p["page"] for p in pages if len(p["text"]) >= TEXT_PAGE_MIN_CHARS]
        scan_pages = [p["page"] for p in pages if len(p["text"]) < TEXT_PAGE_MIN_CHARS]
        return {"type": "pdf", "pages": len(pages), "text_pages": text_pages, "scan_pages": scan_pages}
    return {"type": "other"}


def plan_item(reg: Path, slug: str, item: Dict[str, Any]) -> Dict[str, Any]:
    """Decide how one item is extracted. `action` is `python`, `claude`, `external` or `skip`; `method` names the tool."""
    kind, key = str(item.get("kind")), str(item.get("key"))
    method = str(item.get("method") or "auto")
    entry: Dict[str, Any] = {"kind": kind, "key": key, "requested": method, "out": str(extracted_path(reg, slug, kind, key))}
    if kind not in KINDS or method not in METHODS:
        return {**entry, "action": "skip", "method": method, "reason": "unknown kind or method"}
    if has_extracted_text(reg, slug, kind, key):
        return {**entry, "action": "skip", "method": method, "reason": "already extracted"}
    file = resolve_item(reg, slug, kind, key)
    if file is None or not file.is_file():
        return {**entry, "action": "skip", "method": method, "reason": "no downloaded file"}
    entry["file"] = str(file)
    info = inspect(file)
    entry["type"] = info["type"]
    if info["type"] == "docx":  # a docx has text: the method choice only matters for scans
        return {**entry, "action": "python", "method": "python-docx"}
    if info["type"] == "other":
        return {**entry, "action": "skip", "method": method, "reason": "not a docx, pdf or image"}
    if method in ("gemini-ocr", "tesseract"):
        return {**entry, "action": "external", "method": method, "pages": "all"}
    if method == "claude-vision" or info["type"] == "image":
        return {**entry, "action": "claude", "method": "claude-vision", "pages": "all"}
    if info.get("error"):  # no pymupdf: do not guess with pdftotext (it garbles Hebrew); Claude reads the pages
        return {**entry, "action": "claude", "method": "claude-vision", "pages": "all", "reason": info["error"]}
    if not info["text_pages"]:
        return {**entry, "action": "claude", "method": "claude-vision", "pages": "all", "reason": "scanned pdf, no text layer"}
    return {**entry, "action": "python", "method": "pymupdf", "pages": info["pages"], "scan_pages": info["scan_pages"]}


def plan(job: Dict[str, Any], reg: Path) -> List[Dict[str, Any]]:
    """The plan for a whole job, one entry per item, in order."""
    slug = str(job.get("course") or "")
    return [plan_item(reg, slug, i) for i in job.get("items") or [] if isinstance(i, dict)]


def _docx_text(path: Path) -> Tuple[str, str]:
    docx = _import("docx")
    if docx is not None and path.suffix.lower() == ".docx":
        doc = docx.Document(str(path))
        parts = [p.text for p in doc.paragraphs]
        for table in doc.tables:
            for row in table.rows:
                parts.append(" | ".join(c.text.strip() for c in row.cells))
        return normalise("\n".join(parts)), "python-docx"
    if shutil.which("pandoc"):
        done = subprocess.run(["pandoc", "-t", "plain", "--wrap=none", str(path)], capture_output=True, text=True,
                              encoding="utf-8", check=True)
        return normalise(done.stdout), "pandoc"
    raise ExtractError("neither python-docx nor pandoc is installed")


def run_text_layer(path: Path, *, expect_hebrew: Optional[bool] = None) -> Dict[str, Any]:
    """Python extraction of one file. Returns {method, pages: [{page, label, printed, text}], fallback: [{page, reason}]}.

    `pages` holds the pages that passed the gate; `fallback` the pages Claude vision must read, with the reason."""
    if path.suffix.lower() in DOCX_SUFFIXES:
        text, method = _docx_text(path)
        return {"method": method, "pages": [{"page": 1, "label": None, "printed": None, "text": text}], "fallback": []}
    raw = pdf_page_texts(path)
    if expect_hebrew is None:  # the document's language decides whether a Latin page is junk
        heb = sum(len(HEB.findall(p["text"])) for p in raw)
        latin = sum(len(LATIN.findall(p["text"])) for p in raw)
        expect_hebrew = heb > latin
    kept, fallback = [], []
    for p in raw:
        ok, reason = page_quality(p["text"], expect_hebrew=expect_hebrew)
        if ok:
            kept.append({**p, "printed": printed_page_number(p["text"])})
        else:
            fallback.append({"page": p["page"], "reason": reason})
    return {"method": "pymupdf", "pages": kept, "fallback": fallback}


def render_markdown(title: str, result: Dict[str, Any]) -> str:
    """One `## עמוד N` heading per page: the printed number when the page shows one, else the PDF page; `pdf` keeps both."""
    out = [f"# {title}", "", f"<!-- extracted with {result['method']} -->", ""]
    for p in result["pages"]:
        shown = p.get("printed") or p.get("label") or p["page"]
        out += [f"## עמוד {shown} <!-- pdf:{p['page']} -->", "", p["text"], ""]
    if result["fallback"]:
        out += ["<!-- pages for Claude vision: " + ", ".join(f"{f['page']} ({f['reason']})" for f in result["fallback"]) + " -->", ""]
    return "\n".join(out)


def _finish(reg: Path, slug: str, entry: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    out = Path(entry["out"])
    out.parent.mkdir(parents=True, exist_ok=True)
    meta = {"course": slug, "kind": entry["kind"], "key": entry["key"], "file": entry.get("file"), "method": result["method"],
            "pages": [p["page"] for p in result["pages"]], "fallback": result["fallback"], "at": _stamp()}
    if result["pages"] or not result["fallback"]:
        out.write_text(render_markdown(f"{entry['kind']} {entry['key']}", result), encoding="utf-8")
    _write_json(out.with_suffix(".json"), meta)
    return meta


def write_handoff(reg: Path, slug: str, entry: Dict[str, Any], pages: Any, method: str, reason: str) -> Path:
    """A file the nightly Claude step reads: which file, which pages, which method, where to write the text."""
    path = handoff_dir(reg) / f"{slug}-{entry['kind']}-{_safe(entry['key'])}.json"
    main = Path(entry["out"])
    out = str(main) if pages == "all" else str(main.with_name(main.stem + ".claude.md"))  # the python pages already own `main`
    entry = {**entry, "out": out}
    _write_json(path, {"course": slug, "kind": entry["kind"], "key": entry["key"], "file": entry.get("file"), "pages": pages,
                       "method": method, "reason": reason, "out": out, "queued_at": _stamp(),
                       "instruction": _instruction(entry, pages, method)})
    return path


def _instruction(entry: Dict[str, Any], pages: Any, method: str) -> str:
    where = "all pages" if pages == "all" else f"pages {', '.join(str(p) for p in pages)}"
    how = {"claude-vision": "Render the pages to images and read them yourself (Read tool); transcribe exactly, keep printed page numbers.",
           "gemini-ocr": "Run `aw ocr` (Gemini). The student chose Gemini for this item.",
           "tesseract": "Run tesseract on the rendered pages. The student chose Tesseract for this item."}[method]
    return f"{how} Source: {entry.get('file')} ({where}). Write the text to {entry['out']} with one `## עמוד N` heading per page."


def pending_handoffs(reg: Path) -> List[Dict[str, Any]]:
    """Handoff files whose output is not there yet, oldest first. A finished one is removed here."""
    out = []
    folder = handoff_dir(reg)
    for path in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        data = _read_json(path, None)
        if not isinstance(data, dict):
            continue
        if data.get("out") and Path(str(data["out"])).is_file():
            path.unlink()
            continue
        out.append({**data, "handoff_file": path.name})
    return out


def ingest_dir(reg: Path) -> Path:
    return reg / "queue" / "extract" / "ingest"


def note_ingest(reg: Path, slug: str, entry: Dict[str, Any]) -> Optional[Path]:
    """A source the student chose that still has its `courses.py add-source` Trove job (queue/sources/<course>-<sha8>.json):
    record that the Trove ingest follows the extraction. Only a chosen file is ever ingested; nothing drains queue/sources itself."""
    if entry["kind"] != "source":
        return None
    job = reg / "queue" / "sources" / f"{slug}-{str(entry['key'])[:8]}.json"
    if not job.is_file():
        return None
    path = ingest_dir(reg) / f"{slug}-{_safe(entry['key'])}.json"
    _write_json(path, {"course": slug, "key": entry["key"], "sources_job": str(job), "text": entry["out"],
                       "queued_at": _stamp(),
                       "instruction": "After the extracted text exists, ingest it as the job says (course-book rules in "
                                      "skills/courses/references/course-book.md), then run source-done for the job."})
    return path


def pending_ingests(reg: Path) -> List[Dict[str, Any]]:
    """Chosen sources whose Trove job is still waiting. A file whose queue/sources job is gone (source-done moved it) is removed."""
    out = []
    folder = ingest_dir(reg)
    for path in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        data = _read_json(path, None)
        if not isinstance(data, dict):
            continue
        if not Path(str(data.get("sources_job", ""))).is_file():
            path.unlink()
            continue
        out.append({**data, "ingest_file": path.name})
    return out


def run_item(reg: Path, slug: str, entry: Dict[str, Any]) -> Dict[str, Any]:
    """Carry out one planned item: python now, hand the rest to Claude. Returns the per-item result."""
    if entry["action"] == "skip":
        return {"state": "skipped", "detail": entry.get("reason", "")}
    note_ingest(reg, slug, entry)
    if entry["action"] in ("claude", "external"):
        write_handoff(reg, slug, entry, entry.get("pages", "all"), entry["method"], entry.get("reason") or "requested")
        return {"state": "handoff", "method": entry["method"]}
    result = run_text_layer(Path(entry["file"]))
    meta = _finish(reg, slug, entry, result)
    if result["fallback"]:
        write_handoff(reg, slug, entry, [f["page"] for f in result["fallback"]], "claude-vision",
                      "; ".join(f"p{f['page']}: {f['reason']}" for f in result["fallback"]))
    return {"state": "ok" if not result["fallback"] else "partial", "method": result["method"], "pages": len(meta["pages"]),
            "fallback": result["fallback"]}


def drain(reg: Path, *, dry_run: bool = False) -> Dict[str, Any]:
    """Run every job in queue/extract/*.json, oldest first. Finished jobs move to queue/extract/done/.

    Python items are extracted here; claude-vision, gemini-ocr and tesseract items become handoff files for the nightly
    Claude step (`report["handoff"]` lists them). A job whose every item errored stays for the next run, up to MAX_ATTEMPTS."""
    folder = reg / "queue" / "extract"
    report: Dict[str, Any] = {"jobs": [], "dry_run": dry_run, "handoff": [], "ingest": []}
    if not folder.is_dir():
        return report
    lock = (folder / ".drain.lock").open("a+")
    fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
    try:
        for path in sorted(folder.glob("*.json")):
            job = _read_json(path, None)
            if not isinstance(job, dict) or not job.get("course") or not isinstance(job.get("items"), list):
                report["jobs"].append({"job": path.name, "status": "invalid"})
                continue
            slug = str(job["course"])
            plans = plan(job, reg)
            results: Dict[str, Any] = {}
            for entry in plans:
                label = f"{entry['kind']}:{entry['key']}"
                if dry_run:
                    results[label] = {"state": "planned", "action": entry["action"], "method": entry["method"],
                                      "reason": entry.get("reason", "")}
                    continue
                try:
                    results[label] = run_item(reg, slug, entry)
                except Exception as exc:  # a bad file must not stop the queue
                    results[label] = {"state": "error", "detail": str(exc)[:200]}
            errored = [k for k, v in results.items() if v.get("state") == "error"]
            entry_out: Dict[str, Any] = {"job": path.name, "course": slug, "results": results,
                                         "plan": [{k: e.get(k) for k in ("kind", "key", "action", "method", "reason")} for e in plans]}
            if plans and len(errored) == len(plans):
                attempts = int(job.get("attempts") or 0) + 1
                entry_out.update(attempts=attempts, status="failed" if attempts >= MAX_ATTEMPTS else "retry")
            else:
                entry_out["status"] = "done"
            report["jobs"].append(entry_out)
            if dry_run:
                continue
            job.update({"results": results, "status": entry_out["status"], "processed_at": _stamp()})
            if "attempts" in entry_out:
                job["attempts"] = entry_out["attempts"]
            if entry_out["status"] == "retry":
                job["status"] = "pending"
                _write_json(path, job)
            else:
                _write_json(folder / "done" / path.name, job)
                path.unlink()
    finally:
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        lock.close()
    report["handoff"] = pending_handoffs(reg) if not dry_run else []
    report["ingest"] = pending_ingests(reg) if not dry_run else []
    return report
