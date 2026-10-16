#!/usr/bin/env python3
"""Fetch cited pages of a Kotar (CET) book as one PDF, for the reader's own study.

Kotar's viewer serves page images by a per-page token. The tokens can only be
read from a signed-in viewer tab, so that one step runs in the browser; this
script prints the snippet for it and does everything else:

  tokens-js <book_id> <start_idx> <end_idx>   print the javascript_tool snippet
  fetch <out_dir> --tokens-file F --start-idx I --first-page N [--step S] [--last-page B]
                                              download one JPEG per token (iNNNN.jpg)
  peek <out_dir> [IDX ...]                    one strip image of page headers and footers
  check <out_dir> --seen IDX:PRINTED|plate ... [--plate IDX ...]
                                              verify the first AND last image of every batch
  merge <out_dir> <out.pdf>                   merge in index order (only after check passes)
  offset <index> <printed>                    index - printed page (+ index range)

Indices (nPageStart/nPageEnd) are Kotar's internal page indices, not printed
page numbers, and plates can shift the mapping anywhere in a range. So the
mapping is never assumed: every batch's first and last image must be read and
match the expected printed number before merge will run. Files are named by
index, so book order is kept even across unnumbered plates. Pure Python plus
subprocess curl; PIL only for peek and merge.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

VIEWER_ORIGIN = "https://kotar-cet-ac-il.eu1.proxy.openathens.net"
IMAGE_URL = ("https://kotarimagesstg.cet.ac.il/GetPageImg_v2.ashx"
             "?Type=page_img&gPageToken={token}&nStep=9&nVersion=10")
MAX_PAGES_PER_REQUEST = 10   # Kotar's own print limit
MIN_PAGE_BYTES = 20_000      # nStep >= 10 and failures return a ~6 KB placeholder
PAGE_NAME = re.compile(r"^i(\d{4})\.jpg$")
MANIFEST = "manifest.json"
# A uuid whose groups are separated by dashes or by whitespace (the browser
# tool blocks output that looks like URL query data, so the snippet returns
# the tokens with dashes replaced by spaces).
TOKEN = re.compile(
    r"\b([0-9a-fA-F]{8})[\s-]+([0-9a-fA-F]{4})[\s-]+([0-9a-fA-F]{4})"
    r"[\s-]+([0-9a-fA-F]{4})[\s-]+([0-9a-fA-F]{12})\b")


def batches(start: int, end: int, size: int = MAX_PAGES_PER_REQUEST) -> list[tuple[int, int]]:
    if end < start:
        raise ValueError(f"end index {end} is before start index {start}")
    return [(s, min(s + size - 1, end)) for s in range(start, end + 1, size)]


def tokens_js(book_id: str, start: int, end: int) -> str:
    """The snippet to run with javascript_tool in the signed-in viewer tab."""
    if not str(book_id).isdigit():
        raise ValueError(f"book id must be numeric, got {book_id!r}")
    ranges = json.dumps(batches(start, end))
    return (
        # javascript_tool returns {} for a bare promise; top-level await resolves it.
        "await (async () => {\n"
        f"  const ranges = {ranges};\n"
        "  const out = [];\n"
        "  for (const [s, e] of ranges) {\n"
        "    const r = await fetch(location.origin + '/KotarApp/Viewer/Popups/PrintPages.aspx'"
        f" + '?nBookID={book_id}&nPageStart=' + s + '&nPageEnd=' + e, {{credentials: 'include'}});\n"
        "    const html = await r.text();\n"
        "    const doc = new DOMParser().parseFromString(html, 'text/html');\n"
        "    for (const img of doc.querySelectorAll('img')) {\n"
        "      const m = (img.getAttribute('src') || '').match(/gPageToken=([0-9a-fA-F-]{36})/);\n"
        "      if (m) out.push(m[1].replace(/-/g, ' '));\n"
        "    }\n"
        "  }\n"
        "  return out.length + ' tokens\\n' + out.join('\\n');\n"
        "})()"
    )


def parse_tokens(text: str) -> list[str]:
    """Dashed uuids in order of appearance, duplicates dropped."""
    seen: dict[str, None] = {}
    for m in TOKEN.finditer(text):
        seen.setdefault("-".join(m.groups()).lower(), None)
    return list(seen)


def page_name(idx: int) -> str:
    return f"i{idx:04d}.jpg"


def is_real_page(data: bytes) -> bool:
    return len(data) > MIN_PAGE_BYTES and data[:3] == b"\xff\xd8\xff"


def curl(url: str) -> bytes:
    proc = subprocess.run(["curl", "-sL", "--max-time", "60", "-A", "Mozilla/5.0", url],
                          capture_output=True, check=False)
    return proc.stdout if proc.returncode == 0 else b""


def load_manifest(out_dir: Path) -> dict:
    path = out_dir / MANIFEST
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"segments": [], "pages": {}, "failed": [], "plates": [], "seen": {}, "verified": False}


def save_manifest(out_dir: Path, manifest: dict) -> None:
    (out_dir / MANIFEST).write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def fetch(out_dir: Path, tokens: list[str], start_idx: int, first_page: int, step: int = 1,
          last_page: int | None = None, getter=curl, retries: int = 1) -> dict:
    """Download one JPEG per token; token i is Kotar index start_idx + i.

    Each call adds a segment (start index, the printed page expected there, and
    the step: 2 for a two-column encyclopedia page numbered by its first column).
    A new fetch always clears the verified flag.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest(out_dir)
    for i, token in enumerate(tokens):
        idx = start_idx + i
        data = b""
        for _ in range(retries + 1):
            data = getter(IMAGE_URL.format(token=token))
            if is_real_page(data):
                break
        manifest["failed"] = [f for f in manifest["failed"] if f["idx"] != idx]
        if is_real_page(data):
            (out_dir / page_name(idx)).write_bytes(data)
            manifest["pages"][str(idx)] = {"file": page_name(idx), "bytes": len(data)}
        else:
            manifest["failed"].append({"idx": idx, "token": token, "bytes": len(data)})
    end_idx = start_idx + len(tokens) - 1
    manifest["segments"].append({
        "start_idx": start_idx, "end_idx": end_idx, "first_page": first_page, "step": step,
        "last_page": last_page, "batches": batches(start_idx, end_idx) if tokens else []})
    manifest["verified"] = False
    save_manifest(out_dir, manifest)
    return manifest


def segment_for(manifest: dict, idx: int) -> dict | None:
    """The latest segment covering idx (a re-fetch overrides an earlier one)."""
    for seg in reversed(manifest["segments"]):
        if seg["start_idx"] <= idx <= seg["end_idx"]:
            return seg
    return None


def expected_printed(manifest: dict, idx: int) -> int | str:
    """The printed number idx should carry, counting declared plates before it."""
    if idx in manifest["plates"]:
        return "plate"
    seg = segment_for(manifest, idx)
    if seg is None:
        raise KeyError(idx)
    plates_before = sum(1 for p in manifest["plates"] if seg["start_idx"] <= p < idx)
    return seg["first_page"] + (idx - seg["start_idx"] - plates_before) * seg["step"]


def parse_seen(items: list[str]) -> dict[str, int | str]:
    out: dict[str, int | str] = {}
    for item in items:
        idx, _, value = item.partition(":")
        value = value.strip().lower()
        if not idx.strip().isdigit() or not (value.isdigit() or value == "plate"):
            raise ValueError(f"--seen wants IDX:PRINTED or IDX:plate, got {item!r}")
        out[str(int(idx))] = int(value) if value.isdigit() else "plate"
    return out


def check(out_dir: Path, seen: dict[str, int | str] | None = None, plates: list[int] | None = None) -> dict:
    """Verify the first and last image of every batch against the expected printed number.

    A batch passes only when both ends were read (--seen) and match. Any
    mismatch means plates or a numbering jump moved the mapping: re-probe that
    batch (peek its images), declare plates with --plate, or re-fetch the rest as
    a new segment from the right start index. Never guessed: unread ends fail.
    """
    manifest = load_manifest(out_dir)
    manifest["seen"].update(seen or {})
    # Plates are only ever declared explicitly, after a re-probe: seeing a plate
    # where a number was expected is a mismatch, not a silent correction.
    manifest["plates"] = sorted(set(manifest["plates"]) | set(plates or []))
    problems = []
    for seg in manifest["segments"]:
        for s, e in seg["batches"]:
            for idx in sorted({s, e}):
                if segment_for(manifest, idx) is not seg:
                    continue  # superseded by a later segment
                want = expected_printed(manifest, idx)
                got = manifest["seen"].get(str(idx))
                if got is None:
                    problems.append({"idx": idx, "batch": [s, e], "expected": want, "seen": None,
                                     "fix": f"read the printed number on {page_name(idx)} and pass --seen {idx}:<n|plate>"})
                elif got != want:
                    problems.append({"idx": idx, "batch": [s, e], "expected": want, "seen": got,
                                     "fix": f"the mapping moved inside batch {s}-{e}: re-probe its images (peek), "
                                            "declare plates with --plate, or re-fetch from the first wrong index "
                                            "as a new segment with its real printed page"})
    short = []
    wants = [seg["last_page"] for seg in manifest["segments"] if seg.get("last_page") is not None]
    if wants:
        covered = [n for seg in manifest["segments"] for i in range(seg["start_idx"], seg["end_idx"] + 1)
                   if segment_for(manifest, i) is seg and isinstance(n := expected_printed(manifest, i), int)]
        covers_to = max(covered, default=None)
        if covers_to is None or covers_to < max(wants):
            short.append({"covers_to": covers_to, "wants": max(wants),
                          "fix": "plates used up indices: fetch the next indices as another segment"})
    for f in manifest["failed"]:
        problems.append({"idx": f["idx"], "fetch_failed": True, "fix": "re-run tokens-js and fetch for this index"})
    manifest["verified"] = not problems and not short and bool(manifest["segments"])
    save_manifest(out_dir, manifest)
    return {"verified": manifest["verified"], "problems": problems, "short": short,
            "plates": manifest["plates"]}


def ordered_pages(out_dir: Path) -> list[Path]:
    found = [(int(m.group(1)), p) for p in out_dir.iterdir() if (m := PAGE_NAME.match(p.name))]
    return [p for _, p in sorted(found)]


def peek(out_dir: Path, idxs: list[int] | None = None, out: Path | None = None) -> Path:
    """Stack the header and footer strips of the given images (default: every batch's ends)."""
    from PIL import Image

    manifest = load_manifest(out_dir)
    if not idxs:
        idxs = sorted({i for seg in manifest["segments"] for s, e in seg["batches"] for i in (s, e)})
    strips = []
    for idx in idxs:
        f = out_dir / page_name(idx)
        if not f.exists():
            continue
        im = Image.open(f).convert("RGB")
        w, h = im.size
        for box in ((0, 0, w, int(h * 0.08)), (0, int(h * 0.90), w, h)):
            strips.append(im.crop(box).resize((max(1, w // 2), max(1, (box[3] - box[1]) // 2))))
    if not strips:
        raise SystemExit(f"no images to peek in {out_dir}")
    sheet = Image.new("RGB", (max(s.size[0] for s in strips), sum(s.size[1] for s in strips)), "white")
    y = 0
    for s in strips:
        sheet.paste(s, (0, y))
        y += s.size[1]
    out = out or out_dir / "peek.png"
    sheet.save(out)
    return out


def merge(out_dir: Path, out_pdf: Path) -> int:
    from PIL import Image

    if not load_manifest(out_dir).get("verified"):
        raise SystemExit(f"{out_dir} is not verified: run check with every batch's first and last page read")
    files = ordered_pages(out_dir)
    if not files:
        raise SystemExit(f"no iNNNN.jpg pages in {out_dir}")
    images = [Image.open(f).convert("RGB") for f in files]
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    images[0].save(out_pdf, "PDF", save_all=True, append_images=images[1:], resolution=150)
    return len(images)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("tokens-js", help="print the javascript_tool snippet")
    t.add_argument("book_id")
    t.add_argument("start_idx", type=int)
    t.add_argument("end_idx", type=int)
    f = sub.add_parser("fetch", help="download one JPEG per token, with the size check")
    f.add_argument("out_dir", type=Path)
    f.add_argument("--tokens-file", type=Path, required=True)
    f.add_argument("--start-idx", type=int, required=True, help="Kotar index of the first token")
    f.add_argument("--first-page", type=int, required=True, help="printed page expected at --start-idx")
    f.add_argument("--step", type=int, default=1, help="printed numbers per image (2 for two-column pages)")
    f.add_argument("--last-page", type=int, help="last printed page wanted, to detect a short range")
    p = sub.add_parser("peek", help="strip image of headers and footers to read printed numbers")
    p.add_argument("out_dir", type=Path)
    p.add_argument("idxs", type=int, nargs="*")
    c = sub.add_parser("check", help="verify the first and last image of every batch")
    c.add_argument("out_dir", type=Path)
    c.add_argument("--seen", action="append", default=[], help="IDX:PRINTED or IDX:plate, as read on the image")
    c.add_argument("--plate", action="append", type=int, default=[], help="index of an unnumbered plate")
    m = sub.add_parser("merge", help="merge iNNNN.jpg in index order into one PDF (after check)")
    m.add_argument("out_dir", type=Path)
    m.add_argument("out_pdf", type=Path)
    o = sub.add_parser("offset", help="offset = index - printed page")
    o.add_argument("index", type=int)
    o.add_argument("printed", type=int)
    o.add_argument("--pages", help="printed range A-B to convert to an index range")
    args = ap.parse_args(argv)

    if args.cmd == "tokens-js":
        print(tokens_js(args.book_id, args.start_idx, args.end_idx))
    elif args.cmd == "fetch":
        tokens = parse_tokens(args.tokens_file.read_text(encoding="utf-8"))
        if not tokens:
            print("no tokens found in the tokens file", file=sys.stderr)
            return 2
        result = fetch(args.out_dir, tokens, args.start_idx, args.first_page, args.step, args.last_page)
        seg = result["segments"][-1]
        failed = [x for x in result["failed"] if seg["start_idx"] <= x["idx"] <= seg["end_idx"]]
        print(json.dumps({"ok": len(tokens) - len(failed), "failed": failed, "batches": seg["batches"],
                          "next": "peek, then check --seen for the first and last index of every batch"}))
        return 1 if failed else 0
    elif args.cmd == "peek":
        print(peek(args.out_dir, args.idxs))
    elif args.cmd == "check":
        result = check(args.out_dir, parse_seen(args.seen), args.plate)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["verified"] else 1
    elif args.cmd == "merge":
        print(f"{merge(args.out_dir, args.out_pdf)} pages -> {args.out_pdf}")
    elif args.cmd == "offset":
        off = args.index - args.printed
        line = {"offset": off}
        if args.pages:
            a, b = (int(x) for x in re.split(r"[-–]", args.pages))
            line.update(start_idx=a + off, end_idx=b + off)
        print(json.dumps(line))
    return 0


if __name__ == "__main__":
    sys.exit(main())
