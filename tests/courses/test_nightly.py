import importlib.util
import json
import os
import plistlib
import subprocess
import sys
from pathlib import Path

import pytest

COURSES_DIR = Path(__file__).resolve().parents[2] / "src" / "scripts" / "courses"
sys.path.insert(0, str(COURSES_DIR))
import nightly  # noqa: E402

LABEL = "com.academic-writer.courses-daily"


@pytest.fixture
def env(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("ACADEMIC_HOME", str(home / "Academic"))
    monkeypatch.delenv("ACADEMIC_TERM", raising=False)
    monkeypatch.delenv("COURSES_TERM_DIR", raising=False)
    agents = tmp_path / "LaunchAgents"
    agents.mkdir()
    script = tmp_path / "bin" / "courses-daily.sh"
    script.parent.mkdir()
    script.write_text('#!/bin/bash\necho "dry=${COURSES_DRY:-}"\nexit "${STUB_EXIT:-0}"\n')
    launchctl = tmp_path / "launchctl"
    log = tmp_path / "launchctl.log"
    launchctl.write_text('#!/bin/sh\necho "$@" >> "%s"\nexit "${STUB_LAUNCHCTL_EXIT:-0}"\n' % log)
    launchctl.chmod(0o755)
    return {"agents": agents, "script": script, "launchctl": launchctl, "log": log, "home": home, "tmp": tmp_path}


def call(env, sub, *extra, platform="darwin", shared=True):
    args = ["nightly", sub]
    if shared:
        args += ["--launch-agents-dir", str(env["agents"]), "--launchctl", str(env["launchctl"]), "--platform", platform]
    args += list(extra)
    import argparse
    parser = argparse.ArgumentParser()
    nightly.add_parser(parser.add_subparsers(dest="command"))
    return nightly.run(parser.parse_args(args))


def launchctl_calls(env):
    return env["log"].read_text().splitlines() if env["log"].exists() else []


def plists(env):
    return sorted(p.name for p in env["agents"].iterdir())


def test_set_writes_valid_plist_and_loads(env, capsys):
    rc = call(env, "set", "--time", "03:30", "--script", str(env["script"]))
    assert rc == 0
    path = env["agents"] / (LABEL + ".plist")
    data = plistlib.loads(path.read_bytes())
    assert data["Label"] == LABEL
    assert data["ProgramArguments"][-1] == str(env["script"])
    assert data["StartCalendarInterval"] == {"Hour": 3, "Minute": 30}
    assert data["RunAtLoad"] is False
    assert data["EnvironmentVariables"]["ACADEMIC_HOME"] == str(env["home"] / "Academic")
    assert data["StandardOutPath"] == data["StandardErrorPath"]
    assert data["StandardOutPath"].endswith("launchd.log")
    assert Path(data["StandardOutPath"]).parent.is_dir()
    calls = launchctl_calls(env)
    assert [c.split()[0] for c in calls] == ["bootout", "bootstrap"]
    assert LABEL in calls[0] and str(path) in calls[1]
    assert "03:30" in capsys.readouterr().out


def test_bootout_failure_is_ignored(env, monkeypatch):
    monkeypatch.setenv("STUB_LAUNCHCTL_EXIT", "3")
    assert call(env, "set", "--time", "04:00", "--script", str(env["script"])) == 0
    assert (env["agents"] / (LABEL + ".plist")).exists()


def test_no_load_skips_launchctl(env):
    assert call(env, "set", "--time", "04:00", "--script", str(env["script"]), "--no-load") == 0
    assert launchctl_calls(env) == []


def test_reset_updates_in_place_with_backup_and_same_label(env):
    legacy = env["agents"] / "com.example.academic-courses-daily.plist"
    legacy.write_bytes(plistlib.dumps({"Label": "com.example.academic-courses-daily",
                                       "ProgramArguments": ["/bin/bash", str(env["script"])],
                                       "StartCalendarInterval": {"Hour": 2, "Minute": 0}}))
    assert call(env, "set", "--time", "05:15") == 0
    names = plists(env)
    baks = [n for n in names if ".plist.bak-" in n]
    assert len(baks) == 1 and not baks[0].endswith(".plist")
    assert "com.example.academic-courses-daily.plist" in names
    assert LABEL + ".plist" not in names
    data = plistlib.loads(legacy.read_bytes())
    assert data["Label"] == "com.example.academic-courses-daily"
    assert data["StartCalendarInterval"] == {"Hour": 5, "Minute": 15}
    backup = plistlib.loads((env["agents"] / baks[0]).read_bytes())
    assert backup["StartCalendarInterval"] == {"Hour": 2, "Minute": 0}
    assert any("com.example.academic-courses-daily" in c for c in launchctl_calls(env))


@pytest.mark.parametrize("bad", ["25:00", "3:5x", "12:60", "", "noon", "07"])
def test_bad_time_exits_2_and_writes_nothing(env, bad, capsys):
    assert call(env, "set", "--time", bad, "--script", str(env["script"])) == 2
    assert plists(env) == [] and launchctl_calls(env) == []
    assert "HH:MM" in capsys.readouterr().err


def test_missing_script_exits_2_and_points_at_example(env, capsys):
    missing = env["tmp"] / "nope.sh"
    assert call(env, "set", "--time", "03:00", "--script", str(missing)) == 2
    assert plists(env) == [] and launchctl_calls(env) == []
    assert "courses-daily.sh.example" in capsys.readouterr().err


def test_default_script_missing_exits_2(env, capsys):
    assert call(env, "set", "--time", "03:00") == 2
    assert plists(env) == []
    assert "courses-daily.sh.example" in capsys.readouterr().err


def test_off_disables_and_set_revives(env, capsys):
    call(env, "set", "--time", "03:30", "--script", str(env["script"]))
    env["log"].unlink()
    assert call(env, "off") == 0
    assert plists(env) == [LABEL + ".plist.disabled"]
    assert [c.split()[0] for c in launchctl_calls(env)] == ["bootout"]
    assert "run-now" in capsys.readouterr().out
    capsys.readouterr()
    assert call(env, "status", "--json") == 0
    st = json.loads(capsys.readouterr().out)
    assert st["scheduled"] is False and st["label"] == LABEL
    assert call(env, "set", "--time", "06:45") == 0
    assert plists(env) == [LABEL + ".plist"]
    assert plistlib.loads((env["agents"] / (LABEL + ".plist")).read_bytes())["StartCalendarInterval"] == {"Hour": 6, "Minute": 45}


def test_off_without_plist_is_ok(env, capsys):
    assert call(env, "off") == 0
    assert "run-now" in capsys.readouterr().out


def test_status_json(env, capsys):
    assert call(env, "status", "--json") == 0
    st = json.loads(capsys.readouterr().out)
    assert st == {"scheduled": False, "time": None, "plist": None, "script": None, "label": None, "last_run": None}
    call(env, "set", "--time", "03:30", "--script", str(env["script"]))
    capsys.readouterr()
    call(env, "status", "--json")
    st = json.loads(capsys.readouterr().out)
    assert st["scheduled"] is True and st["time"] == "03:30" and st["label"] == LABEL
    assert st["script"] == str(env["script"]) and st["plist"].endswith(LABEL + ".plist")
    assert set(st) == {"scheduled", "time", "plist", "script", "label", "last_run"}


def test_status_last_run_from_log(env, capsys):
    term = env["home"] / "Academic" / ".academic-helper" / "terms" / "t1"
    # registry location is resolved by courses.registry_dir; seed it through the same function
    sys.path.insert(0, str(COURSES_DIR))
    import courses
    root = courses.courses_root()
    d = root / "t1"
    (d / "logs").mkdir(parents=True)
    (d / "term.json").write_text(json.dumps({"term": "t1"}))
    (d / "logs" / "daily-2026-10-17.log").write_text("x\n== done 2026-10-17T03:31:02+0300\n")
    assert call(env, "status", "--json") == 0
    st = json.loads(capsys.readouterr().out)
    assert st["last_run"].startswith("2026-10-17T03:31:02")


def test_status_text(env, capsys):
    call(env, "status")
    assert "runs on demand" in capsys.readouterr().out


def test_run_now_returns_exit_code_and_dry_env(env, capfd, monkeypatch):
    assert call(env, "run-now", "--script", str(env["script"]), shared=False) == 0
    assert "dry=" in capfd.readouterr().out
    assert "dry=1" not in env["script"].read_text()
    assert call(env, "run-now", "--dry", "--script", str(env["script"]), shared=False) == 0
    assert "dry=1" in capfd.readouterr().out
    monkeypatch.setenv("STUB_EXIT", "7")
    assert call(env, "run-now", "--script", str(env["script"]), shared=False) == 7


def test_run_now_uses_plist_script(env, capfd):
    call(env, "set", "--time", "03:30", "--script", str(env["script"]))
    capfd.readouterr()
    assert call(env, "run-now", "--dry") == 0
    assert "dry=1" in capfd.readouterr().out


def test_run_now_missing_script_exits_2(env):
    assert call(env, "run-now", "--script", str(env["tmp"] / "nope.sh"), shared=False) == 2


def test_linux_prints_cron_line_and_writes_nothing(env, capsys):
    assert call(env, "set", "--time", "03:30", "--script", str(env["script"]), platform="linux") == 0
    out = capsys.readouterr().out
    assert "30 3 * * * bash %s" % env["script"] in out
    assert plists(env) == [] and launchctl_calls(env) == []


def test_set_via_courses_cli(env):
    out = subprocess.run([sys.executable, str(COURSES_DIR / "courses.py"), "nightly", "set", "--time", "03:30",
                          "--script", str(env["script"]), "--launch-agents-dir", str(env["agents"]),
                          "--launchctl", str(env["launchctl"]), "--platform", "darwin"],
                         capture_output=True, text=True, env={**os.environ, "HOME": str(env["home"])})
    assert out.returncode == 0, out.stderr
    assert (env["agents"] / (LABEL + ".plist")).exists()


def test_setup_checks_still_sees_the_plist(env):
    call(env, "set", "--time", "03:30", "--script", str(env["script"]), "--label", "com.example.academic-nightly")
    spec = importlib.util.spec_from_file_location("setup_checks_t", COURSES_DIR.parent / "setup_checks.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["setup_checks_t"] = mod
    spec.loader.exec_module(mod)
    agents = env["home"] / "Library" / "LaunchAgents"
    agents.mkdir(parents=True)
    (agents / "com.example.academic-nightly.plist").write_bytes((env["agents"] / "com.example.academic-nightly.plist").read_bytes())
    check = mod._nightly({"HOME": str(env["home"])}, "darwin", None)
    assert check["ok"] is True


def test_run_now_passes_plist_environment(env, capfd, monkeypatch):
    env["script"].write_text('#!/bin/bash\necho "home=${ACADEMIC_HOME:-}"\n')
    call(env, "set", "--time", "03:30", "--script", str(env["script"]))
    capfd.readouterr()
    monkeypatch.delenv("ACADEMIC_HOME")
    assert call(env, "run-now") == 0
    assert "home=%s" % (env["home"] / "Academic") in capfd.readouterr().out
