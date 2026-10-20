"""Chrome bookmark folders per course, rebuilt from the registry.

Each course gets one folder under the bookmarks bar, inside ``BIU <term>``. Its items are the
NotebookLM notebook, the Trove book, the Lemida course, the current task and that task's readings.
Nothing here starts Chrome: when Chrome is closed the run reports it and exits ``EXIT_CHROME``.
"""

from __future__ import annotations

import subprocess
import sys
from typing import Any, Callable

import chores
import courses

EXIT_CHROME = 5  # Chrome not running or osascript failing: the nightly step logs it, it is not fatal
# AppleScript must address Chrome by bundle id: the name "Google Chrome" resolves to "Google Chrome for Testing" here.
CHROME_BUNDLE_ID = "com.google.Chrome"
NOT_RUNNING = "not running"
ABSENT = "ABSENT"
US = "\x1f"  # field separator in the read-back text (titles and URLs never contain it)
RS = "\x1e"  # record separator in the read-back text
# Verified 2026-10-18 in a signed-in browser: this form opens the book at that page.
# Template with {book_id} and {page} placeholders; set to None to leave Trove items out.
TROVE_URL_FORM: str | None = "https://heytrove.ai/library/{book_id}?page={page}"


class BookmarkError(Exception):
    """Chrome or osascript could not be used. Raised before any change is confirmed."""


def trove_url(book_id: str, page: int | None = None) -> str | None:
    if not TROVE_URL_FORM:
        return None
    return TROVE_URL_FORM.format(book_id=book_id, page=1 if page is None else page)


def current_task(registry: courses.Registry, slug: str) -> dict[str, Any] | None:
    """The course's open chore due soonest; undated chores follow the dated ones, oldest first."""
    return min(chores.list_chores(registry, status="open", course=slug), key=chores._due_key, default=None)


def _reading_items(registry: courses.Registry, slug: str, task: dict[str, Any]) -> list[dict[str, str]]:
    """One item per core text that matches a source title and has a Trove page; nothing else."""
    by_title = {courses.normalise_name(str(s.get("title", ""))): s for s in registry.courses[slug].get("sources", [])}
    items = []
    for text in task.get("core_texts") or []:
        trove = (by_title.get(courses.normalise_name(text)) or {}).get("trove") or {}
        url = trove_url(str(trove.get("book_id", "")), trove.get("page")) if trove.get("book_id") and trove.get("page") else None
        if url:
            items.append({"title": text, "url": url})
    return items


def plan(registry: courses.Registry, slug: str) -> dict[str, Any]:
    """The folder and its items for one course. Items with an empty title or URL are left out."""
    course = registry.courses[slug]
    lemida = str(registry.term.get("lemida", {}).get("base_url", "")).rstrip("/")
    book_url = trove_url(str(course["book_id"])) if course.get("book_id") else None
    items: list[dict[str, str]] = []
    if course.get("notebook_id"):
        items.append({"title": "NotebookLM", "url": f"https://notebooklm.google.com/notebook/{course['notebook_id']}"})
    if book_url:
        items.append({"title": "Trove", "url": book_url})
    if lemida and course.get("lemida_course_id"):
        items.append({"title": "Lemida", "url": f"{lemida}/course/view.php?id={course['lemida_course_id']}"})
    task = current_task(registry, slug)
    if task:
        task_url = courses.lemida_module_url(lemida, course, task.get("ref"), str(task.get("kind", "")))
        if task_url:
            items.append({"title": str(task.get("title", "")), "url": task_url})
        readings = _reading_items(registry, slug, task)
        # no reading maps to a page: the course's Trove book stands in, once
        if not readings and book_url and book_url not in {item["url"] for item in items}:
            readings = [{"title": "Trove", "url": book_url}]
        items.extend(readings)
    return {
        "course": slug,
        "root": f"BIU {registry.term['term']}",
        "folder": str(course.get("name") or slug),
        "items": [item for item in items if item["title"] and item["url"]],
    }


def _q(text: str) -> str:
    """An AppleScript string literal: backslash and double quote are the only characters to escape."""
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


_FIND_HANDLER = f"""on findFolder(parentFolder, folderName)
	tell application id "{CHROME_BUNDLE_ID}"
		repeat with f in (bookmark folders of parentFolder)
			if title of f is folderName then return f
		end repeat
	end tell
	return missing value
end findFolder
"""

# The only handler that creates folders: the read-only script must not carry it.
_ENSURE_HANDLER = f"""on ensureFolder(parentFolder, folderName)
	tell application id "{CHROME_BUNDLE_ID}"
		repeat with f in (bookmark folders of parentFolder)
			if title of f is folderName then return f
		end repeat
		return make new bookmark folder with properties {{title:folderName}} at end of bookmark folders of parentFolder
	end tell
end ensureFolder

"""


def _apply_lines(p: dict[str, Any]) -> str:
    """Replace one planned folder: create it if missing, empty it, then write its items in plan order."""
    lines = [
        f"\t\tset rootF to my ensureFolder(bookmarks bar, {_q(p['root'])})",
        f"\t\tset courseF to my ensureFolder(rootF, {_q(p['folder'])})",
        "\t\tdelete every bookmark item of courseF",
        "\t\tdelete every bookmark folder of courseF",
    ]
    lines += [
        f"\t\tmake new bookmark item with properties {{title:{_q(i['title'])}, URL:{_q(i['url'])}}} at end of bookmark items of courseF"
        for i in p["items"]
    ]
    return "\n".join(lines) + "\n"


def _read_lines(p: dict[str, Any]) -> str:
    """Read one planned folder into `out`: its name, then fieldSep-separated title/URL pairs, then recSep."""
    lines = [
        f"\t\tset rootF to my findFolder(bookmarks bar, {_q(p['root'])})",
        "\t\tset courseF to missing value",
        f"\t\tif rootF is not missing value then set courseF to my findFolder(rootF, {_q(p['folder'])})",
        "\t\tif courseF is missing value then",
        f"\t\t\tset out to out & {_q(p['folder'])} & fieldSep & {_q(ABSENT)} & recSep",
        "\t\telse",
        f"\t\t\tset out to out & {_q(p['folder'])}",
        "\t\t\trepeat with b in (bookmark items of courseF)",
        "\t\t\t\tset out to out & fieldSep & (title of b) & fieldSep & (URL of b)",
        "\t\t\tend repeat",
        "\t\t\tset out to out & recSep",
        "\t\tend if",
    ]
    return "\n".join(lines) + "\n"


def build_script(plans: list[dict[str, Any]]) -> str:
    """The AppleScript that replaces each planned folder's contents. Running it twice changes nothing new."""
    return (
        _ENSURE_HANDLER
        + _FIND_HANDLER
        + "\non run\n"
        + f'\tif application id "{CHROME_BUNDLE_ID}" is not running then return "{NOT_RUNNING}"\n'
        + f'\ttell application id "{CHROME_BUNDLE_ID}"\n'
        + "".join(_apply_lines(p) for p in plans)
        + "\tend tell\n"
        + '\treturn "ok"\nend run\n'
    )


def read_script(plans: list[dict[str, Any]]) -> str:
    """Read-only AppleScript: prints each planned folder as it stands, in the layout `_record` expects."""
    return (
        _FIND_HANDLER
        + "\non run\n"
        + f'\tif application id "{CHROME_BUNDLE_ID}" is not running then return "{NOT_RUNNING}"\n'
        + "\tset fieldSep to ASCII character 31\n\tset recSep to ASCII character 30\n\tset out to \"\"\n"
        + f'\ttell application id "{CHROME_BUNDLE_ID}"\n'
        + "".join(_read_lines(p) for p in plans)
        + "\tend tell\n\treturn out\nend run\n"
    )


def _record(p: dict[str, Any]) -> str:
    """What the read script must print for a planned folder that already matches the plan."""
    return p["folder"] + "".join(US + i["title"] + US + i["url"] for i in p["items"]) + RS


def run_osascript(script: str, runner: Callable[..., Any] = subprocess.run) -> str:
    try:
        done = runner(["osascript", "-"], input=script, encoding="utf-8", capture_output=True, check=False)
    except OSError as exc:
        raise BookmarkError(f"osascript could not start: {exc}") from exc
    if done.returncode != 0:
        raise BookmarkError(f"osascript failed (exit {done.returncode}): {(done.stderr or '').strip()}")
    out = (done.stdout or "").rstrip("\n")
    if out == NOT_RUNNING:
        raise BookmarkError("Google Chrome is not running; open Chrome and run again")
    return out


def check(plans: list[dict[str, Any]], runner: Callable[..., Any] = subprocess.run) -> bool:
    """True when the folders in Chrome already hold exactly what applying the plans would write."""
    return run_osascript(read_script(plans), runner) == "".join(_record(p) for p in plans)


def run(registry: courses.Registry, *, slug: str | None = None, all_courses: bool = False, print_script: bool = False,
        check_only: bool = False, runner: Callable[..., Any] = subprocess.run) -> int:
    if bool(slug) == all_courses:
        print("bookmarks: give one course slug or --all", file=sys.stderr)
        return 2
    if slug and slug not in registry.courses:
        raise ValueError(f"unknown course {slug!r}")
    plans = [plan(registry, s) for s in (sorted(registry.courses) if all_courses else [slug])]
    if print_script:
        print(build_script(plans))
        return 0
    try:
        if check_only:
            up_to_date = check(plans, runner)
            print("bookmarks: up to date" if up_to_date else "bookmarks: applying would change Chrome")
            return 0 if up_to_date else 1
        run_osascript(build_script(plans), runner)
    except BookmarkError as exc:
        print(f"bookmarks: {exc}", file=sys.stderr)
        return EXIT_CHROME
    print(f"bookmarks: {len(plans)} folder(s) written")
    return 0
