"""A fake `trove` command for the pilib tests: serves books/<id>/{toc,read}.json from $FAKE_TROVE_DIR.

    trove items toc <id> --json --no-session
    trove items read <id>:all --json --no-session

Every call is appended to $FAKE_TROVE_LOG. FAKE_TROVE_TRUNCATED=1 marks the full read as truncated.
It refuses write commands, like the real one would be asked never to be used for here.
"""
import json
import os
import sys

args = sys.argv[1:]
log = os.environ.get("FAKE_TROVE_LOG")
if log:
    with open(log, "a", encoding="utf-8") as f:
        f.write(json.dumps(args) + "\n")
root = os.environ["FAKE_TROVE_DIR"]
if args[:2] not in (["items", "toc"], ["items", "read"]) or "--json" not in args or "--no-session" not in args:
    sys.stderr.write("fake trove: unsupported call " + " ".join(args) + "\n")
    sys.exit(2)
book = args[2].split(":")[0]
name = "toc.json" if args[1] == "toc" else "read.json"
path = os.path.join(root, "books", book, name)
if not os.path.exists(path):
    sys.stderr.write("fake trove: no such item " + book + "\n")
    sys.exit(1)
doc = json.load(open(path, encoding="utf-8"))
if args[1] == "read":
    if args[2] != book + ":all":
        sys.stderr.write("fake trove: only <id>:all is served\n")
        sys.exit(2)
    if os.environ.get("FAKE_TROVE_TRUNCATED"):
        doc["truncatedItemIds"] = [book]
sys.stdout.write(json.dumps(doc, ensure_ascii=False))
