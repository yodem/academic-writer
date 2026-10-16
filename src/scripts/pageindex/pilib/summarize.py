"""Node summaries for a native tree: one model call per node, bottom up, reused when nothing changed.

A leaf is summarised from its own pages. A parent is summarised from the summaries of its children, so a
long book costs one short call per node instead of one huge call. Every call goes through
`litellm.completion` (looked up on the module each time) so `LLMMeter` counts it, caps it and prices it.

The cache maps a key to a summary. The key covers the model, the node's title and page range, and the exact
text it was written from (the pages for a leaf, the child summaries for a parent), so a re-index calls the
model only for nodes whose own text, or whose descendants' text, changed.
"""
from __future__ import annotations

import hashlib
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from .errors import IndexFailure, scrub
from .meter import CallCapExceeded
from .render_trove import clean

MAX_NODE_CHARS = 48000      # leaf text sent per call; longer sections are cut at this many characters
MAX_CHILD_CHARS = 40000     # parent input: titles and child summaries are cut at this many characters
SUMMARY_WORDS = 90          # the length the model is asked for
ATTEMPTS = 2                # one retry per node on a model error
RETRY_PAUSE = 1.0           # seconds before the retry
REQUEST_TIMEOUT = 120       # seconds per model call
EARLY_ABORT_FAILURES = 5    # this many failures with no success stop the run (bad key, wrong model name)
REASONING_EFFORT = "low"

LEAF_PROMPT = (
    "You index a scholarly text so a researcher can decide which pages to open. Summarise this section of "
    "\"{title}\" in at most {words} words, in the language of the text. Say what it argues or contains: main "
    "claims, named people, works, terms and cases. Plain prose, no markdown, no preamble.\n\nSection pages:\n{text}"
)
PARENT_PROMPT = (
    "You index a scholarly text so a researcher can decide which pages to open. Below are the summaries of the "
    "parts of \"{title}\". Write one overview of the whole in at most {words} words, in the language of the "
    "summaries. Plain prose, no markdown, no preamble.\n\nParts:\n{text}"
)

_DATA_URI = re.compile(r"data:[\w/+.-]+;base64,[A-Za-z0-9+/=]+")


def walk(nodes, depth=0):
    for node in nodes or []:
        yield depth, node
        yield from walk(node.get("nodes"), depth + 1)


def node_text(node: dict, pages: list) -> str:
    text = "\n\n".join(pages[node["start_index"] - 1:node["end_index"]])
    return _DATA_URI.sub("[diagram]", clean(text)).strip()[:MAX_NODE_CHARS]


def child_text(node: dict) -> str:
    lines = []
    for child in node.get("nodes") or []:
        summary = (child.get("summary") or child.get("prefix_summary") or "").strip()
        if summary:
            lines.append(f"- {child['title'][:200]}: {summary}")
    return "\n".join(lines)[:MAX_CHILD_CHARS]


def cache_key(kind: str, model: str, node: dict, text: str) -> str:
    raw = "\x1f".join([kind, model, node["title"], str(node["start_index"]), str(node["end_index"]), text])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def summary_field(node: dict) -> str:
    return "prefix_summary" if node.get("nodes") else "summary"


def complete(model: str, prompt: str) -> str:
    import litellm
    last = None
    for attempt in range(ATTEMPTS):
        try:
            response = litellm.completion(model=model, messages=[{"role": "user", "content": prompt}],
                                          reasoning_effort=REASONING_EFFORT, drop_params=True,
                                          timeout=REQUEST_TIMEOUT)
            text = (response.choices[0].message.content or "").strip()
            if not text:
                raise ValueError("the model returned an empty summary")
            return text
        except Exception as error:  # CallCapExceeded is a BaseException and passes through
            last = error
            if attempt + 1 < ATTEMPTS:
                time.sleep(RETRY_PAUSE)
    raise last


def summarize(structure: list, pages: list, model: str, meter, concurrency: int, cache: dict, dry_run: bool = False):
    """Fill `summary` (leaf) / `prefix_summary` (parent) on every node.

    Returns (stats, used) where used maps cache key -> summary for the nodes that now carry one, and stats has
    nodes, reused, generated, failed, empty, expected_calls and input_chars (the text still to be sent).
    On a cap or a model that never answers it raises IndexFailure carrying `partial`, the summaries written so far.
    """
    stats = {"nodes": 0, "reused": 0, "generated": 0, "failed": 0, "empty": 0, "expected_calls": 0, "input_chars": 0}
    used: dict = {}
    unknown: set = set()  # dry run only: nodes whose summary would have to be generated, so their parent's input is not known yet
    successes = failures = 0
    by_depth: dict = {}
    for depth, node in walk(structure):
        by_depth.setdefault(depth, []).append(node)
        stats["nodes"] += 1
    last_error = ""
    for depth in sorted(by_depth, reverse=True):
        jobs = []  # (node, key, prompt)
        for node in by_depth[depth]:
            parent = bool(node.get("nodes"))
            if dry_run and parent and any(id(child) in unknown for child in node["nodes"]):
                unknown.add(id(node))
                stats["expected_calls"] += 1
                continue
            text = child_text(node) if parent else node_text(node, pages)
            if not text:
                stats["empty"] += 1
                continue
            kind = "parent" if parent else "leaf"
            key = cache_key(kind, model, node, text)
            if key in cache:
                node[summary_field(node)] = cache[key]
                used[key] = cache[key]
                stats["reused"] += 1
                continue
            stats["expected_calls"] += 1
            stats["input_chars"] += len(text)
            if dry_run:
                unknown.add(id(node))
            template = PARENT_PROMPT if parent else LEAF_PROMPT
            jobs.append((node, key, template.format(title=node["title"][:200], words=SUMMARY_WORDS, text=text)))
        if dry_run or not jobs:
            continue
        executor = ThreadPoolExecutor(max_workers=max(1, concurrency))
        futures = {executor.submit(complete, model, prompt): (node, key) for node, key, prompt in jobs}
        capped = stalled = False
        try:
            for future in as_completed(futures):
                try:
                    text = future.result()
                except CallCapExceeded:
                    capped = True
                    break
                except Exception as error:
                    failures += 1
                    stats["failed"] += 1
                    last_error = scrub(error, 200)
                    if successes == 0 and failures >= EARLY_ABORT_FAILURES:
                        stalled = True
                        break
                    continue
                node, key = futures[future]
                node[summary_field(node)] = text
                used[key] = text
                successes += 1
                stats["generated"] += 1
        finally:
            executor.shutdown(wait=True, cancel_futures=True)
        if capped or stalled:
            for future, (node, key) in futures.items():  # keep what finished while the others were stopped
                if future.done() and not future.cancelled() and future.exception() is None and key not in used:
                    used[key] = future.result()
                    stats["generated"] += 1
            if capped:
                raise IndexFailure("call_cap", f"stopped at the model call cap ({meter.cap}); the summaries done so far are kept, "
                                   "raise --max-calls and run again to finish", partial=used)
            raise IndexFailure("model_failed", f"the model did not answer ({failures} failed calls, none succeeded): {last_error}",
                               partial=used)
    return stats, used
