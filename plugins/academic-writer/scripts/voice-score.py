#!/usr/bin/env python3
"""Compare draft prose with an author's corpus using a compact authorship distance."""
import argparse
import json
import re
import statistics
from collections import Counter
from pathlib import Path

FUNCTION = set('אני אתה הוא היא הם הן של את על עם כי אשר אם גם לא או אבל כאשר מן אל כל בין זאת זה'.split())

def prose(path: Path) -> str:
    text = path.read_text(encoding='utf-8')
    text = re.sub(r'```.*?```', ' ', text, flags=re.S)
    text = re.sub(r'(?m)^[ \t]*(?:\[\^\d+\]|\^\d+)[ \t].*$', ' ', text)
    text = re.sub(r'\[[^\]]*\]\([^)]*\)', ' ', text)
    text = re.sub(r'“[^”]*”|"[^"]*"|״[^״]*״|«[^»]*»', ' ', text)
    text = re.sub(r'(?m)^[ \t]*>.*$', ' ', text)
    return text

def features(text: str) -> Counter[str]:
    words = re.findall(r'[^\W_]+', text.lower(), flags=re.UNICODE)
    total = max(len(words), 1)
    counts: Counter[str] = Counter({f'w:{word}': n / total for word, n in Counter(w for w in words if w in FUNCTION).items()})
    compact = re.sub(r'\s+', ' ', text.lower())
    grams = [compact[i:i+3] for i in range(max(0, len(compact)-2))]
    counts.update({f'g:{gram}': n / max(len(grams), 1) for gram, n in Counter(grams).items()})
    return counts

def distance(left: Counter[str], right: Counter[str]) -> float:
    dot = sum(value * right.get(key, 0.0) for key, value in left.items())
    norm_l = sum(v*v for v in left.values()) ** .5
    norm_r = sum(v*v for v in right.values()) ** .5
    return 1.0 - dot / (norm_l * norm_r) if norm_l and norm_r else 1.0

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--drafts', required=True, type=Path)
    parser.add_argument('--author', required=True, type=Path)
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    authors = [p for p in args.author.rglob('*') if p.is_file() and p.suffix.lower() in {'.md', '.txt'}]
    if not authors:
        parser.error('author directory contains no Markdown or text files')
    draft_files = [args.drafts] if args.drafts.is_file() else [p for p in args.drafts.rglob('*') if p.is_file() and p.suffix.lower() in {'.md', '.txt'}]
    author_features = [features(prose(p)) for p in authors]
    distances = [distance(features(prose(p)), f) for p in draft_files for f in author_features]
    within = [distance(author_features[i], author_features[j]) for i in range(len(author_features)) for j in range(i+1, len(author_features))]
    p75 = statistics.quantiles(within, n=4)[2] if len(within) > 1 else (within[0] if within else 0.0)
    print(json.dumps({'median_distance': statistics.median(distances) if distances else 1.0, 'author_p75': p75}))

if __name__ == '__main__':
    main()
