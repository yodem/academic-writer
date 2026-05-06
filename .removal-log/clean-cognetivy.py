#!/usr/bin/env python3
"""Remove cognetivy references from a markdown/JSON file. Logs every change."""
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


def log(log_file: Path, action: str, **kwargs):
    entry = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "action": action,
        **kwargs,
    }
    with log_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


COGNETIVY_RE = re.compile(r"cognetivy", re.IGNORECASE)


def clean_markdown(text: str) -> tuple[str, dict]:
    """Strip cognetivy references from markdown. Returns (cleaned, stats)."""
    lines = text.splitlines(keepends=False)
    out: list[str] = []
    stats = {"lines_removed": 0, "sections_removed": 0, "empty_blocks_removed": 0}

    i = 0
    while i < len(lines):
        line = lines[i]

        # Skip H2/H3 sections whose heading mentions cognetivy
        m = re.match(r"^(#{2,4})\s+.*[Cc]ognetivy", line)
        if m:
            level = len(m.group(1))
            stats["sections_removed"] += 1
            i += 1
            # Skip until next heading at same or shallower level, or end
            while i < len(lines):
                nm = re.match(r"^(#{1,6})\s", lines[i])
                if nm and len(nm.group(1)) <= level:
                    break
                stats["lines_removed"] += 1
                i += 1
            continue

        # Drop any single line that mentions cognetivy
        if COGNETIVY_RE.search(line):
            stats["lines_removed"] += 1
            # Special: clean .cognetivy paths from mkdir/path lists rather than dropping whole line
            cleaned_inline = re.sub(r"\s*\.cognetivy\S*", "", line)
            cleaned_inline = COGNETIVY_RE.sub("", cleaned_inline)
            cleaned_inline = re.sub(r"\s+$", "", cleaned_inline)
            # If line was a list/path with multiple tokens, keep the rest
            stripped_orig = line.strip()
            if (
                stripped_orig.startswith(("mkdir ", "rm ", "cp ", "ls "))
                or "mkdir -p" in stripped_orig
            ):
                if cleaned_inline.strip() and not COGNETIVY_RE.search(cleaned_inline):
                    out.append(cleaned_inline)
                    stats["lines_removed"] -= 1
                i += 1
                continue
            i += 1
            continue

        out.append(line)
        i += 1

    # Collapse empty bash/json code fences left behind
    cleaned: list[str] = []
    j = 0
    while j < len(out):
        if out[j].strip().startswith("```") and j + 1 < len(out):
            # find matching close
            close = j + 1
            inner: list[str] = []
            while close < len(out) and not out[close].strip().startswith("```"):
                inner.append(out[close])
                close += 1
            if close < len(out) and not any(s.strip() for s in inner):
                # Empty code block — skip the whole thing including fences
                stats["empty_blocks_removed"] += 1
                j = close + 1
                continue
        cleaned.append(out[j])
        j += 1

    # Collapse 3+ blank lines to max 2
    final: list[str] = []
    blank_run = 0
    for ln in cleaned:
        if ln.strip() == "":
            blank_run += 1
            if blank_run <= 2:
                final.append(ln)
        else:
            blank_run = 0
            final.append(ln)

    return "\n".join(final) + ("\n" if text.endswith("\n") else ""), stats


def clean_json(text: str) -> tuple[str, dict]:
    """Remove cognetivy entries from JSON. Returns (cleaned, stats)."""
    stats = {"keys_removed": 0}
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return text, stats

    def walk(obj):
        if isinstance(obj, dict):
            for k in list(obj.keys()):
                if "cognetivy" in k.lower():
                    obj.pop(k)
                    stats["keys_removed"] += 1
                    continue
                walk(obj[k])
        elif isinstance(obj, list):
            new = []
            for item in obj:
                if isinstance(item, str) and "cognetivy" in item.lower():
                    stats["keys_removed"] += 1
                    continue
                walk(item)
                new.append(item)
            obj.clear()
            obj.extend(new)

    walk(data)
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n", stats


def main():
    log_file = Path(sys.argv[1])
    targets = sys.argv[2:]

    for path_str in targets:
        path = Path(path_str)
        if not path.exists():
            log(log_file, "skip_missing", path=str(path))
            continue
        original = path.read_text(encoding="utf-8")
        if not COGNETIVY_RE.search(original) and ".cognetivy" not in original:
            log(log_file, "no_change", path=str(path))
            continue

        if path.suffix == ".json":
            cleaned, stats = clean_json(original)
        else:
            cleaned, stats = clean_markdown(original)

        if cleaned == original:
            log(log_file, "no_change_after_clean", path=str(path))
            continue

        path.write_text(cleaned, encoding="utf-8")
        log(
            log_file,
            "cleaned",
            path=str(path),
            bytes_before=len(original),
            bytes_after=len(cleaned),
            **stats,
        )


if __name__ == "__main__":
    main()
