"""The product site (site/, published to GitHub Pages) must stay complete and truthful.

Every English string marked for translation has a Hebrew counterpart, every command the site
names is a real skill, every local asset it references exists, and the Pages workflow publishes
the site with the bundled guide at /guide/.
"""
import re
import subprocess
import sys
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


def test_dashboard_section_follows_courses_and_is_linked():
    html = INDEX.read_text(encoding="utf-8")
    assert '<section class="sec dash" id="dashboard"' in html
    assert html.index('id="courses"') < html.index('id="dashboard"') < html.index('id="film"')
    assert 'href="#dashboard"' in html
    for img in ("dashboard-overview-light", "dashboard-overview-dark", "activity-pane"):
        assert (SITE / "assets" / "img" / (img + ".webp")).exists()


def _changelog_versions() -> list[str]:
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    return re.findall(r"^## \[(\d+\.\d+\.\d+)\]", text, re.M)


def test_hero_says_claude_code_plugin():
    html = INDEX.read_text(encoding="utf-8")
    hero = html[html.index('id="top"'):html.index("<!-- FILM -->")]
    assert "Claude Code plugin" in hero
    assert "Claude Code plugin" in html[html.index("<title>"):html.index("</title>")]
    he = HE.read_text(encoding="utf-8")
    assert re.search(r'hero_kicker:\s*"[^"]*Claude Code', he)
    assert re.search(r'r3c_hero_sub:\s*"ב-Claude Code', he)


def test_news_block_exists_and_is_current():
    html = INDEX.read_text(encoding="utf-8")
    assert "<!-- news:start -->" in html and "<!-- news:end -->" in html
    assert 'id="news"' in html and 'data-i18n="news_h"' in html
    assert {"news_h", "news_sub", "news_all", "nav_news"} <= _he_keys()
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "gen-site-news.py"), "--check"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_news_lists_newest_released_version_first():
    html = INDEX.read_text(encoding="utf-8")
    block = html[html.index("<!-- news:start -->"):html.index("<!-- news:end -->")]
    shown = re.findall(r'class="news__ver">v(\d+\.\d+\.\d+)<', block)
    released = _changelog_versions()
    assert shown and shown[0] == released[0]
    assert shown == released[:3]
    assert "Unreleased" not in block
