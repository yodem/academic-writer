"""A fake `trove` command for the pilib tests: serves books/<id>/{toc,read}.json from $FAKE_TROVE_DIR.

    trove items toc <id> --json --no-session
    trove items read <id>:all --json --no-session

Every call is appended to $FAKE_TROVE_LOG. FAKE_TROVE_TRUNCATED=1 marks the full read as truncated.
FAKE_TROVE_PAGE_LIMIT=N serves at most N pages per read and names the rest in `next`, as the real
~20 KB reply does; continuations come back as `<id> --pages a-b`.
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
env_log = os.environ.get("FAKE_TROVE_ENV_LOG")
if env_log:  # the names of the variables this child was started with (never the values)
    with open(env_log, "a", encoding="utf-8") as f:
        f.write(json.dumps(sorted(os.environ)) + "\n")
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
    # `<id>:all`, or a continuation `<id> --pages a-b [--part n]` named by a previous reply's `next`
    if args[2] == book + ":all":
        wanted = None
    elif args[2] == book and "--pages" in args:
        a, _, b = args[args.index("--pages") + 1].partition("-")
        wanted = range(int(a), int(b or a) + 1)
    else:
        sys.stderr.write("fake trove: only <id>:all or <id> --pages a-b is served\n")
        sys.exit(2)
    item = doc["items"][0]
    pages = [p for p in item.get("pages") or [] if wanted is None or int(p["pageNum"]) in wanted]
    limit = int(os.environ.get("FAKE_TROVE_PAGE_LIMIT") or 0)  # like the real ~20 KB reply: fewer pages, rest in `next`
    item["next"] = None
    if limit and len(pages) > limit:
        rest = pages[limit:]
        pages = pages[:limit]
        item["next"] = {"pages": f"{rest[0]['pageNum']}-{rest[-1]['pageNum']}"}
    item["pages"] = pages
    if os.environ.get("FAKE_TROVE_TRUNCATED"):
        doc["truncatedItemIds"] = [book]
sys.stdout.write(json.dumps(doc, ensure_ascii=False))
