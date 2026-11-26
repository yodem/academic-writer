#!/usr/bin/env python3
"""Lists Playwright tests as jsonl on stdout (run from the tree root), for the test-integrity gate.

Parameterised specs (`test(`${route} ${scheme} ${width}`)`) have titles that never appear in the source, so the
gate's source check cannot see them. This shim reuses the core's Playwright report parser, then writes each id as
`<file>::<project>::<static text found in the file>[<full describe > title chain>]`: the bracket keeps the id unique and
the static text before it (the title's longest whole-word prefix found in the file, else the innermost describe title found there, else the literal `test(`, which only proves the file still declares tests)
is what the gate looks for in the committed source (verify "word"). Skipped state comes from the report unchanged.
"""
import json
import os
import subprocess
import sys

here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
import test_integrity as core  # noqa: E402  (the same core that judges: the base's copy in CI)

tree = os.getcwd()
proc = subprocess.run(["npx", "playwright", "test", "--list", "--reporter=json"], capture_output=True, text=True)
if proc.returncode != 0:
    sys.stderr.write(proc.stderr[-2000:])
    sys.exit(proc.returncode)
texts = {}


def source(rel):
    if rel not in texts:
        try:
            with open(os.path.join(tree, rel), encoding="utf-8") as f:
                texts[rel] = f.read()
        except OSError:
            texts[rel] = ""
    return texts[rel]


def static_part(text, chain):
    title = chain[-1]
    words = title.split(" ")
    for n in range(len(words), 0, -1):
        cand = " ".join(words[:n])
        if len(cand) >= 3 and cand in text:
            return cand
    for part in reversed(chain[:-1]):
        if part in text:
            return part
    # Fully generated title (loops over fixtures): the best the source can prove is that the file still declares tests.
    return "test(" if "test(" in text else ""


for tid, skipped in core._parse_playwright(proc.stdout, tree):
    file, project, name = tid.split("::", 2)
    chain = name.split(" > ")
    out = "%s::%s::%s[%s]" % (file, project, static_part(source(file), chain).replace("[", "(").replace("]", ")"), name)
    print(json.dumps({"id": out, "skipped": bool(skipped)}))
