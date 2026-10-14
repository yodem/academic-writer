"""The product site (site/, published to GitHub Pages) must stay complete and truthful.

Every English string marked for translation has a Hebrew counterpart, every command the site
names is a real skill, every local asset it references exists, and the Pages workflow publishes
the site with the bundled guide at /guide/.
"""
import re
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
INDEX = SITE / "index.html"
HE = SITE / "assets" / "js" / "i18n.he.js"
WORKFLOW = ROOT / ".github" / "workflows" / "pages.yml"


class _Refs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.keys, self.urls = set(), []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        for name in ("data-i18n", "data-i18n-html"):
            if a.get(name):
                self.keys.add(a[name])
        for pair in (a.get("data-i18n-attr") or "").split(";"):
            if ":" in pair:
                self.keys.add(pair.split(":", 1)[1].strip())
        for name in ("src", "href", "poster"):
            if a.get(name):
                self.urls.append(a[name])
        for part in (a.get("srcset") or "").split(","):
            if part.strip():
                self.urls.append(part.split()[0])


def _parse() -> _Refs:
    p = _Refs()
    p.feed(INDEX.read_text(encoding="utf-8"))
    return p


def _he_keys() -> set[str]:
    text = HE.read_text(encoding="utf-8")
    return set(re.findall(r"""^\s*["']?([A-Za-z0-9_.-]+)["']?\s*:""", text, re.M))


def test_every_translatable_string_has_hebrew():
    keys = _parse().keys
    assert len(keys) > 50, "site has suspiciously few translatable strings"
    missing = sorted(keys - _he_keys())
    assert not missing, f"missing Hebrew for: {missing}"


def test_every_named_command_is_a_real_skill():
    text = INDEX.read_text(encoding="utf-8") + HE.read_text(encoding="utf-8")
    named = set(re.findall(r"/academic-writer:([a-z0-9-]+)", text))
    assert named, "site names no commands"
    unknown = sorted(n for n in named if not (ROOT / "src" / "skills" / n / "SKILL.md").is_file())
    assert not unknown, f"site names commands with no skill: {unknown}"


def test_local_assets_exist():
    missing = []
    for url in _parse().urls:
        if re.match(r"^(?:[a-z]+:|//|#)", url) or url.startswith("./guide"):
            continue
        path = (SITE / url.split("#")[0].split("?")[0]).resolve()
        if not path.exists():
            missing.append(url)
    assert not missing, missing


def test_page_contract():
    text = INDEX.read_text(encoding="utf-8")
    css = (SITE / "assets" / "css" / "site.css").read_text(encoding="utf-8")
    assert 'name="viewport"' in text
    assert "prefers-color-scheme: dark" in css
    assert "prefers-reduced-motion" in css
    assert 'href="#main"' in text or "skip" in text.lower()


def test_pages_publishes_site_and_guide():
    wf = WORKFLOW.read_text(encoding="utf-8")
    assert "cp -R site/. _site/" in wf
    assert "cp -R src/guide/. _site/guide/" in wf
    assert "path: _site" in wf
