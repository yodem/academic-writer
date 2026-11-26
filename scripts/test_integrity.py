#!/usr/bin/env python3
"""Test-integrity gate: compare the test runner's own collected test list on base vs head.

Subcommands: list, run, list-unittest.  Python 3.9+, stdlib only.
Exit codes for `run`: 0 pass, 1 test(s) missing / newly skipped / guarded change, 2 invalid input.
"""
import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
import unittest

EXEMPT_RE = re.compile(r"^tests-removed:\s*(\S+)\s+(?:—|-{1,3})+\s+(.{8,})$")


class Invalid(Exception):
    """Anything that makes the verdict impossible (exit 2)."""


# ---------------------------------------------------------------- listing

def _load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        raise Invalid("cannot read JSON %s: %s" % (path, e))


def load_config(path):
    cfg = _load_json(path)
    if not isinstance(cfg, dict):
        raise Invalid("config must be an object")
    for key, typ in (("maintainers", list), ("label", str), ("suites", list), ("guarded", list)):
        if not isinstance(cfg.get(key), typ):
            raise Invalid("config key %r missing or wrong type" % key)
    cfg.setdefault("guarded_package_scripts", [])
    for s in cfg["suites"]:
        if not isinstance(s, dict) or not all(k in s for k in ("name", "cmd", "format")):
            raise Invalid("each suite needs name, cmd, format")
        if s["format"] not in ("jsonl", "vitest-json", "playwright-json"):
            raise Invalid("suite %s: unknown format %r" % (s["name"], s["format"]))
    return cfg


def _rel(path, tree):
    if os.path.isabs(path):
        path = os.path.relpath(path, tree)
    return path.replace(os.sep, "/")


def _parse_jsonl(out):
    items = []
    for line in out.splitlines():
        if line.strip():
            d = json.loads(line)
            items.append((str(d["id"]), bool(d.get("skipped", False))))
    return items


def _parse_vitest(out, tree):
    return [("%s::%s" % (_rel(t["file"], tree), t["name"]), False) for t in json.loads(out)]


def _walk_playwright(suite, path, tree, acc):
    here = path + ([suite["title"]] if suite.get("title") and not suite.get("file") else [])
    for spec in suite.get("specs", []):
        file = _rel(spec.get("file") or suite.get("file") or "", tree)
        for t in spec.get("tests", []):
            skipped = t.get("expectedStatus") == "skipped" or any(
                a.get("type") in ("skip", "fixme") for a in t.get("annotations", []))
            name = " > ".join(here + [spec["title"]])
            acc.append(("%s::%s::%s" % (file, t.get("projectName", ""), name), skipped))
    for child in suite.get("suites", []):
        _walk_playwright(child, here, tree, acc)


def _parse_playwright(out, tree):
    acc = []
    for s in json.loads(out).get("suites", []):
        _walk_playwright(s, [], tree, acc)
    return acc


def list_suite(suite, tree):
    cwd = os.path.join(tree, suite.get("cwd", "."))
    name = suite["name"]
    try:
        core = os.path.abspath(__file__)
        cmd = [a.replace("{core_dir}", os.path.dirname(core)) if a != "{core}" else core for a in suite["cmd"]]
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    except OSError as e:
        raise Invalid("suite %s: cannot run lister: %s" % (name, e))
    if proc.returncode != 0:
        raise Invalid("suite %s: lister exited %d: %s" % (name, proc.returncode, proc.stderr.strip()[-500:]))
    try:
        if suite["format"] == "jsonl":
            items = _parse_jsonl(proc.stdout)
        elif suite["format"] == "vitest-json":
            items = _parse_vitest(proc.stdout, tree)
        else:
            items = _parse_playwright(proc.stdout, tree)
    except (ValueError, KeyError, TypeError, AttributeError) as e:
        raise Invalid("suite %s: unparseable lister output (%s: %s)" % (name, type(e).__name__, e))
    if not items:
        raise Invalid("suite %s: lister returned zero tests" % name)
    return [{"suite": name, "id": "%s::%s" % (name, i), "skipped": sk} for i, sk in items]


def list_tree(cfg, tree):
    rows = []
    for suite in cfg["suites"]:
        rows.extend(list_suite(suite, tree))
    return rows


def read_list_file(path):
    rows = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    d = json.loads(line)
                    rows.append({"suite": d["suite"], "id": d["id"], "skipped": bool(d["skipped"])})
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise Invalid("unparseable test list %s: %s" % (path, e))
    if not rows:
        raise Invalid("empty test list %s" % path)
    return rows


def write_rows(rows, out):
    text = "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows)
    if out:
        with open(out, "w", encoding="utf-8") as f:
            f.write(text)
    else:
        sys.stdout.write(text)


# ---------------------------------------------------------------- run

def exemptions(body):
    found = {}
    for line in body.splitlines():
        m = EXEMPT_RE.match(line.strip())
        if m:
            found[m.group(1)] = m.group(2)
    return found


def _read_text(path):
    if not path:
        return ""
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _json_values(text):
    """Parse one or more concatenated JSON documents; arrays are flattened."""
    dec, i, out = json.JSONDecoder(), 0, []
    text = text.strip()
    while i < len(text):
        val, j = dec.raw_decode(text, i)
        out.extend(val if isinstance(val, list) else [val])
        i = j
        while i < len(text) and text[i].isspace():
            i += 1
    return out


def label_valid(cfg, labels_file, events_file):
    """The label must be present now and last applied by a maintainer."""
    label = cfg["label"]
    labels = _read_text(labels_file)
    present = {x.strip() for x in re.split(r"[,\n]", labels) if x.strip()}
    if labels.strip().startswith("["):
        try:
            present = {x["name"] if isinstance(x, dict) else x for x in _json_values(labels)}
        except (ValueError, KeyError, TypeError):
            present = set()
    if label not in present:
        return False
    try:
        events = _json_values(_read_text(events_file))
    except ValueError:
        return False
    last = None
    for ev in events:
        if isinstance(ev, dict) and ev.get("event") == "labeled" and (ev.get("label") or {}).get("name") == label:
            last = ev
    return bool(last) and (last.get("actor") or {}).get("login") in cfg["maintainers"]


def glob_match(path, pattern):
    regex, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            regex += "(?:.*/)?"
            i += 3
        elif pattern.startswith("**", i):
            regex += ".*"
            i += 2
        elif pattern[i] == "*":
            regex += "[^/]*"
            i += 1
        else:
            regex += re.escape(pattern[i]) if pattern[i] != "?" else "[^/]"
            i += 1
    return re.fullmatch(regex, path) is not None or fnmatch.fnmatchcase(path, pattern)


def git(tree, *args):
    proc = subprocess.run(["git", "-C", tree] + list(args), capture_output=True, text=True)
    if proc.returncode != 0:
        raise Invalid("git %s failed: %s" % (" ".join(args), proc.stderr.strip()))
    return proc.stdout


def _scripts_of(text):
    try:
        d = json.loads(text) if text else {}
        return d.get("scripts", {}) if isinstance(d, dict) else {}
    except ValueError:
        return {"<unparseable>": text}


def guarded_changes(cfg, base_tree, head_tree, base_ref):
    git(head_tree, "rev-parse", "--verify", "--quiet", base_ref + "^{commit}")
    changed = [p for p in git(head_tree, "diff", "--name-only", base_ref + "...HEAD").splitlines() if p]
    hits = ["%s (matches %s)" % (p, g) for p in changed for g in cfg["guarded"] if glob_match(p, g)]
    hits = sorted(set(hits))
    for pj in cfg["guarded_package_scripts"]:
        if pj not in changed:
            continue
        base_text = ""
        base_path = os.path.join(base_tree, pj)
        if os.path.exists(base_path):
            base_text = _read_text(base_path)
        head_text = _read_text(os.path.join(head_tree, pj))
        if _scripts_of(base_text) != _scripts_of(head_text):
            hits.append("%s (scripts changed)" % pj)
    return hits


def cmd_run(args):
    cfg = load_config(args.config)
    base = read_list_file(args.base_list) if args.base_list else list_tree(cfg, args.base_tree)
    head = read_list_file(args.head_list) if args.head_list else list_tree(cfg, args.head_tree)
    base_map = {r["id"]: r["skipped"] for r in base}
    head_map = {r["id"]: r["skipped"] for r in head}
    missing = sorted(i for i in base_map if i not in head_map)
    newly_skipped = sorted(i for i in head_map if head_map[i] and i in base_map and not base_map[i])
    guarded = guarded_changes(cfg, args.base_tree, args.head_tree, args.base_ref)

    valid = label_valid(cfg, args.labels_file, args.label_events_file)
    excused = exemptions(_read_text(args.pr_body_file))
    for i in sorted(excused):
        if i not in missing and i not in newly_skipped:
            print("test-integrity: warning: exemption names %s, which is not missing or newly skipped" % i)

    problems = []
    for i in missing:
        if not (valid and i in excused):
            problems.append("missing on head: %s" % i)
    for i in newly_skipped:
        if not (valid and i in excused):
            problems.append("newly skipped on head: %s" % i)
    if guarded and not valid:
        problems.extend("guarded change without a valid %s label: %s" % (cfg["label"], g) for g in guarded)

    if problems:
        print("test-integrity: FAIL (tests missing or newly skipped, or guarded files changed)")
        for p in problems:
            print("  " + p)
        print("  An exemption needs the %r label from a maintainer after the latest push, "
              "plus a 'tests-removed: <id> -- <reason>' line in the PR body." % cfg["label"])
        return 1
    print("test-integrity: OK base=%d head=%d" % (len(base_map), len(head_map)))
    return 0


def cmd_list(args):
    cfg = load_config(args.config)
    write_rows(list_tree(cfg, args.tree), args.out)
    return 0


# ---------------------------------------------------------------- unittest lister

def _flatten(suite):
    for t in suite:
        if isinstance(t, unittest.TestSuite):
            yield from _flatten(t)
        else:
            yield t


def cmd_list_unittest(args):
    root = os.getcwd()
    tests = []
    for d in args.dirs:
        start = os.path.abspath(d)
        tests.extend(_flatten(unittest.TestLoader().discover(start, top_level_dir=start)))
    rows = []
    for t in tests:
        cls = type(t)
        if cls.__name__ == "_FailedTest":
            print("import failure: %s" % t.id(), file=sys.stderr)
            return 3
        mod = sys.modules[cls.__module__]
        path = _rel(getattr(mod, "__file__", cls.__module__), root)
        method = getattr(cls, t._testMethodName, None)
        skipped = bool(getattr(cls, "__unittest_skip__", False) or getattr(method, "__unittest_skip__", False))
        rows.append({"id": "%s::%s.%s" % (path, cls.__name__, t._testMethodName), "skipped": skipped})
    for r in sorted(rows, key=lambda r: r["id"]):
        print(json.dumps(r))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("list")
    a.add_argument("--config", required=True)
    a.add_argument("--tree", required=True)
    a.add_argument("--out")
    r = sub.add_parser("run")
    r.add_argument("--config", required=True)
    r.add_argument("--base-tree", required=True)
    r.add_argument("--head-tree", required=True)
    r.add_argument("--base-ref", required=True)
    r.add_argument("--pr-body-file")
    r.add_argument("--labels-file")
    r.add_argument("--label-events-file")
    r.add_argument("--base-list")
    r.add_argument("--head-list")
    u = sub.add_parser("list-unittest")
    u.add_argument("dirs", nargs="+")
    args = p.parse_args(argv)
    try:
        return {"list": cmd_list, "run": cmd_run, "list-unittest": cmd_list_unittest}[args.cmd](args)
    except Invalid as e:
        print("test-integrity: invalid: %s" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
