#!/usr/bin/env python3
"""Test-integrity gate: compare the test runner's own collected test list on base vs head.

Subcommands: list, run, list-unittest.  Python 3.9+, stdlib only.
Exit codes for `run`: 0 pass, 1 test(s) missing / newly skipped / guarded change, 2 invalid input.
See scripts/TEST-INTEGRITY.md for usage and known limits.
Limits: skips decided at run time (skipTest(), setUpClass SkipTest, pytest.skip()) are not visible to listing.
"""
import argparse
import fnmatch
import json
import os
import re
import signal
import subprocess
import sys
import unittest

MAX_BODY_BYTES = 65536


class Invalid(Exception):
    """Anything that makes the verdict impossible (exit 2)."""


# ---------------------------------------------------------------- listing

def _load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        raise Invalid("cannot read JSON %s: %s" % (path, e))


DEFAULT_SKIP_MARKERS = [
    r"@unittest\.skip(?:If|Unless)?\b", r"\.skipTest\(", r"raise\s+(?:unittest\.)?SkipTest",
    r"pytest\.mark\.(?:skip|skipif|xfail)\b", r"pytest\.skip\(",
    r"\.(?:skip|skipIf|todo|only|fixme)\(",  # js: it.skip( .todo( test.fixme( it.only( (only hides the others)
    r"\b(?:xit|xdescribe|xtest)\(",
]


def _str_list(cfg, key, required):
    val = cfg.get(key, None if required else [])
    if not isinstance(val, list) or not all(isinstance(x, str) for x in val):
        raise Invalid("config key %r must be a list of strings" % key)
    return val


def load_config(path):
    cfg = _load_json(path)
    if not isinstance(cfg, dict):
        raise Invalid("config must be an object")
    _str_list(cfg, "maintainers", True)
    _str_list(cfg, "guarded", True)
    _str_list(cfg, "guarded_package_scripts", False)
    if not isinstance(cfg.get("label"), str) or not cfg["label"]:
        raise Invalid("config key 'label' must be a non-empty string")
    if not isinstance(cfg.get("suites"), list) or not cfg["suites"]:
        raise Invalid("config key 'suites' must be a non-empty list")
    cfg.setdefault("guarded_package_scripts", [])
    names = set()
    for s in cfg["suites"]:
        if not isinstance(s, dict):
            raise Invalid("each suite must be an object")
        name = s.get("name")
        if not isinstance(name, str) or not name or name in names:
            raise Invalid("suite name must be a unique non-empty string: %r" % (name,))
        names.add(name)
        if not isinstance(s.get("cmd"), list) or not s["cmd"] or not all(isinstance(x, str) for x in s["cmd"]):
            raise Invalid("suite %s: cmd must be a non-empty list of strings" % name)
        if not isinstance(s.get("cwd", "."), str):
            raise Invalid("suite %s: cwd must be a string" % name)
        t = s.get("timeout_s", 600)
        if isinstance(t, bool) or not isinstance(t, (int, float)) or t <= 0:
            raise Invalid("suite %s: timeout_s must be a positive number" % name)
        if s.get("verify", "word") not in ("word", "literal", "none"):
            raise Invalid("suite %s: verify must be word, literal or none" % name)
        if s.get("format") not in ("jsonl", "vitest-json", "playwright-json"):
            raise Invalid("suite %s: unknown format %r" % (name, s.get("format")))
    markers = _str_list(cfg, "skip_markers", False) or DEFAULT_SKIP_MARKERS
    for m in markers:
        try:
            re.compile(m)
        except re.error as e:
            raise Invalid("skip_markers: invalid regex %r: %s" % (m, e))
    cfg["skip_markers"] = markers
    return cfg


def _rel(path, tree):
    if os.path.isabs(path):
        path = os.path.relpath(path, tree)
    return path.replace(os.sep, "/")


def _record(d):
    """Strict shape: an object with a non-empty string id and a boolean skipped; anything else is invalid."""
    if not isinstance(d, dict) or not isinstance(d.get("id"), str) or not d["id"]:
        raise ValueError("record needs a non-empty string id: %r" % (d,))
    if not isinstance(d.get("skipped"), bool):
        raise ValueError("record needs a boolean skipped: %r" % (d,))
    return d["id"], d["skipped"]


def _parse_jsonl(out):
    return [_record(json.loads(line)) for line in out.splitlines() if line.strip()]


def _parse_vitest(out, tree):
    return [("%s::%s" % (_rel(t["file"], tree), t["name"]), False) for t in json.loads(out)]


def _walk_playwright(suite, path, tree, acc):
    title = suite.get("title")
    # Only the top-level file suite (title == its file) is omitted; every describe title is kept.
    here = path + ([title] if title and title != suite.get("file") else [])
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
        timeout = suite.get("timeout_s", 600)
        popen = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                 start_new_session=True)
        try:
            stdout, stderr = popen.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(popen.pid, signal.SIGKILL)
            popen.communicate()
            raise Invalid("suite %s: lister timed out after %ss" % (name, timeout))
        proc = subprocess.CompletedProcess(cmd, popen.returncode, stdout, stderr)
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
    _no_duplicates([i for i, _ in items], "suite %s" % name)
    return [{"suite": name, "id": "%s::%s" % (name, i), "skipped": sk} for i, sk in items]


def _no_duplicates(ids, where):
    seen, dup = set(), set()
    for i in ids:
        (dup if i in seen else seen).add(i)
    if dup:
        raise Invalid("%s: duplicate test id: %s" % (where, sorted(dup)[0]))


def list_tree(cfg, tree):
    rows = []
    for suite in cfg["suites"]:
        rows.extend(list_suite(suite, tree))
    return rows


def read_list_file(path):
    """Returns (rows, meta); an optional first record {"meta": {...}} carries the head sha the list was made for."""
    rows, meta = [], {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    d = json.loads(line)
                    if isinstance(d, dict) and set(d) == {"meta"} and isinstance(d["meta"], dict):
                        meta = d["meta"]
                        continue
                    tid, skipped = _record(d)
                    if not isinstance(d.get("suite"), str) or not d["suite"]:
                        raise ValueError("record needs a non-empty string suite: %r" % (d,))
                    rows.append({"suite": d["suite"], "id": tid, "skipped": skipped})
    except (OSError, ValueError) as e:
        raise Invalid("unparseable test list %s: %s" % (path, e))
    if not rows:
        raise Invalid("empty test list %s" % path)
    _no_duplicates([r["id"] for r in rows], "list %s" % path)
    return rows, meta


def write_rows(rows, out, meta=None):
    text = (json.dumps({"meta": meta}) + "\n" if meta else "") + "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows)
    if out:
        with open(out, "w", encoding="utf-8") as f:
            f.write(text)
    else:
        sys.stdout.write(text)


# ---------------------------------------------------------------- run

def exemptions(body, known_ids):
    """Returns ({id: reason}, [unmatched lines]).  A `tests-removed:` line excuses the LONGEST known id that its
    text starts with, provided a separator (" \u2014 " or " -- ") and a reason of 8+ chars follow it."""
    ids = sorted(known_ids, key=len, reverse=True)
    found, unmatched = {}, []
    for line in body.splitlines():
        line = line.strip()
        if not line.startswith("tests-removed:"):
            continue
        rest = line[len("tests-removed:"):].strip()
        hit = None
        for tid in ids:
            tail = rest[len(tid):] if rest.startswith(tid) else None
            for sep in (" \u2014 ", " -- "):
                if tail is not None and tail.startswith(sep) and len(tail[len(sep):].strip()) >= 8:
                    hit = (tid, tail[len(sep):].strip())
                    break
            if hit:
                break
        if hit:
            found[hit[0]] = hit[1]
        else:
            unmatched.append(rest)
    return found, unmatched


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


def label_valid(cfg, labels, events_text):
    """The label must be present now and last applied by a maintainer (inputs are already-read text)."""
    label = cfg["label"]
    try:
        present = {x["name"] if isinstance(x, dict) else x for x in _json_values(labels)}
    except (ValueError, KeyError, TypeError):
        present = set()
    if label not in present:
        return False
    try:
        events = _json_values(events_text)
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


def _git_argv(tree):
    """Every git call ignores replace refs and fsmonitor hooks, so repo-local config cannot change what is read."""
    return ["git", "--no-replace-objects", "-c", "core.fsmonitor=false", "-C", tree]


def git(tree, *args):
    proc = subprocess.run(_git_argv(tree) + list(args), capture_output=True, text=True)
    if proc.returncode != 0:
        raise Invalid("git %s failed: %s" % (" ".join(args), proc.stderr.strip()))
    return proc.stdout


def _scripts_of(text):
    try:
        d = json.loads(text) if text else {}
        return d.get("scripts", {}) if isinstance(d, dict) else {}
    except ValueError:
        return {"<unparseable>": text}


def _git_show(tree, ref, path):
    proc = subprocess.run(_git_argv(tree) + ["show", "%s:%s" % (ref, path)], capture_output=True, text=True)
    return proc.stdout if proc.returncode == 0 else ""


def guarded_changes(cfg, head_tree, base_sha, head_sha):
    raw = git(head_tree, "diff", "--no-renames", "--name-only", "-z", "%s...%s" % (base_sha, head_sha))
    changed = [p for p in raw.split("\0") if p]
    hits = sorted({"%s (matches %s)" % (p, g) for p in changed for g in cfg["guarded"] if glob_match(p, g)})
    for pj in cfg["guarded_package_scripts"]:
        if pj in changed and _scripts_of(_git_show(head_tree, base_sha, pj)) != _scripts_of(_git_show(head_tree, head_sha, pj)):
            hits.append("%s (scripts changed)" % pj)
    return hits


# ---- source check: a lister's output is not trusted alone; ids must still appear in the head tree's source

def _source_probe(suite, tid):
    """Return (relative file, matcher) for an id, or None when the id cannot be checked."""
    prefix = suite["name"] + "::"
    if not tid.startswith(prefix) or suite.get("verify", "") == "none":
        return None
    rest = tid[len(prefix):]
    if "::" not in rest:
        return None
    file, rest = rest.split("::", 1)
    if suite["format"] == "playwright-json":
        rest = rest.split("::", 1)[-1]
    mode = suite.get("verify") or ("word" if suite["format"] == "jsonl" else "literal")
    if mode == "word":
        seg = rest.split("::")[-1].split("[")[0].split(".")[-1]
        pat = re.compile(r"(?<!\w)%s(?!\w)" % re.escape(seg)) if seg else None
        return (file, (lambda text: pat.search(text) is not None)) if pat else None
    title = rest.split(" > ")[-1]
    return (file, (lambda text: title in text)) if title else None


def _has_source(repo, sha, probe, cache):
    """Check committed content only: `git show <sha>:<file>` in the head repo, never the working tree."""
    file, match = probe
    if file not in cache:
        proc = subprocess.run(_git_argv(repo) + ["show", "%s:%s" % (sha, file)], capture_output=True)
        cache[file] = proc.stdout.decode("utf-8", "replace") if proc.returncode == 0 else None
    return cache[file] is not None and match(cache[file])


def source_missing(cfg, repo, base_sha, head_sha, ids):
    """ids present on both sides; returns (ids whose source vanished on head, count unverifiable)."""
    suites = {s["name"]: s for s in cfg["suites"]}
    base_cache, head_cache, gone, unverifiable = {}, {}, [], 0
    for tid in ids:
        suite = suites.get(tid.split("::", 1)[0])
        probe = _source_probe(suite, tid) if suite else None
        if probe is None or not _has_source(repo, base_sha, probe, base_cache):
            unverifiable += 1
        elif not _has_source(repo, head_sha, probe, head_cache):
            gone.append(tid)
    return gone, unverifiable


def _file_of(tid):
    parts = tid.split("::")
    return parts[1] if len(parts) > 2 else None


def skip_marker_additions(cfg, repo, base_sha, head_sha, ids):
    """Trusted skip state: count skip markers in the committed base and head blobs of every file with a base id."""
    regexes = [re.compile(m) for m in cfg["skip_markers"]]

    def count(sha, file):
        proc = subprocess.run(_git_argv(repo) + ["show", "%s:%s" % (sha, file)], capture_output=True)
        text = proc.stdout.decode("utf-8", "replace") if proc.returncode == 0 else ""
        return sum(len(r.findall(text)) for r in regexes)

    hits = []
    for file in sorted({f for f in map(_file_of, ids) if f}):
        added = count(head_sha, file) - count(base_sha, file)
        if added > 0:
            hits.append("skip markers added: %s (+%d)" % (file, added))
    return hits


def cmd_run(args):
    cfg = load_config(args.config)
    # Judge inputs are read and fixed BEFORE any lister runs (listers execute PR code).
    base_sha = git(args.head_tree, "rev-parse", "--verify", args.base_ref + "^{commit}").strip()
    head_sha = git(args.head_tree, "rev-parse", "--verify", "HEAD^{commit}").strip()
    guarded = guarded_changes(cfg, args.head_tree, base_sha, head_sha)
    body_text = _read_text(args.pr_body_file)
    if len(body_text.encode("utf-8")) > MAX_BODY_BYTES:
        raise Invalid("PR body is larger than %d bytes" % MAX_BODY_BYTES)
    valid = label_valid(cfg, _read_text(args.labels_file), _read_text(args.label_events_file))
    if args.head_sha and args.head_sha != head_sha:
        raise Invalid("checked-out head %s is not the event head sha %s" % (head_sha, args.head_sha))
    base = read_list_file(args.base_list)[0] if args.base_list else list_tree(cfg, args.base_tree)
    if args.head_list:
        head, meta = read_list_file(args.head_list)
        if args.head_sha and meta.get("head_sha") != args.head_sha:
            raise Invalid("head list was made for %s, not the event head sha %s" % (meta.get("head_sha"), args.head_sha))
    else:
        head = list_tree(cfg, args.head_tree)  # head last
    base_map = {r["id"]: r["skipped"] for r in base}
    head_map = {r["id"]: r["skipped"] for r in head}
    missing = {i for i in base_map if i not in head_map}
    gone, unverifiable = source_missing(cfg, args.head_tree, base_sha, head_sha, [i for i in base_map if i in head_map])
    forged = set(gone)
    missing |= forged
    markers = skip_marker_additions(cfg, args.head_tree, base_sha, head_sha, list(base_map))
    newly_skipped = sorted(i for i in head_map if head_map[i] and i in base_map and not base_map[i])
    excused, unmatched = exemptions(body_text, set(missing) | set(newly_skipped))
    for line in unmatched:
        print("test-integrity: warning: exemption line names no missing or newly skipped test: %s" % line[:200])

    problems = []
    for i in sorted(missing):
        if not (valid and i in excused):
            note = " (not found in source)" if i in forged else ""
            problems.append("missing on head%s: %s" % (note, i))
    for i in newly_skipped:
        if not (valid and i in excused):
            problems.append("newly skipped on head: %s" % i)
    if markers and not valid:
        problems.extend(markers)
    if guarded and not valid:
        problems.extend("guarded change without a valid %s label: %s" % (cfg["label"], g) for g in guarded)

    if problems:
        print("test-integrity: FAIL (tests missing or newly skipped, or guarded files changed)")
        for p in problems:
            print("  " + p)
        print("  An exemption needs the %r label from a maintainer after the latest push, "
              "plus a 'tests-removed: <id> -- <reason>' line in the PR body." % cfg["label"])
        return 1
    print("test-integrity: source check: %d unverifiable id(s)" % unverifiable)
    print("test-integrity: OK base=%d head=%d" % (len(base_map), len(head_map)))
    return 0


def cmd_list(args):
    cfg = load_config(args.config)
    meta = None
    if args.head_sha:
        actual = git(args.tree, "rev-parse", "--verify", "HEAD^{commit}").strip()
        if actual != args.head_sha:
            raise Invalid("tree HEAD %s is not the expected head sha %s" % (actual, args.head_sha))
        meta = {"head_sha": actual}
    write_rows(list_tree(cfg, args.tree), args.out, meta)
    return 0


# ---------------------------------------------------------------- unittest lister

def _flatten(suite):
    for t in suite:
        if isinstance(t, unittest.TestSuite):
            yield from _flatten(t)
        else:
            yield t


def cmd_list_unittest(args):
    """Each existing root is listed in its own subprocess, so same-named modules in two roots cannot collide.
    A root absent in this tree contributes no tests (its tests then show as missing on head)."""
    if args.single:
        return _list_unittest_root(args.dirs[0])
    for d in args.dirs:
        if not os.path.isdir(d):
            continue
        proc = subprocess.run([sys.executable, os.path.abspath(__file__), "list-unittest", "--single", d],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        sys.stderr.write(proc.stderr)
        if proc.returncode != 0:
            return proc.returncode
        sys.stdout.write(proc.stdout)
    return 0


def _list_unittest_root(d):
    root = os.getcwd()
    start = os.path.abspath(d)
    tests = list(_flatten(unittest.TestLoader().discover(start, top_level_dir=start)))
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
    a.add_argument("--head-sha")
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
    r.add_argument("--head-sha", help="PR head sha from the event payload; the head list must carry the same sha")
    u = sub.add_parser("list-unittest")
    u.add_argument("--single", action="store_true", help=argparse.SUPPRESS)
    u.add_argument("dirs", nargs="+")
    args = p.parse_args(argv)
    try:
        return {"list": cmd_list, "run": cmd_run, "list-unittest": cmd_list_unittest}[args.cmd](args)
    except Invalid as e:
        print("test-integrity: invalid: %s" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
