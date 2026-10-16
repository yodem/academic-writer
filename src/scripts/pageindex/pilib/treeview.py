"""Depth-limited, node-scoped views of a slimmed PageIndex tree (used by `pilib tree`).

A tree arrives as the nested dicts both CLIs already print: node_id, title, start_index, end_index,
optional summary, optional `nodes`. `view` can

  * scope to one node (`--node ID`): that node and its subtree;
  * cut at a depth (`--depth N`): depth 1 = the shown top level only; nodes deeper than N are not listed
    and their parent carries `children_hidden` (the count of its direct children instead);
  * with neither flag, keep the full tree when its JSON fits in MAX_CHARS, else cut to depth 2 (or the
    deepest depth that still fits, never less than 1) and add a one-line `note` saying how to expand.
"""
from __future__ import annotations

import json

MAX_CHARS = 40_000


def count(nodes) -> int:
    return sum(1 + count(n.get("nodes")) for n in nodes or [])


def find(nodes, node_id: str):
    for n in nodes or []:
        if str(n.get("node_id")) == str(node_id):
            return n
        hit = find(n.get("nodes"), node_id)
        if hit is not None:
            return hit
    return None


def cut(nodes, depth: int, level: int = 1) -> list:
    out = []
    for n in nodes:
        item = {k: v for k, v in n.items() if k != "nodes"}
        kids = n.get("nodes")
        if kids:
            if level >= depth:
                item["children_hidden"] = len(kids)
            else:
                item["nodes"] = cut(kids, depth, level + 1)
        out.append(item)
    return out


def size(nodes) -> int:
    return len(json.dumps(nodes, ensure_ascii=False))


def view(structure, depth: int | None = None, node: str | None = None, prog: str = "pilib tree",
         max_chars: int = MAX_CHARS):
    """Return (structure_to_print, note_or_None)."""
    if node is not None:
        hit = find(structure, node)
        if hit is None:
            raise SystemExit(f"no node {node!r} in this tree")
        structure = [hit]
    if depth is not None:
        return cut(structure, max(1, depth)), None
    if size(structure) <= max_chars:
        return structure, None
    depth = 2
    shown = cut(structure, depth)
    while depth > 1 and size(shown) > max_chars:
        depth -= 1
        shown = cut(structure, depth)
    note = (f"Large tree ({count(structure)} nodes): showing depth {depth}; 'children_hidden' is the number of "
            f"child nodes not listed. Expand one with `{prog} <book id> --node <node_id>` "
            f"or show more levels with `--depth N`.")
    return shown, note
