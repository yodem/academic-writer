import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "scripts"))
import home  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "profile"


def _md(path: Path, front: str, body: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("---\n" + front + "\n---\n\n" + body, encoding="utf-8")


def test_env_beats_pointer(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "home.json").write_text(json.dumps({"path": "/b"}))
    assert home.home_dir({"ACADEMIC_HOME": "/a", "CLAUDE_PLUGIN_DATA": str(data)}) == Path("/a")
    assert home.home_dir({"CLAUDE_PLUGIN_DATA": str(data)}) == Path("/b")


def test_no_home_returns_none(tmp_path):
    assert home.home_dir({}) is None
    assert home.home_dir({"CLAUDE_PLUGIN_DATA": str(tmp_path)}) is None
    (tmp_path / "home.json").write_text("{not json")
    assert home.home_dir({"CLAUDE_PLUGIN_DATA": str(tmp_path)}) is None


def test_set_home_writes_pointer_and_only_the_helper_dir(tmp_path):
    h, data = tmp_path / "Academic", tmp_path / "data"
    home.set_home(h, data)
    assert home.home_dir({"CLAUDE_PLUGIN_DATA": str(data)}) == h
    assert sorted(p.name for p in h.iterdir()) == [".academic-helper"]


def test_workspace_overrides_home(tmp_path):
    h, ws = tmp_path / "home", tmp_path / "ws"
    _md(h / ".academic-helper" / "home.md", "name: X\ncitationStyle: chicago",
        '## Sources\n\n```json\n[{"id": "home"}]\n```\n\n## Tools\n\n```json\n{"a": 1}\n```\n')
    _md(ws / ".academic-helper" / "profile.md", "citationStyle: apa\nworkspace: course\ncourse: cohen\nterm: T1",
        '## Sources\n\n```json\n[{"id": "ws"}]\n```\n')
    r = home.resolve_profile(ws, {"ACADEMIC_HOME": str(h)})
    assert r.values["citationStyle"] == "apa"
    assert r.values["name"] == "X"
    assert r.sections["sources"] == [{"id": "ws"}]
    assert r.sections["tools"] == {"a": 1}
    assert (r.workspace_type, r.course, r.term) == ("course", "cohen", "T1")
    assert r.home == h and r.home_missing is False


def test_home_missing_flagged(tmp_path):
    ws = tmp_path / "ws"
    _md(ws / ".academic-helper" / "profile.md", "citationStyle: apa")
    r = home.resolve_profile(ws, {"ACADEMIC_HOME": str(tmp_path / "gone")})
    assert r.home_missing is True
    assert r.values["citationStyle"] == "apa"


def test_missing_workspace_kept_and_flagged(tmp_path):
    h, ws = tmp_path / "home", tmp_path / "ws"
    (h / ".academic-helper").mkdir(parents=True)
    ws.mkdir()
    home.register_workspace(h, ws, "project", None, None)
    assert home.list_workspaces(h)[0]["exists"] is True
    shutil.rmtree(ws)
    rows = home.list_workspaces(h)
    assert len(rows) == 1 and rows[0]["exists"] is False
    assert json.loads((h / ".academic-helper" / "workspaces.json").read_text())[0]["path"] == str(ws.resolve())


def test_register_is_upsert(tmp_path):
    h, ws = tmp_path / "home", tmp_path / "ws"
    ws.mkdir()
    home.register_workspace(h, ws, "project")
    home.register_workspace(h, ws, "course", "cohen", "T1")
    rows = home.list_workspaces(h)
    assert len(rows) == 1
    assert (rows[0]["type"], rows[0]["course"], rows[0]["term"]) == ("course", "cohen", "T1")


def test_frontmatter_matches_ts_parser():
    text = (FIXTURES / "sample-profile.md").read_text(encoding="utf-8")
    expected = json.loads((FIXTURES / "sample-profile.expected.json").read_text(encoding="utf-8"))
    assert home.read_frontmatter(text) == expected["frontmatter"]
    assert home.read_sections(text) == expected["sections"]
