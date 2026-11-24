#!/usr/bin/env python3
"""docs-fresh.py [--advisory] [repo]: check a repo's docs/ folder against the drive docs convention.

Stdlib only, Python 3.9. Never writes files. Exit 0 no errors, 1 errors, 2 invalid.
Two roles: CI runs it as a gate (exit 1 on errors); /drive runs it with --advisory, which prints the same lines but
exits 0 on errors (exit 2 on invalid input stays).
"""
import os
import re
import subprocess
import sys

CORE = {"README.md": 30, "product.md": 60, "architecture.md": 120}
OPTIONAL_CAP = {"ux.md": 60, "glossary.md": 60, "runbook.md": 60}
ADR_CAP = 40
BUDGET = 400
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def inside(repo, rel):
    """True when `rel` resolves to a path under the repo root (no absolute path, no .. escape, no symlink escape)."""
    root = os.path.realpath(repo)
    full = os.path.realpath(os.path.join(root, rel))
    return not os.path.isabs(rel) and (full == root or full.startswith(root + os.sep))


def line_count(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return sum(1 for _ in f)


def front_matter(path):
    """Return dict of key -> str or list from a leading --- block."""
    with open(path, encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()
    fm = {}
    if not lines or lines[0].strip() != "---":
        return fm
    key = None
    for ln in lines[1:]:
        if ln.strip() == "---":
            break
        m = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", ln)
        if m:
            key = m.group(1)
            val = m.group(2).strip().strip("'\"")
            fm[key] = val if val else []
        elif key is not None and re.match(r"^\s*-\s+", ln):
            item = re.sub(r"^\s*-\s+", "", ln).strip().strip("'\"")
            if not isinstance(fm.get(key), list):
                fm[key] = []
            fm[key].append(item)
    return fm


def git_changed(repo, since, path):
    """True when `path` has a commit after the end of day `since` (a commit on the review day itself is covered)."""
    r = subprocess.run(
        ["git", "-C", repo, "-c", "core.fsmonitor=false", "log", "--since=" + since + " 23:59:59", "--format=%H", "--", path],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    return r.returncode == 0 and r.stdout.strip() != ""


def md_files(root, skip_dirs):
    out = []
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if os.path.join(dp, d) not in skip_dirs]
        for fn in sorted(fns):
            if fn.endswith(".md"):
                out.append(os.path.join(dp, fn))
    return sorted(out)


def main(argv):
    args = [a for a in argv[1:] if a != "--advisory"]
    advisory = len(args) != len(argv) - 1
    repo = args[0] if args else "."
    if not os.path.isdir(repo):
        print("docs-fresh: invalid: not a directory: %s" % repo)
        return 2
    try:
        subprocess.run(["git", "--version"], stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, check=True)
    except (OSError, subprocess.CalledProcessError):
        print("docs-fresh: invalid: git unavailable")
        return 2

    errors, warnings = [], []
    docs = os.path.join(repo, "docs")

    for name in CORE:
        if not os.path.isfile(os.path.join(docs, name)):
            errors.append("MISSING docs/%s" % name)

    if os.path.isdir(docs):
        plans = os.path.join(docs, "plans")
        adr = os.path.join(docs, "adr")
        budget_total = 0
        for path in md_files(docs, {plans}):
            rel = os.path.relpath(path, docs)
            n = line_count(path)
            in_adr = rel.startswith("adr" + os.sep)
            if not in_adr:
                budget_total += n
            top = rel
            if rel in CORE:
                if n > CORE[rel]:
                    errors.append("OVER-CAP docs/%s %d/%d" % (rel, n, CORE[rel]))
            elif rel in OPTIONAL_CAP:
                if n > OPTIONAL_CAP[rel]:
                    warnings.append("OVER-CAP docs/%s %d/%d (warning)" % (rel, n, OPTIONAL_CAP[rel]))
            elif in_adr and n > ADR_CAP * 2:
                warnings.append("OVER-CAP docs/%s %d/%d (warning)" % (rel, n, ADR_CAP * 2))
            del top

            fm = front_matter(path)
            covers = fm.get("covers")
            covers = covers if isinstance(covers, list) else []
            reviewed = fm.get("last-reviewed")
            reviewed = reviewed if isinstance(reviewed, str) and reviewed else None
            if reviewed and not DATE_RE.match(reviewed):
                warnings.append("BAD-DATE docs/%s: last-reviewed %r is not YYYY-MM-DD (warning)" % (rel, reviewed))
                reviewed = None
            if covers and not reviewed:
                warnings.append("NO-DATE docs/%s: covers set but no last-reviewed (warning)" % rel)
            for c in covers:
                if not inside(repo, c):
                    warnings.append("BAD-COVERS docs/%s: %s is outside the repo (warning)" % (rel, c))
                elif not os.path.exists(os.path.join(repo, c)):
                    warnings.append("GONE docs/%s: covers %s (warning)" % (rel, c))
                elif reviewed and git_changed(repo, reviewed, c):
                    warnings.append("STALE docs/%s: %s changed since %s (warning)" % (rel, c, reviewed))

            with open(path, encoding="utf-8", errors="replace") as f:
                text = f.read()
            for m in re.finditer(r"\[[^\]]*\]\(([^)\s]+)[^)]*\)", text):
                t = m.group(1)
                if re.match(r"^(https?:|mailto:|#)", t):
                    continue
                t = t.split("#")[0]
                if not t:
                    continue
                target = os.path.normpath(os.path.join(os.path.dirname(path), t))
                if not inside(repo, os.path.relpath(target, repo)):
                    warnings.append("BROKEN-LINK docs/%s: %s (outside the repo) (warning)" % (rel, m.group(1)))
                elif not os.path.exists(target):
                    warnings.append("BROKEN-LINK docs/%s: %s (warning)" % (rel, m.group(1)))

        if budget_total > BUDGET:
            warnings.append("OVER-CAP docs/ %d/%d (warning)" % (budget_total, BUDGET))

        readme = os.path.join(docs, "README.md")
        readme_text = ""
        if os.path.isfile(readme):
            with open(readme, encoding="utf-8", errors="replace") as f:
                readme_text = f.read()
        for entry in sorted(os.listdir(docs)):
            if entry in ("README.md", "plans") or entry.startswith("."):
                continue
            if entry not in readme_text:
                warnings.append("UNLISTED docs/%s (warning)" % entry)

        if os.path.isdir(adr):
            seen = {}
            for fn in sorted(os.listdir(adr)):
                m = re.match(r"^(\d+)-", fn)
                if m:
                    seen.setdefault(m.group(1), []).append(fn)
            for num, fns in sorted(seen.items()):
                if len(fns) > 1:
                    warnings.append("ADR-REUSED %s (warning)" % num)

    for line in errors + warnings:
        print(line)
    print("docs-fresh: %d error(s), %d warning(s)" % (len(errors), len(warnings)))
    return 1 if errors and not advisory else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
