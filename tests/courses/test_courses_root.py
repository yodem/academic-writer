import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "scripts" / "courses"))
import courses
import refs


@pytest.fixture
def env(tmp_path, monkeypatch):
    """A clean environment: HOME is a temp dir, no override, no home, no term."""
    fake_home = tmp_path / "userhome"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    for name in ("ACADEMIC_COURSES_DIR", "ACADEMIC_HOME", "ACADEMIC_TERM", "CLAUDE_PLUGIN_DATA"):
        monkeypatch.delenv(name, raising=False)
    return fake_home


def _term(root: Path, name: str = "T1") -> Path:
    d = root / name
    d.mkdir(parents=True)
    (d / "term.json").write_text(json.dumps({"term": name}))
    return d


def test_courses_root_env_override(env, tmp_path, monkeypatch):
    monkeypatch.setenv("ACADEMIC_COURSES_DIR", str(tmp_path / "custom"))
    monkeypatch.setenv("ACADEMIC_HOME", str(tmp_path / "acad"))
    assert courses.courses_root() == tmp_path / "custom"


def test_courses_root_prefers_home_terms(env, tmp_path, monkeypatch):
    acad = tmp_path / "acad"
    _term(acad / ".academic-helper" / "terms")
    _term(env / ".academic-writer" / "courses")
    monkeypatch.setenv("ACADEMIC_HOME", str(acad))
    assert courses.courses_root() == acad / ".academic-helper" / "terms"


def test_courses_root_falls_back_to_legacy(env):
    _term(env / ".academic-writer" / "courses")
    assert courses.courses_root() == env / ".academic-writer" / "courses"


def test_courses_root_legacy_wins_when_home_has_no_terms_yet(env, tmp_path, monkeypatch):
    acad = tmp_path / "acad"
    (acad / ".academic-helper").mkdir(parents=True)
    _term(env / ".academic-writer" / "courses")
    monkeypatch.setenv("ACADEMIC_HOME", str(acad))
    assert courses.courses_root() == env / ".academic-writer" / "courses"


def test_courses_root_new_home_without_anything(env, tmp_path, monkeypatch):
    acad = tmp_path / "acad"
    monkeypatch.setenv("ACADEMIC_HOME", str(acad))
    assert courses.courses_root() == acad / ".academic-helper" / "terms"


def test_courses_root_no_home_no_legacy_keeps_legacy_path(env):
    assert courses.courses_root() == env / ".academic-writer" / "courses"


def test_refs_uses_same_root(env, tmp_path, monkeypatch):
    acad = tmp_path / "acad"
    term = _term(acad / ".academic-helper" / "terms")
    monkeypatch.setenv("ACADEMIC_HOME", str(acad))
    assert refs.registry_dir(None, None) == term == courses.registry_dir(None)
    legacy_only = tmp_path / "other"
    assert refs.registry_dir(legacy_only, None) == legacy_only
    monkeypatch.setenv("ACADEMIC_TERM", "T9")
    assert refs.registry_dir(None, None) == courses.registry_dir(None)


def test_refs_missing_term_still_raises_refs_error(env, tmp_path, monkeypatch):
    root = tmp_path / "acad" / ".academic-helper" / "terms"
    _term(root, "A")
    _term(root, "B")
    monkeypatch.setenv("ACADEMIC_HOME", str(tmp_path / "acad"))
    with pytest.raises(refs.RefsError):
        refs.registry_dir(None, None)
