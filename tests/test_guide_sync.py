"""The HTML guide and the help skill must stay in sync with the skills and the manifest.

scripts/gen-guide.py regenerates both command lists from skill frontmatter at build time; these
tests fail when someone adds a skill, changes a summary or bumps the version without regenerating.
"""
import html
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
GEN = ROOT / "scripts" / "gen-guide.py"
GUIDE = ROOT / "src" / "guide" / "index.html"
HELP = ROOT / "src" / "skills" / "help" / "SKILL.md"
INTRO = ROOT / "src" / "skills" / "intro" / "SKILL.md"
MANIFEST = ROOT / "manifests" / "academic-writer.json"


def _fm(path: Path) -> dict:
    m = re.match(r"---\n(.*?)\n---\n", path.read_text(encoding="utf-8"), re.S)
    return yaml.safe_load(m.group(1)) if m else {}


def _user_invocable(root: Path = ROOT) -> list[str]:
    return sorted(
        str(_fm(p).get("name") or p.parent.name)
        for p in (root / "src" / "skills").glob("*/SKILL.md")
        if _fm(p).get("user-invocable") is True
    )


def _between(text: str, start: str, end: str) -> str:
    m = re.search(re.escape(start) + r"(.*?)" + re.escape(end), text, re.S)
    assert m, f"markers {start} / {end} missing"
    return m.group(1)


def _run_check(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(GEN), "--check", "--root", str(root)],
                          capture_output=True, text=True)


def test_gen_guide_check_passes():
    r = _run_check(ROOT)
    assert r.returncode == 0, r.stderr


def test_every_user_invocable_skill_in_guide_and_help():
    guide = _between(GUIDE.read_text(encoding="utf-8"),
                     "<!-- guide:commands:start -->", "<!-- guide:commands:end -->")
    helptext = _between(HELP.read_text(encoding="utf-8"),
                        "<!-- help:commands:start -->", "<!-- help:commands:end -->")
    names = _user_invocable()
    assert "intro" in names and "help" in names
    for name in names:
        slash = f"/academic-writer:{name}"
        assert f"<code>{html.escape(slash)}</code>" in guide, f"guide missing {slash}"
        assert f"`{slash}`" in helptext, f"help missing {slash}"
    # And nothing internal leaks into the lists.
    listed = set(re.findall(r"/academic-writer:([a-z0-9-]+)", guide))
    assert listed == set(names), listed ^ set(names)


def test_version_stamp_matches_manifest():
    version = json.loads(MANIFEST.read_text(encoding="utf-8"))["version"]
    stamp = _between(GUIDE.read_text(encoding="utf-8"),
                     "<!-- guide:version:start -->", "<!-- guide:version:end -->")
    assert stamp.strip() == version


def test_guide_is_self_contained():
    text = GUIDE.read_text(encoding="utf-8")
    # Plain <a href="http..."> links are fine: they only open when clicked.
    stripped = re.sub(r"<a\s[^>]*?href\s*=\s*\"https?://[^\"]*\"", "<a", text, flags=re.I)
    offenders = re.findall(
        r"(?:src|href|action|poster|data)\s*=\s*[\"']?\s*(?:https?:)?//"
        r"|url\(\s*[\"']?\s*(?:https?:)?//"
        r"|@import"
        r"|\bfetch\s*\("
        r"|XMLHttpRequest"
        r"|new\s+WebSocket"
        r"|<link\b[^>]*rel\s*=\s*[\"']?stylesheet",
        stripped, flags=re.I)
    assert not offenders, offenders
    assert "prefers-color-scheme: dark" in text
    assert 'name="viewport"' in text
    assert 'dir="rtl"' in text


def test_help_is_short_and_points_to_intro():
    fm = _fm(HELP)
    body = HELP.read_text(encoding="utf-8")
    assert len(body.splitlines()) < 150
    assert fm.get("model") == "haiku"
    assert "/academic-writer:intro" in body
    assert "Use when" in fm["description"]


def test_intro_opener_covers_three_platforms():
    fm = _fm(INTRO)
    body = INTRO.read_text(encoding="utf-8")
    assert fm.get("user-invocable") is True
    assert fm.get("disable-model-invocation") is False
    assert "Use when the user asks how the plugin works" in fm["description"]
    assert "${CLAUDE_PLUGIN_ROOT}/guide/index.html" in body
    platforms = {
        "macos": re.search(r"^\s*open \"\$GUIDE\"", body, re.M),
        "linux": "xdg-open" in body,
        "windows": ('start ""' in body) or ("Start-Process" in body),
    }
    assert sum(bool(v) for v in platforms.values()) >= 3, platforms
    assert "NOT_OPENED" in body and "double-click" in body


def test_intro_opener_script_runs_with_stubbed_opener():
    """Run the skill's bash block with a fake `open`/`xdg-open` so no browser launches."""
    body = INTRO.read_text(encoding="utf-8")
    script = re.search(r"```bash\n(.*?)```", body, re.S).group(1)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "plugin root" / "guide").mkdir(parents=True)
        (tmp / "plugin root" / "guide" / "index.html").write_text("<html></html>")
        bindir = tmp / "bin"
        bindir.mkdir()
        for name in ("open", "xdg-open"):
            stub = bindir / name
            stub.write_text(f"#!/bin/sh\necho \"$1\" > \"{tmp}/opened\"\n")
            stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
        script = script.replace("${CLAUDE_PLUGIN_ROOT}", str(tmp / "plugin root"))
        env = dict(os.environ, PATH=f"{bindir}:{os.environ['PATH']}")
        r = subprocess.run(["bash", "-c", script], capture_output=True, text=True, env=env)
        assert r.returncode == 0, r.stderr
        if sys.platform in ("darwin", "linux"):
            assert r.stdout.startswith("OPENED"), r.stdout
            assert (tmp / "opened").read_text().strip().endswith("guide/index.html")


def _copy_tree(dst: Path) -> None:
    shutil.copytree(ROOT / "src" / "skills", dst / "src" / "skills")
    shutil.copytree(ROOT / "src" / "guide", dst / "src" / "guide")
    (dst / "manifests").mkdir()
    shutil.copy(MANIFEST, dst / "manifests" / MANIFEST.name)


def test_check_fails_when_a_new_skill_is_added():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        _copy_tree(tmp)
        assert _run_check(tmp).returncode == 0
        new = tmp / "src" / "skills" / "zz-new" / "SKILL.md"
        new.parent.mkdir()
        new.write_text('---\nname: zz-new\ndescription: "Does a new thing. Use when testing."\n'
                       'user-invocable: true\n---\n\n# New\n', encoding="utf-8")
        r = _run_check(tmp)
        assert r.returncode == 1
        assert "stale" in r.stderr
        # Regenerating fixes it and is idempotent.
        subprocess.run([sys.executable, str(GEN), "--root", str(tmp)], check=True, capture_output=True)
        assert "/academic-writer:zz-new" in (tmp / "src/guide/index.html").read_text(encoding="utf-8")
        assert "/academic-writer:zz-new" in (tmp / "src/skills/help/SKILL.md").read_text(encoding="utf-8")
        assert _run_check(tmp).returncode == 0


def test_check_fails_when_version_bumps():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        _copy_tree(tmp)
        m = tmp / "manifests" / MANIFEST.name
        data = json.loads(m.read_text(encoding="utf-8"))
        data["version"] = "99.0.0"
        m.write_text(json.dumps(data), encoding="utf-8")
        assert _run_check(tmp).returncode == 1


def test_build_runs_generator_and_ships_guide():
    build = (ROOT / "scripts" / "build-plugins.sh").read_text(encoding="utf-8")
    assert 'python3 "$PROJECT_ROOT/scripts/gen-guide.py"' in build
    assert 'cp -R "$SRC_DIR/guide" "$PLUGIN_DIR/"' in build
    assert build.index("gen-guide.py") < build.index('cp -R "$SRC_DIR/skills"')
