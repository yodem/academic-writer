"""Course references: find the sources a course cites, look them up in BIU Primo, record the decision, render the page.

Registry layout (one term directory): REG/refs/<slug>.json holds {"course", "_note", "refs": [...]}. Each ref has
key, citation, pages_cited, role, found_in, status, note, and optionally target_url (online), call_number (print-only)
and trove_url (ingested). Sources come from REG/sources/<slug>/ (.docx and .pptx through pandoc; .pdf is skipped
because pandoc cannot read it) and REG/lessons/<slug>/*/transcript.txt (spoken, so every candidate is unverified).

Stdlib plus a pandoc subprocess only. The one network call is fetch_url; tests replace it.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import html
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from datetime import datetime
from collections import Counter
from pathlib import Path
from typing import Any, Callable

PRIMO = "https://biu.primo.exlibrisgroup.com/primaws/rest/pub/pnxs"
PRIMO_BASE = {"vid": "972BIU_INST:BIUNDE", "tab": "Everything", "scope": "MyInst_and_CI",
              "inst": "972BIU_INST", "lang": "he", "offset": "0", "limit": "5",
              "skipDelivery": "N", "disableSplitFacets": "true"}
STATUSES = ("pending", "online", "downloaded", "ingested", "kotar", "print-only", "not-found")
SOURCE_SUFFIXES = (".docx", ".pptx")
PAGE_MARK = re.compile(r"עמ['׳’]|pp\.")
CHORE_KIND = {"kotar": "kotar-source", "print-only": "manual", "not-found": "manual"}
COURSES_PY = Path(__file__).resolve().with_name("courses.py")

ANNAS_SCRIPT = Path(os.environ.get("ANNAS_ARCHIVE_SCRIPT", "~/.claude/skills/annas-archive-ebooks/annas.py")).expanduser()
OCR_POLICY = ("gemini-text-first", "tesseract-hidden-check", "empty-gemini-page-blocked")

Fetch = Callable[[str], str]


class RefsError(Exception):
    """A failure the user can fix: printed as one line, exit 2."""


def fetch_url(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read().decode("utf-8", "replace")


# --- BIU Primo lookup (ported from biu_lookup.py) -------------------------------------------------

def search(query: str, fetch: Fetch = fetch_url) -> list[dict[str, Any]]:
    params = dict(PRIMO_BASE, q=f"any,contains,{query}")
    return json.loads(fetch(PRIMO + "?" + urllib.parse.urlencode(params))).get("docs", [])


def _cto_key(block: str, name: str) -> str:
    match = re.search(rf'<key id="{name}">([^<]*)', block)
    return html.unescape(match.group(1)) if match else ""


def resolve(openurl: str, fetch: Fetch = fetch_url) -> list[dict[str, str]]:
    """Alma OpenURL (svc_dat=CTO) to the list of services: package, type, free flag and target URL."""
    xml = fetch(openurl.replace("svc_dat=viewit", "svc_dat=CTO").replace(" ", "%20"))
    services = []
    for block in re.findall(r"<context_service .*?</context_service>", xml, re.S):
        target = re.search(r"<target_url>([^<]*)", block)
        services.append({"package": _cto_key(block, "package_display_name"),
                         "type": _cto_key(block, "service_type_description"),
                         "free": _cto_key(block, "Is_free"),
                         "target_url": html.unescape(target.group(1)) if target else ""})
    return services


def classify(services: list[dict[str, str]], availability: str, holding: list[Any]) -> tuple[str | None, str]:
    """Suggested status and call number. Kotar wins; None means the agent decides."""
    if any("kotar" in service["package"].lower() for service in services):
        return "kotar", ""
    if services:
        return "online", ""
    if availability == "available_in_library":
        # The holding field name is not confirmed against a live response; tolerate it being absent.
        call = next((h.get("callNumber") or "" for h in holding if isinstance(h, dict) and h.get("callNumber")), "")
        return "print-only", call
    return None, ""


QUERY_STOP = {"בתוך", "עורכת", "עורך", "עורכים", "in", "ed", "eds", "vol", "pp", "p"}


def primo_query(citation: str, words: int = 5) -> str:
    """Short author and title words for Primo. Full citations with quotes, commas and page refs return nothing."""
    text = re.sub(r"\b(?:עמ'|עמ׳|pp?\.)\s*[\d–-].*$", "", clean_markdown(citation))  # drop the page reference
    text = re.sub(r"[\"'“”„׳״,:;()\[\]{}.]", " ", text)
    kept = [w for w in text.split() if len(w) > 1 and w.lower() not in QUERY_STOP]  # single letters are initials
    return " ".join(kept[:words])


def propose(citation: str, fetch: Fetch = fetch_url, query: str | None = None) -> list[dict[str, Any]]:
    """Up to three Primo hits for a citation, with a suggested status. Changes nothing on disk."""
    hits = []
    for doc in search(query or primo_query(citation), fetch)[:3]:
        display, delivery = doc["pnx"]["display"], doc.get("delivery", {})
        hit: dict[str, Any] = {"title": (display.get("title") or [""])[0][:120],
                               "type": (display.get("type") or [""])[0],
                               "part_of": (display.get("ispartof") or [""])[0][:120],
                               "availability": (delivery.get("availability") or [""])[0],
                               "services": []}
        if delivery.get("almaOpenurl"):
            try:
                hit["services"] = resolve(delivery["almaOpenurl"], fetch)
            except Exception as exc:  # a resolver hiccup keeps the hit, marked
                hit["resolve_error"] = str(exc)[:100]
        hit["suggested_status"], hit["call_number"] = classify(hit["services"], hit["availability"],
                                                              delivery.get("holding", []))
        hits.append(hit)
    return hits


# --- registry and files ---------------------------------------------------------------------------

def registry_dir(registry: Path | None, term: str | None) -> Path:
    if registry is not None:
        return registry.expanduser()
    root = Path(os.environ.get("ACADEMIC_COURSES_DIR", "~/.academic-writer/courses")).expanduser()
    term = term or os.environ.get("ACADEMIC_TERM")
    if term:
        return root / term
    dirs = sorted(p for p in root.iterdir() if p.is_dir()) if root.is_dir() else []
    if len(dirs) == 1:
        return dirs[0]
    if (root / "term.json").is_file():
        return root
    raise RefsError(f"term is required: pass --term or set ACADEMIC_TERM (terms live under {root})")


def refs_path(reg: Path, slug: str) -> Path:
    return reg / "refs" / f"{slug}.json"


def load_refs(reg: Path, slug: str) -> dict[str, Any]:
    path = refs_path(reg, slug)
    if not path.is_file():
        raise RefsError(f"no refs file for {slug}: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data.get("refs"), list):
        raise RefsError(f"{path}: 'refs' must be a list")
    return data


def save_json(path: Path, payload: Any) -> None:
    """Atomic replace, so a crash never leaves a half-written refs file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    with os.fdopen(handle, "w", encoding="utf-8") as out:
        out.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    os.replace(tmp, path)


def make_key(citation: str) -> str:
    """Deterministic dedupe key: first Latin word, year, and a short hash. Hebrew-only citations get 'ref'."""
    norm = " ".join(citation.split())
    year = re.search(r"\b(1[5-9]\d\d|20\d\d)\b", norm)
    # The first Latin word that is not an editor or page marker ("pp.", "ed.", "eds.", "vol.").
    author = next((w for w in re.findall(r"[A-Za-z][A-Za-z'-]*", norm)
                   if w.lower() not in {"pp", "p", "ed", "eds", "vol", "vols", "in", "the", "and"}), None)
    name = re.sub(r"[^a-z]", "", author.lower()) if author else ""
    digest = hashlib.sha1(norm.encode("utf-8")).hexdigest()[:6]
    return f"{name or 'ref'}-{year.group(1) if year else 'nd'}-{digest}"


# --- extract --------------------------------------------------------------------------------------

def run_pandoc(path: Path) -> str:
    result = subprocess.run(["pandoc", "-t", "markdown", str(path)], capture_output=True, text=True,
                            encoding="utf-8", check=True)
    return result.stdout


ESCAPED = re.compile(r"\\([!\"#$%&'()*+,\-./:;<=>?@\[\]^_`{|}~\\])")  # pandoc escapes quotes, dashes, apostrophes
SPAN = re.compile(r"\[([^\[\]]*)\]\{[^{}]*\}")  # [text]{dir="rtl"} and [text]{.underline}; nested spans unwrap inside-out


def clean_markdown(text: str) -> str:
    """Pandoc markdown to plain citation text: unescape, unwrap spans, drop emphasis and soft hyphens."""
    text = ESCAPED.sub(r"\1", text)
    previous = None
    while previous != text:
        previous, text = text, SPAN.sub(r"\1", text)
    return text.replace("*", "").replace("\u00ad", "")


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<!pp\.)(?<=[.!?])\s+", text) if s.strip()]


def file_candidates(label: str, text: str, *, transcript: bool = False) -> tuple[list[dict[str, str]], int]:
    """Footnote bodies (every one) and page-marked sentences, plus the marker count for the sanity line."""
    text = clean_markdown(text)
    candidates = []
    prose = []
    for block in re.split(r"\n\s*\n", text):
        block = " ".join(block.split())
        note = re.match(r"\[\^(\d+)\]:\s*(.*)", block)
        if note:
            candidates.append((f"{label}, footnote {note.group(1)}", note.group(2)))
        elif block:
            prose.append(re.sub(r"\[\^\d+\]", "", block))
    for paragraph in prose:
        candidates += [(label, sentence) for sentence in _split_sentences(paragraph) if PAGE_MARK.search(sentence)]
    out = []
    for where, citation in candidates:
        if not citation:
            continue
        found_in = f"{where} (transcript, unverified)" if transcript else where
        out.append({"key": make_key(citation), "citation": citation, "found_in": found_in})
    return out, len(PAGE_MARK.findall(text))


def extract(reg: Path, slug: str, runner: Callable[[Path], str] = run_pandoc) -> tuple[list[dict[str, str]], list[str]]:
    candidates: list[dict[str, str]] = []
    report: list[str] = []
    sources = reg / "sources" / slug
    for path in sorted(p for p in sources.rglob("*") if p.is_file()) if sources.is_dir() else []:
        label = path.relative_to(reg).as_posix()
        if path.suffix.lower() not in SOURCE_SUFFIXES:
            report.append(f"skipped {label}: pandoc cannot read this type (PDF text is not extracted here)")
            continue
        try:
            markdown = runner(path)
        except (OSError, subprocess.CalledProcessError) as exc:
            report.append(f"skipped {label}: pandoc failed ({exc})")
            continue
        found, hits = file_candidates(label, markdown)
        candidates += found
        report.append(f"sanity {label}: {hits} page-marker hits, {len(found)} candidates proposed")
    for path in sorted((reg / "lessons" / slug).glob("*/transcript.txt")):
        label = path.relative_to(reg).as_posix()
        found, hits = file_candidates(label, path.read_text(encoding="utf-8"), transcript=True)
        candidates += found
        report.append(f"sanity {label}: {hits} page-marker hits, {len(found)} candidates proposed")
    return candidates, report


def write_candidates(reg: Path, slug: str, candidates: list[dict[str, str]], only: list[str] | None = None) -> int:
    """Append chosen candidates as pending refs. Existing refs are never touched.

    `only` limits the write to the keys the agent confirmed; an unknown key is an error, so a typo cannot
    silently drop a ref. A candidate is skipped when its key or its exact citation is already recorded.
    """
    path = refs_path(reg, slug)
    data = load_refs(reg, slug) if path.is_file() else {"course": slug, "_note": "", "refs": []}
    if only is not None:
        offered = {item["key"] for item in candidates}
        unknown = sorted(set(only) - offered)
        if unknown:
            raise RefsError(f"not among the candidates: {', '.join(unknown)}")
        candidates = [item for item in candidates if item["key"] in set(only)]
    seen = {ref.get("key") for ref in data["refs"]}
    cited = {" ".join(str(ref.get("citation", "")).split()) for ref in data["refs"]}
    added = 0
    for item in candidates:
        if item["key"] in seen or " ".join(item["citation"].split()) in cited:
            continue
        seen.add(item["key"])
        cited.add(" ".join(item["citation"].split()))
        data["refs"].append({"key": item["key"], "citation": item["citation"], "pages_cited": "",
                             "role": "quoted", "found_in": item["found_in"], "status": "pending", "note": ""})
        added += 1
    if added:
        save_json(path, data)
    return added


# --- lookup and decisions -------------------------------------------------------------------------

def lookup_pending(reg: Path, slug: str, key: str | None = None, fetch: Fetch = fetch_url,
                   query: str | None = None) -> list[dict[str, Any]]:
    results = []
    for ref in load_refs(reg, slug)["refs"]:
        if ref.get("status") != "pending" or (key and ref.get("key") != key):
            continue
        try:
            hits = propose(ref.get("citation", ""), fetch, query=query)
        except (OSError, ValueError) as exc:  # network or malformed Primo reply; name the ref, keep going
            raise RefsError(f"Primo lookup failed for {ref.get('key')}: {exc}") from exc
        results.append({"key": ref.get("key"), "citation": ref.get("citation", ""), "hits": hits})
    if key and not results:
        raise RefsError(f"no pending ref with key {key} in {slug}")
    return results


def record_decision(reg: Path, slug: str, key: str, status: str, *, note: str | None = None,
                    target_url: str | None = None, trove_url: str | None = None,
                    call_number: str | None = None) -> None:
    if status not in STATUSES:
        raise RefsError(f"status must be one of {', '.join(STATUSES)}; got {status!r}")
    if status == "online" and not target_url:
        raise RefsError("status online needs --target-url (the resolved full-text link)")
    data = load_refs(reg, slug)
    ref = next((r for r in data["refs"] if r.get("key") == key), None)
    if ref is None:
        raise RefsError(f"no ref with key {key} in {refs_path(reg, slug)}")
    ref["status"] = status
    for field, value in (("note", note), ("target_url", target_url), ("trove_url", trove_url),
                         ("call_number", call_number)):
        if value:
            ref[field] = value
    save_json(refs_path(reg, slug), data)


# --- status ---------------------------------------------------------------------------------------

def course_slugs(reg: Path) -> list[str]:
    slugs = set()
    for path in reg.glob("*.json"):
        if path.name == "term.json":
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("slug"):  # links.json and other non-course JSON carry no slug
            slugs.add(data["slug"])
    refs_dir = reg / "refs"
    if refs_dir.is_dir():
        slugs |= {p.stem for p in refs_dir.glob("*.json")}
    return sorted(slugs)


def status_report(reg: Path, slugs: list[str], *, require_refs: bool) -> tuple[list[str], bool]:
    lines, ok = [], True
    for slug in slugs:
        if not refs_path(reg, slug).is_file():
            # In --all mode a course with neither sources nor a refs file is not in scope.
            sources = reg / "sources" / slug
            has_sources = sources.is_dir() and any(sources.rglob("*"))
            if require_refs or has_sources:
                lines.append(f"{slug}: no refs file")
                ok = False
            continue
        refs = load_refs(reg, slug)["refs"]
        counts = Counter(ref.get("status", "") for ref in refs)
        known = sum(counts[s] for s in STATUSES)
        cells = "  ".join(f"{s} {counts[s]}" for s in STATUSES)
        lines.append(f"{slug:<12} total {len(refs):>3}  {cells}")
        if counts["pending"]:
            ok = False
        if known != len(refs):
            lines.append(f"{slug}: {len(refs) - known} ref(s) with an unknown status")
            ok = False
    return lines, ok


# --- chores ---------------------------------------------------------------------------------------

def existing_chores(reg: Path) -> set[tuple[Any, Any, Any]]:
    path = reg / "chores.json"
    if not path.is_file():
        return set()
    return {(c.get("course"), c.get("kind"), c.get("ref"))
            for c in json.loads(path.read_text(encoding="utf-8")) if isinstance(c, dict)}


def chore_plan(reg: Path, slug: str) -> list[dict[str, str]]:
    done = existing_chores(reg)
    plan = []
    for ref in load_refs(reg, slug)["refs"]:
        status = ref.get("status")
        if status not in CHORE_KIND:
            continue
        kind, ref_id = CHORE_KIND[status], f"refs:{slug}:{ref.get('key')}"
        if (slug, kind, ref_id) in done:
            continue
        citation = " ".join(str(ref.get("citation", "")).split())
        if status == "kotar":
            text = f"download from Kotar: {citation}"
        elif status == "print-only":
            text = f"print copy in the library; call number {ref.get('call_number', '')}: {citation}"
        else:
            text = f"not found in BIU Primo; find by hand: {citation}"
        plan.append({"kind": kind, "ref": ref_id, "title": citation[:80], "text": text})
    return plan


def apply_chores(reg: Path, slug: str, plan: list[dict[str, str]],
                 runner: Callable[..., Any] = subprocess.run) -> None:
    for item in plan:
        cmd = [sys.executable, str(COURSES_PY), "chores", "add", "--registry", str(reg), "--course", slug,
               "--kind", item["kind"], "--ref", item["ref"], "--title", item["title"], "--text", item["text"]]
        result = runner(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RefsError(f"chores add failed for {item['ref']}: {(result.stderr or '').strip()[:200]}")


# --- fetch chain ----------------------------------------------------------------------------------

def annas_search(citation: str, runner: Callable[..., Any] = subprocess.run) -> list[dict[str, Any]]:
    """Top Anna's Archive candidates via the global skill's CLI. Raises on any failure (DDoS-Guard, bad JSON)."""
    result = runner([sys.executable, str(ANNAS_SCRIPT), "search", primo_query(citation), "--json", "--limit", "3"],
                    capture_output=True, text=True, timeout=90)
    if result.returncode != 0:
        raise RefsError((result.stderr or "annas.py failed").strip()[:150])
    try:
        found = json.loads(result.stdout)
    except ValueError as exc:
        raise RefsError(f"annas.py gave no JSON: {exc}") from exc
    return [{k: item.get(k) for k in ("md5", "title", "author", "year", "format")} for item in found if isinstance(item, dict)]


def _stamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def fetch_ref(reg: Path, slug: str, key: str, *, task: str | None = None, dry_run: bool = False, hit: int | None = None,
              file: Path | None = None, env: dict[str, str] | None = None, lookup: Callable[..., list[dict[str, Any]]] | None = None,
              annas: Callable[[str], list[dict[str, Any]]] | None = None) -> dict[str, Any]:
    """Run the documented order for one ref: (0) Anna's Archive, (1) BIU lookup, (2) download/OCR, Kotar chore, or print-only.

    Every step is appended to `fetch_log` ({step, outcome, at}). `--dry-run` runs the read-only steps but writes nothing.
    A Primo reply with several hits is never auto-picked: pass --hit N (0-based) after reading the logged hits."""
    env = os.environ if env is None else env
    lookup = lookup or (lambda citation: propose(citation))
    annas = annas or annas_search
    data = load_refs(reg, slug)
    ref = next((r for r in data["refs"] if r.get("key") == key), None)
    if ref is None:
        raise RefsError(f"no ref with key {key} in {refs_path(reg, slug)}")
    citation = ref.get("citation", "")
    log: list[dict[str, str]] = []

    def step(name: str, outcome: str, detail: str | None = None) -> None:
        entry = {"step": name, "outcome": outcome, "at": _stamp()}
        if detail:
            entry["detail"] = detail
        log.append(entry)

    prior_annas, prior_candidates = ref.get("annas"), ref.get("annas_candidates")
    annas_ran = False

    def set_annas(value: str) -> None:
        keep = ("found-used", "found-wrong-edition") + (("not-found",) if value == "error" else ())
        if ref.get("annas") not in keep:
            ref["annas"] = value

    # step 0: Anna's Archive (never for Kotar; no key means not checked, and the chain goes on)
    if ref.get("status") == "kotar":
        step("annas", "skipped-kotar")
    elif not env.get("ANNAS_ARCHIVE_KEY"):
        step("annas", "not-checked", "ANNAS_ARCHIVE_KEY unset")
        if not ref.get("annas"):
            ref["annas"] = "not-checked"
    else:
        annas_ran = True
        try:
            candidates = annas(citation)
        except Exception as exc:  # DDoS-Guard, timeouts, bad JSON: record and continue
            step("annas", "error", str(exc)[:150])
            set_annas("error")
        else:
            if candidates:
                step("annas", "candidates", json.dumps(candidates, ensure_ascii=False)[:400])
                set_annas("candidates")
                ref["annas_candidates"] = candidates
            else:
                step("annas", "not-found")
                set_annas("not-found")

    # step 1: BIU library (Primo + CTO), only for a pending ref
    if ref.get("status") == "pending":
        try:
            hits = lookup(citation)
        except Exception as exc:
            hits = None
            step("lookup", "error", str(exc)[:150])
        if hits is not None:
            chosen = None
            if not hits:
                step("lookup", "no-hits")
            elif hit is not None:
                if not 0 <= hit < len(hits):
                    raise RefsError(f"--hit {hit} out of range (0-{len(hits) - 1})")
                chosen = hits[hit]
            elif len(hits) == 1:
                chosen = hits[0]
            else:
                brief = [{"i": i, "title": h.get("title"), "suggested": h.get("suggested_status")} for i, h in enumerate(hits)]
                step("lookup", "needs-choice", json.dumps(brief, ensure_ascii=False)[:400])
            if chosen is not None:
                status = chosen.get("suggested_status")
                if not status:
                    step("lookup", "undecided", chosen.get("title"))
                else:
                    target = next((s["target_url"] for s in chosen.get("services", []) if s.get("target_url")), "")
                    if status == "online" and not target:
                        step("lookup", "undecided", "online but no target url")
                    else:
                        ref["status"] = status
                        if status == "kotar" and annas_ran:  # never Anna's for Kotar: undo what step 0 just recorded
                            ref["annas"] = prior_annas or "not-checked"
                            ref.pop("annas_candidates", None)
                            if prior_candidates:
                                ref["annas_candidates"] = prior_candidates
                            step("annas", "discarded-kotar", "lookup classified the ref as Kotar")
                        if target and status == "online":
                            ref["target_url"] = target
                        if chosen.get("call_number"):
                            ref["call_number"] = chosen["call_number"]
                        step("lookup", status, chosen.get("title"))
    else:
        step("lookup", "skipped", f"status already {ref.get('status')}")

    # step 2: act on the status
    status = ref.get("status")
    if status in ("online", "downloaded"):
        found = None
        if file is not None:  # an explicitly supplied file always wins and must exist
            found = Path(file).expanduser()
            if not found.is_file():
                raise RefsError(f"--file {file} is not a file")
        recorded = Path(ref["download_path"]).expanduser() if ref.get("download_path") else None
        if found is None and recorded is not None and recorded.is_file():
            found = recorded
        if found is None:
            for candidate in (reg / "sources" / slug / f"{key}.pdf", Path.home() / "Downloads" / f"{key}.pdf"):
                if candidate.is_file():
                    found = candidate
                    break
        if found is None and recorded is not None:
            step("download", "missing-file", f"recorded path not found: {recorded}")
            status = None  # nothing downloaded: no success, no OCR queued
        if status is None:
            pass
        elif found is None and status == "online":
            step("download", "needs-browser-download", ref.get("target_url", "no target_url"))
        else:
            ref["status"] = "downloaded"
            if found is not None:
                ref["download_path"] = str(found)
            step("download", "downloaded", str(found) if found else "path not recorded")
            moved = found is not None and recorded is not None and found != recorded  # the queued OCR pointed at the old path
            if not ref.get("ocr") and (not ref.get("ocr_next") or moved):
                ref["ocr_next"] = {"state": "queued", "policy": list(OCR_POLICY),
                                   "note": "Gemini text first; Tesseract only as hidden check; empty Gemini => page blocked"}
                step("ocr", "queued", " > ".join(OCR_POLICY))
            else:
                step("ocr", "skipped", "ocr already recorded")
    elif status == "kotar":
        plan = {"kind": "kotar-source", "ref": f"refs:{slug}:{key}", "title": " ".join(citation.split())[:80],
                "text": f"run /academic-writer:kotar-fetch for: {' '.join(citation.split())}"}
        if dry_run:
            step("kotar", "chore-would-be-created", plan["ref"])
        else:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            import chores as chores_mod
            import courses
            chores_mod.add_chore(courses.Registry(reg), course=slug, kind=plan["kind"], ref=plan["ref"], title=plan["title"], text=plan["text"])
            step("kotar", "chore-created", plan["ref"])
    elif status == "print-only":
        step("print-only", "print-only", ref.get("call_number", ""))
    elif status == "not-found":
        step("final", "not-found", "find by hand (refs.py chores --apply adds the chore)")
    elif status == "ingested":
        step("final", "already-ingested")
    else:
        step("final", "pending", "no decision yet")

    if task and not dry_run:
        sys.path.insert(0, str(Path(__file__).resolve().parent))  # python -I leaves the script dir off sys.path
        import tasks as tasks_mod
        ident = tasks_mod.resolve_task(tasks_mod.sync_tasks(reg, slug, write=False), task)["id"]
        if ident not in ref.setdefault("tasks", []):
            ref["tasks"].append(ident)
    if not dry_run:
        ref.setdefault("fetch_log", []).extend(log)
        save_json(refs_path(reg, slug), data)
    return {"key": key, "status": ref.get("status"), "annas": ref.get("annas"), "dry_run": dry_run, "log": log}


# --- fetch queue (jobs written by the dashboard) --------------------------------------------------

MAX_ATTEMPTS = 3


def _job_error(result: dict[str, Any]) -> str | None:
    """A ref counts as errored when the chain could not run (exception) or the Primo lookup itself failed."""
    for entry in result.get("log", []):
        if entry.get("step") == "lookup" and entry.get("outcome") == "error":
            return f"lookup error: {entry.get('detail', '')}".strip()
    return None


def _ref_outcome(result: dict[str, Any]) -> str:
    steps = [e for e in result.get("log", []) if e.get("step") not in ("annas",)]
    return steps[-1]["outcome"] if steps else "none"


def drain_fetch_queue(reg: Path, *, dry_run: bool = False, env: dict[str, str] | None = None,
                      lookup: Callable[..., list[dict[str, Any]]] | None = None,
                      annas: Callable[[str], list[dict[str, Any]]] | None = None) -> dict[str, Any]:
    """Run `fetch_ref` for every ref of every job in queue/fetch/*.json, oldest first (file name = timestamp).

    A finished job moves to queue/fetch/done/ with per-ref `results`. A job whose refs all errored stays with an
    `attempts` counter and is retried next run; after MAX_ATTEMPTS it moves to done with status "failed".
    Refs that already finished in an earlier attempt are not run again. A lock file keeps two drains apart."""
    folder = reg / "queue" / "fetch"
    report: dict[str, Any] = {"jobs": [], "dry_run": dry_run}
    if not folder.is_dir():
        return report
    lock = (folder / ".drain.lock").open("a+")
    fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
    try:
        for path in sorted(folder.glob("*.json")):
            try:
                job = json.loads(path.read_text(encoding="utf-8"))
            except ValueError:
                report["jobs"].append({"job": path.name, "status": "unreadable"})
                continue
            if not isinstance(job, dict) or not job.get("course") or not isinstance(job.get("refs"), list):
                report["jobs"].append({"job": path.name, "status": "invalid"})
                continue
            results: dict[str, Any] = dict(job.get("results") or {})
            for key in job["refs"]:
                key = str(key)
                if results.get(key, {}).get("state") == "ok":
                    continue
                try:
                    res = fetch_ref(reg, job["course"], key, task=job.get("task"), dry_run=dry_run, env=env, lookup=lookup, annas=annas)
                except Exception as exc:  # unknown course/ref, bad refs file: record, never abort the queue
                    results[key] = {"state": "error", "detail": str(exc)[:200]}
                    continue
                err = _job_error(res)
                results[key] = ({"state": "error", "detail": err} if err else
                                {"state": "ok", "outcome": _ref_outcome(res), "status": res.get("status"), "annas": res.get("annas")})
            errored = [k for k, v in results.items() if v.get("state") == "error"]
            all_errored = bool(job["refs"]) and len(errored) == len(job["refs"])
            entry: dict[str, Any] = {"job": path.name, "course": job["course"], "results": results}
            if all_errored:
                attempts = int(job.get("attempts") or 0) + 1
                entry["attempts"] = attempts
                entry["status"] = "failed" if attempts >= MAX_ATTEMPTS else "retry"
            else:
                entry["status"] = "done"
            report["jobs"].append(entry)
            if dry_run:
                continue
            job.update({"results": results, "status": entry["status"], "processed_at": _stamp()})
            if "attempts" in entry:
                job["attempts"] = entry["attempts"]
            if entry["status"] == "retry":
                job["status"] = "pending"
                save_json(path, job)
            else:
                save_json(folder / "done" / path.name, job)
                path.unlink()
    finally:
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        lock.close()
    return report


# --- index ----------------------------------------------------------------------------------------

def render_index(slug: str, data: dict[str, Any]) -> str:
    lines = [f"# מקורות נזכרים: {data.get('course', slug)}", "",
             "> Load this page when: a lesson or assignment cites one of these sources and you need its status or where it is.",
             ""]
    for ref in data["refs"]:
        citation = " ".join(str(ref.get("citation", "")).split())
        line = f"- {citation} — role: {ref.get('role', '')}; status: {ref.get('status', '')}; cited in: {ref.get('found_in', '')}"
        if ref.get("status") == "ingested":
            line += f" — [Trove]({ref['trove_url']})" if ref.get("trove_url") else " — Trove page not recorded"
        lines.append(line)
    return "\n".join(lines) + "\n"


# --- CLI ------------------------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="refs.py", description="Course references: extract, Primo lookup, status, chores, index.")
    parser.add_argument("--registry", type=Path, help="term directory (default: ACADEMIC_COURSES_DIR/<term>)")
    parser.add_argument("--term", help="term directory name (default: ACADEMIC_TERM, or the sole term)")
    sub = parser.add_subparsers(dest="command", required=True)

    ext = sub.add_parser("extract", help="list citation candidates from a course's sources and transcripts")
    ext.add_argument("slug")
    ext.add_argument("--write", action="store_true", help="append new candidates as pending refs (confirm first)")
    ext.add_argument("--only", action="append", metavar="KEY", help="with --write: only these candidate keys (repeatable)")
    ext.add_argument("--json", action="store_true")

    lk = sub.add_parser("lookup", help="propose Primo hits for pending refs, or record a decision with --set")
    lk.add_argument("slug")
    lk.add_argument("--key", help="only this pending ref")
    lk.add_argument("--query", help="Primo search text to use instead of the one built from the citation")
    lk.add_argument("--set", dest="set_key", metavar="KEY", help="record the decision for this ref key")
    lk.add_argument("--status", choices=STATUSES)
    lk.add_argument("--note")
    lk.add_argument("--target-url")
    lk.add_argument("--trove-url")
    lk.add_argument("--call-number")

    st = sub.add_parser("status", help="counts per status; exit 0 only when nothing is pending")
    st.add_argument("slug", nargs="?")
    st.add_argument("--all", action="store_true")

    ch = sub.add_parser("chores", help="one chore per kotar, print-only and not-found ref")
    ch.add_argument("slug")
    ch.add_argument("--apply", action="store_true", help="add them with courses.py chores add")

    fe = sub.add_parser("fetch", help="run the fetch chain for one ref: Anna's Archive, BIU lookup, download/OCR, Kotar chore")
    fe.add_argument("--course", required=True)
    fe.add_argument("--ref", required=True, help="ref key")
    fe.add_argument("--task", help="also link the ref to this task")
    fe.add_argument("--hit", type=int, help="0-based Primo hit to take when several come back")
    fe.add_argument("--file", type=Path, help="a PDF already downloaded for this ref")
    fe.add_argument("--dry-run", action="store_true", help="run read-only steps, write nothing")

    fq = sub.add_parser("fetch-queue", help="run the fetch chain for every job the dashboard queued (queue/fetch/*.json), oldest first")
    fq.add_argument("--dry-run", action="store_true", help="run read-only steps, move nothing")
    fq.add_argument("--json", action="store_true")

    sys.path.insert(0, str(Path(__file__).resolve().parent))  # python -I leaves the script dir off sys.path
    import tasks as tasks_mod
    tasks_mod.add_task_parser(sub)

    ix = sub.add_parser("index", help="render the מקורות נזכרים page as markdown")
    ix.add_argument("slug")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return _dispatch(args)
    except RefsError as exc:
        print(f"refs: {exc}", file=sys.stderr)
        return 2


def _dispatch(args: argparse.Namespace) -> int:
    reg = registry_dir(args.registry, args.term)

    if args.command == "extract":
        candidates, report = extract(reg, args.slug)
        if args.json:
            print(json.dumps({"candidates": candidates, "report": report}, ensure_ascii=False, indent=2))
        else:
            print("\n".join(report))
            for item in candidates:
                print(f"{item['key']}\t{item['found_in']}\t{item['citation']}")
        if args.write:
            added = write_candidates(reg, args.slug, candidates, only=args.only)
            print(f"wrote {added} new pending ref(s) to {refs_path(reg, args.slug)}")
        else:
            print("not written: re-run with --write after confirming the candidates")
        return 0

    if args.command == "lookup":
        if args.set_key:
            if not args.status:
                raise RefsError("--set needs --status")
            record_decision(reg, args.slug, args.set_key, args.status, note=args.note, target_url=args.target_url,
                            trove_url=args.trove_url, call_number=args.call_number)
            print(f"recorded {args.set_key}: {args.status}")
            return 0
        print(json.dumps(lookup_pending(reg, args.slug, args.key, query=args.query), ensure_ascii=False, indent=2))
        return 0

    if args.command == "status":
        if args.all or args.slug is None:
            slugs = course_slugs(reg)
            if not slugs:
                raise RefsError(f"no courses in {reg}")
            lines, ok = status_report(reg, slugs, require_refs=False)
        else:
            lines, ok = status_report(reg, [args.slug], require_refs=True)
        print("\n".join(lines))
        return 0 if ok else 1

    if args.command == "chores":
        plan = chore_plan(reg, args.slug)
        for item in plan:
            print(f"{item['kind']}\t{item['ref']}\t{item['text']}")
        if not plan:
            print("no chores to add")
        elif args.apply:
            apply_chores(reg, args.slug, plan)
            print(f"added {len(plan)} chore(s)")
        else:
            print("not added: re-run with --apply")
        return 0

    if args.command == "fetch":
        print(json.dumps(fetch_ref(reg, args.course, args.ref, task=args.task, dry_run=args.dry_run, hit=args.hit, file=args.file),
                         ensure_ascii=False, indent=2))
        return 0

    if args.command == "fetch-queue":
        report = drain_fetch_queue(reg, dry_run=args.dry_run)
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            for j in report["jobs"]:
                print(f"{j['job']}\t{j.get('status')}\t{len(j.get('results', {}))} ref(s)")
            if not report["jobs"]:
                print("fetch queue empty")
        failed = [j for j in report["jobs"] if j.get("status") in ("retry", "failed", "invalid", "unreadable")]
        return 1 if failed else 0

    if args.command == "task":
        sys.path.insert(0, str(Path(__file__).resolve().parent))  # python -I leaves the script dir off sys.path
        import tasks as tasks_mod
        return tasks_mod.run_task_command(reg, args)

    if args.command == "index":
        print(render_index(args.slug, load_refs(reg, args.slug)), end="")
        return 0

    raise RefsError(f"unknown command {args.command}")


if __name__ == "__main__":
    sys.exit(main())
