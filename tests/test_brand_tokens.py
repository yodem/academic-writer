"""The Margin brand file (src/brand/DESIGN.md) and the generated token files."""
from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GEN = ROOT / "scripts" / "gen-brand-tokens.py"
DESIGN = ROOT / "src" / "brand" / "DESIGN.md"
SITE_TOKENS = ROOT / "site" / "assets" / "css" / "margin-tokens.css"
SITE_CSS = ROOT / "site" / "assets" / "css" / "site.css"
FIXTURE = ROOT / "tests" / "fixtures" / "brand" / "site-root-0.17.1.json"


def _load_gen():
    spec = importlib.util.spec_from_file_location("gen_brand_tokens", GEN)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["gen_brand_tokens"] = mod
    spec.loader.exec_module(mod)
    return mod


def _decls(body: str) -> dict:
    out = {}
    for m in re.finditer(r"(--[\w-]+|color-scheme)\s*:\s*(.+?);\s*$", body, re.M):
        out[m.group(1)] = m.group(2)
    return out


def _site_maps(css: str) -> dict:
    """Custom properties of the three theme contexts of a site token CSS text."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    media = re.search(r"@media[^{]*prefers-color-scheme:\s*dark[^{]*\{(.*?)\n\}", css, re.S)
    dark_media = {}
    if media:
        inner = re.search(r":root:not\(\[data-theme=\"light\"\]\)\s*\{(.*?)\n\s*\}", media.group(1), re.S)
        dark_media = _decls(inner.group(1))
        css = css.replace(media.group(0), "")
    attr = re.search(r":root\[data-theme=\"dark\"\]\s*\{(.*?)\n\}", css, re.S)
    dark_attr = _decls(attr.group(1))
    css = css.replace(attr.group(0), "")
    root = {}
    for m in re.finditer(r"(?m)^:root\s*\{(.*?)\n\}", css, re.S):
        root.update(_decls(m.group(1)))
    return {"root": root, "dark_media": dark_media, "dark_attr": dark_attr}


def _lum(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    rgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _ratio(a: str, b: str) -> float:
    la, lb = _lum(a), _lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def test_generated_files_up_to_date():
    res = subprocess.run([sys.executable, str(GEN), "--check"], capture_output=True, text=True)
    assert res.returncode == 0, res.stdout + res.stderr


def test_site_css_unchanged():
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    generated = _site_maps(SITE_TOKENS.read_text(encoding="utf-8"))
    assert generated == fixture
    # the blocks are gone from site.css itself, so nothing can drift or shadow them
    site_css = SITE_CSS.read_text(encoding="utf-8")
    assert "--paper:" not in site_css.split(".lit", 1)[0]


def test_course_hues_contrast():
    gen = _load_gen()
    brand = gen.parse_brand(DESIGN.read_text(encoding="utf-8"))
    colors, dark = brand["colors"], brand["dark"]
    courses = [k for k in colors if k.startswith("course-")]
    assert len(courses) == 8
    for name in courses:
        for bg in ("paper", "sheet"):
            r = _ratio(colors[name], colors[bg])
            assert r >= 4.5, "%s on %s is %.2f:1" % (name, bg, r)
    text_keys = ["ink", "ink-2", "indigo", "verified", "rejected"] + courses
    for name in text_keys:
        r = _ratio(dark[name], dark["paper"])
        assert r >= 5.0, "dark %s on dark paper is %.2f:1" % (name, r)
