#!/usr/bin/env python3
"""Per-user academic course registry and resource validator.

The registry is deliberately external to this plugin. Its files are JSON so
they can be reviewed and edited without installing a package.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import unicodedata
import zipfile
from pathlib import Path
from typing import Any, Callable
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
CODE_RE = re.compile(r"(?<!\d)(?:\d{6}(?:-\d{2})?|\d{5}(?:-\d{2})?|\d{2}-\d{3}-\d{2})(?!\d)")


def normalise_name(value: str) -> str:
    """Collapse whitespace and treat Hebrew quote variants consistently."""
    value = unicodedata.normalize("NFC", value)
    value = value.replace("״", '"').replace("׳", "'")
    return " ".join(value.split())


def _term_dir(root: Path, term: str | None = None) -> Path:
    if term is None:
        term = os.environ.get("ACADEMIC_TERM")
    if term:
        return root / term
    dirs = sorted(p for p in root.iterdir() if p.is_dir()) if root.exists() else []
    if len(dirs) == 1:
        return dirs[0]
    if (root / "term.json").is_file():
        return root
    raise ValueError(f"term is required; use --term or ACADEMIC_TERM under {root}")


class Registry:
    def __init__(self, directory: Path):
        self.directory = directory
        self.term = json.loads((directory / "term.json").read_text(encoding="utf-8"))
        self.courses: dict[str, dict[str, Any]] = {}
        for path in sorted(directory.glob("*.json")):
            if path.name == "term.json":
                continue
            course = json.loads(path.read_text(encoding="utf-8"))
            slug = course.get("slug", path.stem)
            self.courses[slug] = course


def registry_from_args(args: argparse.Namespace) -> Registry:
    root = Path(os.environ.get("ACADEMIC_COURSES_DIR", "~/.academic-writer/courses")).expanduser()
    return Registry(_term_dir(root, args.term))


def _json_from_command(command: list[str], runner: Callable[..., Any]) -> Any:
    result = runner(command, check=True, text=True, capture_output=True)
    return json.loads(result.stdout)


def _as_list(value: Any, *keys: str) -> list[dict[str, Any]]:
    for key in keys:
        if isinstance(value, dict) and isinstance(value.get(key), list):
            return value[key]
    if isinstance(value, list):
        return value
    raise ValueError("expected a JSON list")


def validate_registry(registry: Registry, runner: Callable[..., Any] = subprocess.run) -> list[str]:
    """Return one actionable mismatch per absent resource or name mismatch."""
    problems: list[str] = []
    try:
        notebooks = _as_list(_json_from_command(["nlm", "notebook", "list"], runner), "notebooks", "items")
    except Exception as exc:
        return [f"NotebookLM lookup failed: {exc}"]
    try:
        manuscripts = _as_list(_json_from_command(["trove", "ms", "list", "--json", "--no-session"], runner), "manuscripts", "items")
    except Exception as exc:
        return [f"Trove lookup failed: {exc}"]
    notebook_by_id = {str(x.get("id")): x for x in notebooks}
    manuscript_by_id = {str(x.get("id")): x for x in manuscripts}

    drive_cache: dict[str, list[dict[str, Any]] | Exception] = {}
    remote = registry.term.get("drive_remote", "gdrive")
    subject_map = registry.term.get("drive_subject_folders", {})
    naming = registry.term.get("naming", {})
    for slug, course in registry.courses.items():
        expected = {
            "drive": naming.get("drive", "{name}").format(**course, term=registry.term.get("term", "")),
            "notebook": naming.get("notebook", "{name}").format(**course, term=registry.term.get("term", "")),
            "manuscript": naming.get("manuscript", "{name}").format(**course, term=registry.term.get("term", "")),
        }
        for key in ("drive_folder_id", "notebook_id", "manuscript_id"):
            if not course.get(key):
                problems.append(f"{slug}: missing {key}")
        notebook_id = course.get("notebook_id")
        if notebook_id:
            obj = notebook_by_id.get(str(notebook_id))
            if obj is None:
                problems.append(f"{slug}: NotebookLM notebook {notebook_id} not found")
            elif normalise_name(str(obj.get("title", ""))) != normalise_name(expected["notebook"]):
                problems.append(f"{slug}: NotebookLM name mismatch (expected {expected['notebook']!r}, got {obj.get('title')!r})")
        manuscript_id = course.get("manuscript_id")
        if manuscript_id:
            obj = manuscript_by_id.get(str(manuscript_id))
            if obj is None:
                problems.append(f"{slug}: Trove manuscript {manuscript_id} not found")
            elif normalise_name(str(obj.get("title", ""))) != normalise_name(expected["manuscript"]):
                problems.append(f"{slug}: Trove name mismatch (expected {expected['manuscript']!r}, got {obj.get('title')!r})")
        drive_id = course.get("drive_folder_id")
        if drive_id:
            label = course.get("drive_subject_folder") or course.get("drive_subject")
            subject_id = subject_map.get(label, label)
            if not subject_id:
                problems.append(f"{slug}: no Drive subject folder configured")
                continue
            if subject_id not in drive_cache:
                try:
                    result = runner(["rclone", "lsjson", f"{remote}:", "--drive-root-folder-id", str(subject_id), "--dirs-only"], check=True, text=True, capture_output=True)
                    drive_cache[subject_id] = json.loads(result.stdout)
                except Exception as exc:
                    drive_cache[subject_id] = exc
            listing = drive_cache[subject_id]
            if isinstance(listing, Exception):
                problems.append(f"{slug}: Drive lookup failed: {listing}")
                continue
            obj = next((x for x in listing if str(x.get("ID", x.get("id", ""))) == str(drive_id)), None)
            if obj is None:
                problems.append(f"{slug}: Drive folder {drive_id} not found under subject folder {label or subject_id}")
            elif normalise_name(str(obj.get("Name", obj.get("name", "")))) != normalise_name(expected["drive"]):
                problems.append(f"{slug}: Drive name mismatch (expected {expected['drive']!r}, got {obj.get('Name', obj.get('name'))!r})")
    return problems


def _cell_paragraphs(cell: ET.Element) -> list[str]:
    """Keep paragraph/line-break boundaries, including multiple runs."""
    out: list[str] = []
    for paragraph in cell.findall(".//" + W + "p"):
        parts: list[str] = []
        for node in paragraph.iter():
            if node.tag == W + "t":
                parts.append(node.text or "")
            elif node.tag == W + "br":
                parts.append("\n")
        out.extend(line.strip() for line in "".join(parts).splitlines() if line.strip())
        joined = "".join(parts).strip()
        if joined and "\n" not in joined and joined.strip() not in out[-1:]:
            # A paragraph containing only regular text was already emitted.
            pass
    return out


def _cell_text(cell: ET.Element) -> str:
    return "\n".join(_cell_paragraphs(cell))


def parse_docx(path: Path) -> list[dict[str, Any]]:
    """Parse a BIU-like timetable table into reviewable course stubs."""
    with zipfile.ZipFile(path) as zf:
        root = ET.fromstring(zf.read("word/document.xml"))
    tables = root.findall(".//" + W + "tbl")
    if not tables:
        raise ValueError("DOCX contains no tables")
    table = max(tables, key=lambda t: len(t.findall("./" + W + "tr")))
    rows: list[list[dict[str, Any]]] = []
    for tr in table.findall("./" + W + "tr"):
        cells = []
        for tc in tr.findall("./" + W + "tc"):
            text = _cell_text(tc)
            span_el = tc.find("./" + W + "tcPr/" + W + "gridSpan")
            span = int(span_el.get(W + "val", "1")) if span_el is not None else 1
            merge_el = tc.find("./" + W + "tcPr/" + W + "vMerge")
            cells.append({"text": text, "span": span, "merge": merge_el is not None, "continuation": merge_el is not None and merge_el.get(W + "val") is None})
        rows.append(cells)
    if not rows:
        return []

    # Expand physical cells onto the table grid; row 0 provides the weekday headers.
    expanded: list[list[dict[str, Any] | None]] = []
    for row in rows:
        grid: list[dict[str, Any] | None] = []
        for cell in row:
            grid.extend([cell] * cell["span"])
        expanded.append(grid)
    width = max(map(len, expanded))
    expanded = [r + [None] * (width - len(r)) for r in expanded]
    headers: list[tuple[int, int, str]] = []
    head = expanded[0]
    col = 0
    while col < width:
        cell = head[col]
        if cell and cell["text"]:
            span = 1
            while col + span < width and head[col + span] is cell:
                span += 1
            label = cell["text"].splitlines()[0].strip()
            if re.search(r"ראשון|שני|שלישי|רביעי|חמישי|שישי|שבת|יום א|יום ב|יום ג|יום ד|יום ה|יום ו", label):
                headers.append((col, col + span, label))
            col += span
        else:
            col += 1
    stubs: list[dict[str, Any]] = []
    carry: dict[int, str] = {}
    for row in expanded[1:]:
        row_text = " ".join(c["text"] for c in row if c and c["text"])
        time_match = re.search(r"(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})", row_text)
        if not time_match:
            continue
        start, end = time_match.groups()
        for first, last, day_label in headers:
            for subcol in range(first, last):
                cell = row[subcol]
                if cell and cell["merge"] and cell["continuation"]:
                    text = carry.get(subcol, "")
                elif cell and cell["text"]:
                    text = cell["text"]
                    carry[subcol] = text
                else:
                    continue
                if subcol > first and row[subcol - 1] is cell:
                    continue
                same_cell_span = 1
                while subcol + same_cell_span < last and row[subcol + same_cell_span] is cell:
                    same_cell_span += 1
                if same_cell_span > 1 and subcol % 2 == first % 2:
                    semester = "yearly"
                elif same_cell_span > 1:
                    continue
                else:
                    semester = "A" if (subcol - first) % 2 == 0 else "B"
                if not text or re.fullmatch(r"\d{1,2}:\d{2}\s*[-–]\s*\d{1,2}:\d{2}", text):
                    continue
                code_match = CODE_RE.search(text)
                lines = [line.strip() for line in text.splitlines() if line.strip()]
                name = next((line for line in lines if not CODE_RE.search(line) and not re.search(r"נ[״׳']?ז|נ" + '"' + r"?ז", line)), lines[0])
                lecturer = next((line for line in lines if re.search(r"פרופ|ד״ר|ד׳ר|ד'ר|דוקטור", line)), "")
                day = next((d for d, pattern in [("Sun", "ראשון|א׳|א'"), ("Mon", "שני|ב׳|ב'"), ("Tue", "שלישי|ג׳|ג'"), ("Wed", "רביעי|ד׳|ד'"), ("Thu", "חמישי|ה׳|ה'"), ("Fri", "שישי|ו׳|ו'")] if re.search(pattern, day_label)), day_label)
                stubs.append({"code": code_match.group(0) if code_match else None, "name": name, "lecturer": lecturer or None, "credits": next((re.search(r"\d+(?:\.\d+)?\s*נ[״׳']?ז", line).group(0) for line in lines if re.search(r"\d+(?:\.\d+)?\s*נ[״׳']?ז", line)), None), "slots": [{"day": day, "start": start, "end": end, "semester": semester}]})
    return stubs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--term", help="term directory name (defaults to ACADEMIC_TERM or the sole configured term)")
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate", help="validate all configured live course resources")
    validate.add_argument("--json", action="store_true", help="emit mismatch list as JSON")
    imp = sub.add_parser("import-docx", help="extract schedule rows into course stubs for review")
    imp.add_argument("docx", type=Path)
    imp.add_argument("--out", type=Path, help="directory to write one JSON stub per course")
    imp.add_argument("--dry-run", action="store_true", help="print stubs without writing")
    args = parser.parse_args(argv)
    try:
        if args.command == "import-docx":
            stubs = parse_docx(args.docx)
            if args.out and not args.dry_run:
                args.out.mkdir(parents=True, exist_ok=True)
                for i, stub in enumerate(stubs, 1):
                    (args.out / f"course-{i:02d}.json").write_text(json.dumps(stub, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(stubs, ensure_ascii=False, indent=2))
            return 0
        registry = registry_from_args(args)
        problems = validate_registry(registry)
        if args.json:
            print(json.dumps({"valid": not problems, "mismatches": problems}, ensure_ascii=False))
        else:
            for problem in problems:
                print(problem)
            if not problems:
                print(f"Validated {len(registry.courses)} courses")
        return 1 if problems else 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
