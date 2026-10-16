#!/usr/bin/env python3
"""Fetch cited pages of a Kotar (CET) book as one PDF, for the reader's own study.

Kotar's viewer serves page images by a per-page token. The tokens can only be
read from a signed-in viewer tab, so that one step runs in the browser; this
script prints the snippet for it and does everything else:

  tokens-js <book_id> <start_idx> <end_idx>   print the javascript_tool snippet
  fetch <out_dir> --tokens-file F --first-page N
                                              download one JPEG per token
  merge <out_dir> <out.pdf>                   merge the JPEGs in printed-page order
  offset <index> <printed>                    index - printed page (+ index range)

Indices (nPageStart/nPageEnd) are Kotar's internal page indices, not printed
page numbers. Pure Python plus subprocess curl; PIL only for merge.
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
PAGE_NAME = re.compile(r"^p(\d{4})\.jpg$")
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
        "(async () => {\n"
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


def page_name(printed: int) -> str:
    return f"p{printed:04d}.jpg"


def is_real_page(data: bytes) -> bool:
    return len(data) > MIN_PAGE_BYTES and data[:3] == b"\xff\xd8\xff"


def curl(url: str) -> bytes:
    proc = subprocess.run(["curl", "-sL", "--max-time", "60", "-A", "Mozilla/5.0", url],
                          capture_output=True, check=False)
    return proc.stdout if proc.returncode == 0 else b""


def fetch(out_dir: Path, tokens: list[str], first_page: int, getter=curl, retries: int = 1) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    pages, failed = [], []
    for i, token in enumerate(tokens):
        printed = first_page + i
        data = b""
        for _ in range(retries + 1):
            data = getter(IMAGE_URL.format(token=token))
            if is_real_page(data):
                break
        name = page_name(printed)
        if is_real_page(data):
            (out_dir / name).write_bytes(data)
            pages.append({"page": printed, "file": name, "bytes": len(data)})
        else:
            failed.append({"page": printed, "token": token, "bytes": len(data)})
    manifest = {"first_page": first_page, "pages": pages, "failed": failed}
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def ordered_pages(out_dir: Path) -> list[Path]:
    found = [(int(m.group(1)), p) for p in out_dir.iterdir() if (m := PAGE_NAME.match(p.name))]
    return [p for _, p in sorted(found)]


def merge(out_dir: Path, out_pdf: Path) -> int:
    from PIL import Image

    files = ordered_pages(out_dir)
    if not files:
        raise SystemExit(f"no pNNNN.jpg pages in {out_dir}")
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
    f.add_argument("--first-page", type=int, required=True, help="printed page of the first token")
    m = sub.add_parser("merge", help="merge pNNNN.jpg in printed-page order into one PDF")
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
        result = fetch(args.out_dir, tokens, args.first_page)
        print(json.dumps({"ok": len(result["pages"]), "failed": result["failed"],
                          "first": result["pages"][0]["page"] if result["pages"] else None,
                          "last": result["pages"][-1]["page"] if result["pages"] else None}))
        return 1 if result["failed"] else 0
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
