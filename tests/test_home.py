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


# --- home.md writer, corrupt registry ---------------------------------------------------------

def test_write_home_profile_creates_and_upserts_without_dropping(tmp_path):
    h = tmp_path / "home"
    md = h / ".academic-helper" / "home.md"
    home.write_home_profile(h, {"name": "Dana Levi", "role": "student"})
    got = home.read_frontmatter(md.read_text(encoding="utf-8"))
    assert got["name"] == "Dana Levi" and got["role"] == "student"
    md.write_text(md.read_text(encoding="utf-8") + "\n## Tools\n\n```json\n{\"a\": 1}\n```\n", encoding="utf-8")
    home.write_home_profile(h, {"role": "researcher", "institution": "HUJI"})
    text = md.read_text(encoding="utf-8")
    got = home.read_frontmatter(text)
    assert got["name"] == "Dana Levi" and got["role"] == "researcher" and got["institution"] == "HUJI"
    assert home.read_sections(text) == {"tools": {"a": 1}}
    assert not [p for p in (h / ".academic-helper").iterdir() if p.name.endswith(".tmp")]


def test_write_home_profile_keeps_list_keys(tmp_path):
    h = tmp_path / "home"
    md = h / ".academic-helper" / "home.md"
    _md(md, "name: X\nabstractLanguages:\n  - he\n  - en")
    home.write_home_profile(h, {"role": "lecturer"})
    got = home.read_frontmatter(md.read_text(encoding="utf-8"))
    assert got == {"name": "X", "abstractLanguages": ["he", "en"], "role": "lecturer"}


def test_write_home_profile_rejects_bad_role(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        home.write_home_profile(tmp_path / "home", {"role": "teaching"})
    assert not (tmp_path / "home" / ".academic-helper" / "home.md").exists()


def test_cli_set_with_identity_writes_pointer_and_home_md(tmp_path, monkeypatch):
    data, h = tmp_path / "data", tmp_path / "Academic"
    data.mkdir()
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(data))
    monkeypatch.delenv("ACADEMIC_HOME", raising=False)
    assert home._main(["set", "--path", str(h), "--name", "Dana", "--role", "student",
                       "--field", "Philosophy", "--institution", "TAU", "--degree", "MA"]) == 0
    got = home.read_frontmatter((h / ".academic-helper" / "home.md").read_text(encoding="utf-8"))
    assert got["name"] == "Dana" and got["role"] == "student" and got["fieldOfStudy"] == "Philosophy"
    assert got["institution"] == "TAU" and got["degree"] == "MA"
    assert home.home_dir({"CLAUDE_PLUGIN_DATA": str(data)}) == h


def test_cli_set_rejects_teaching_role(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(data))
    assert home._main(["set", "--path", str(tmp_path / "H"), "--role", "teaching"]) == 2
    assert not (tmp_path / "H" / ".academic-helper" / "home.md").exists()


def test_register_on_corrupt_registry_keeps_file_and_fails(tmp_path, capsys, monkeypatch):
    import pytest
    h = tmp_path / "home"
    reg = h / ".academic-helper" / "workspaces.json"
    reg.parent.mkdir(parents=True)
    reg.write_text("{not json", encoding="utf-8")
    ws = tmp_path / "ws"
    ws.mkdir()
    with pytest.raises(home.RegistryError):
        home.register_workspace(h, ws, "project")
    assert reg.read_text(encoding="utf-8") == "{not json"
    assert [p.name for p in reg.parent.iterdir()] == ["workspaces.json"]
    monkeypatch.setenv("ACADEMIC_HOME", str(h))
    assert home._main(["register", "--path", str(ws), "--type", "project"]) == 2
    assert reg.read_text(encoding="utf-8") == "{not json"
    assert "workspaces.json" in capsys.readouterr().out


def test_register_on_non_list_registry_fails_too(tmp_path):
    import pytest
    h = tmp_path / "home"
    reg = h / ".academic-helper" / "workspaces.json"
    reg.parent.mkdir(parents=True)
    reg.write_text('{"a": 1}', encoding="utf-8")
    with pytest.raises(home.RegistryError):
        home.register_workspace(h, tmp_path, "project")
    assert reg.read_text(encoding="utf-8") == '{"a": 1}'
