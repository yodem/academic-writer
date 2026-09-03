"""Tests for voice-sync.sh utility."""

import subprocess
from pathlib import Path
import os, shutil, tempfile

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "src" / "skills" / "voice" / "voice-sync.sh"

# The handful of real binaries voice-sync.sh actually shells out to for the
# `status` action (author_key resolution via grep/sed/tr, plus cat for the
# cached-id branch). Deliberately NOT including `ck` itself here -- that is
# the one thing each test below controls explicitly, by either omitting it
# or stubbing it, so the "ck present" vs "ck absent" branch is a function of
# the test setup rather than of what happens to be installed on the machine
# running the suite.
_REQUIRED_BINS = ("grep", "sed", "tr", "cat")


def _isolated_bin_dir(tmp_path, name, include_ck_stub=False):
    """Build a directory holding only the real binaries voice-sync.sh needs
    (symlinked in from the host), plus optionally an executable `ck` stub.

    Using this as the *entire* PATH makes `command -v ck` succeed or fail
    deterministically, regardless of whether a real `ck` CLI happens to be
    installed on the machine running the tests.
    """
    bin_dir = tmp_path / name
    bin_dir.mkdir()
    for bin_name in _REQUIRED_BINS:
        real = shutil.which(bin_name)
        assert real, f"required binary {bin_name!r} not found on host PATH"
        (bin_dir / bin_name).symlink_to(real)
    if include_ck_stub:
        stub = bin_dir / "ck"
        # voice-sync.sh's `status` action only ever probes `ck` via
        # `command -v ck` -- it never actually invokes it (ensure_id, which
        # calls `ck books list`, is only reached from pull/push). So a stub
        # that merely exists and is executable is sufficient to force the
        # ck-present branch for `status`.
        stub.write_text("#!/bin/sh\nexit 0\n")
        stub.chmod(0o755)
    return str(bin_dir)


def test_script_exists_and_executable():
    assert SCRIPT.is_file()
    assert os.access(SCRIPT, os.X_OK)


def _write_profile_with_author_key(tmp_path, author_key="test-writer"):
    profile_dir = tmp_path / ".academic-helper"
    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / "profile.md").write_text(
        f"# Academic Writer Profile\n\n---\nauthor_key: {author_key}\n---\n"
    )


def test_no_op_when_ck_missing(tmp_path):
    env = os.environ.copy()
    # Deterministically force ck-missing: PATH points ONLY at a directory
    # holding the real grep/sed/tr/cat binaries voice-sync.sh needs, with no
    # `ck` anywhere on it -- independent of whether `ck` is installed on the
    # machine running the suite.
    env["PATH"] = _isolated_bin_dir(tmp_path, "bin-no-ck", include_ck_stub=False)
    env["VOICE_PROJECT_ROOT"] = str(tmp_path)
    (tmp_path / "AUTHOR_VOICE.md").write_text("# stub\n")
    _write_profile_with_author_key(tmp_path)
    r = subprocess.run([str(SCRIPT), "push"], env=env, capture_output=True, text=True)
    assert r.returncode == 0
    assert "ck not available" in (r.stdout + r.stderr).lower()


def test_status_reports_ck_not_available_when_ck_absent(tmp_path):
    """`status` with no `ck` on PATH: deterministically forces the
    ck-absent branch (voice-sync.sh checks `command -v ck` before it ever
    reaches the `status` case arm) and asserts the local-only-mode message
    and a clean exit -- regardless of the host machine's PATH.
    """
    env = os.environ.copy()
    env["PATH"] = _isolated_bin_dir(tmp_path, "bin-no-ck", include_ck_stub=False)
    env["VOICE_PROJECT_ROOT"] = str(tmp_path)
    (tmp_path / ".voice").mkdir()
    _write_profile_with_author_key(tmp_path)
    r = subprocess.run([str(SCRIPT), "status"], env=env, capture_output=True, text=True)
    assert r.returncode == 0
    out = (r.stdout + r.stderr).lower()
    assert "ck not available" in out
    assert "local-only mode" in out


def test_status_reports_no_id_cache_when_ck_present(tmp_path):
    """`status` with `ck` on PATH and no cached id file: deterministically
    forces the ck-present branch via a stub `ck` executable (never actually
    invoked by `status` -- see _isolated_bin_dir) so the "no cached
    candlekeep id" message is reached on every machine, with or without a
    real `ck` CLI installed.
    """
    env = os.environ.copy()
    env["PATH"] = _isolated_bin_dir(tmp_path, "bin-with-ck", include_ck_stub=True)
    env["VOICE_PROJECT_ROOT"] = str(tmp_path)
    (tmp_path / ".voice").mkdir()
    _write_profile_with_author_key(tmp_path)
    r = subprocess.run([str(SCRIPT), "status"], env=env, capture_output=True, text=True)
    assert r.returncode == 0
    assert "no cached candlekeep id" in (r.stdout + r.stderr).lower()


def test_fails_loudly_when_author_key_missing(tmp_path):
    env = os.environ.copy()
    env["VOICE_PROJECT_ROOT"] = str(tmp_path)
    # No .academic-helper/profile.md, no book.yaml, no VOICE_WRITER_NAME override.
    r = subprocess.run([str(SCRIPT), "status"], env=env, capture_output=True, text=True)
    assert r.returncode == 1
    assert "author_key not found" in (r.stdout + r.stderr).lower()
    assert "<unknown>" not in (r.stdout + r.stderr).lower()


# --- ck CLI contract ---------------------------------------------------------
# voice-sync.sh used to call `ck books list|read|create|update`. There is no
# `ck books` subcommand (`ck books --help` -> "unrecognized subcommand"), and
# every call was wrapped in `2>/dev/null || echo "...local-only mode"`, so the
# failure was reported as a missing CandleKeep install on a machine where ck
# was installed and authenticated. These tests pin the real `ck items` surface
# and pin that real errors are surfaced instead of swallowed.

_CK_STUB = r"""#!/bin/bash
# Fake `ck` implementing just enough of the real `ck items` surface.
log="$CK_STUB_LOG"
echo "$*" >> "$log"
if [[ "$1" == "items" && "$2" == "--help" ]]; then exit 0; fi
if [[ "$1" != "items" ]]; then
  echo "error: unrecognized subcommand '$1'" >&2
  exit 2
fi
case "$2" in
  list)
    echo '{"items":[{"id":"ITEM123","title":"Voice Profile — test-writer"}]}'
    ;;
  get)
    printf '# remote\n\n> Updated 2999-01-01\n\nremote body\n'
    ;;
  import)
    echo '{"id":"NEWITEM456"}'
    ;;
  put)
    echo '{"ok":true}'
    ;;
  *)
    echo "error: unrecognized subcommand '$2'" >&2
    exit 2
    ;;
esac
"""

_CK_BROKEN = """#!/bin/bash
if [[ "$1" == "items" && "$2" == "--help" ]]; then exit 0; fi
echo "Error: Not found: Item not found" >&2
exit 1
"""


def _bin_with_ck(tmp_path, name, body):
    bin_dir = tmp_path / name
    bin_dir.mkdir()
    for bin_name in _REQUIRED_BINS + ("bash", "python3", "mktemp", "rm", "mkdir", "printf", "mv"):
        real = shutil.which(bin_name)
        if real and not (bin_dir / bin_name).exists():
            (bin_dir / bin_name).symlink_to(real)
    stub = bin_dir / "ck"
    stub.write_text(body)
    stub.chmod(0o755)
    return str(bin_dir)


def _env_for(tmp_path, bin_dir, log=None):
    env = os.environ.copy()
    env["PATH"] = bin_dir + ":" + env["PATH"]
    env["VOICE_PROJECT_ROOT"] = str(tmp_path)
    if log:
        env["CK_STUB_LOG"] = str(log)
    return env


def test_push_uses_ck_items_not_ck_books(tmp_path):
    """The whole point: no `ck books` call may survive, and an existing
    "Voice Profile — <author_key>" book must be bound by title rather than
    duplicated."""
    log = tmp_path / "ck.log"
    env = _env_for(tmp_path, _bin_with_ck(tmp_path, "bin-ck", _CK_STUB), log)
    (tmp_path / "AUTHOR_VOICE.md").write_text("# local\n\n> Updated 2026-01-01\n")
    _write_profile_with_author_key(tmp_path)

    r = subprocess.run([str(SCRIPT), "push"], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    calls = log.read_text()
    assert "books" not in calls, f"ck books call survived: {calls}"
    assert "items list --json" in calls
    # Bound to the existing item by title -> update, not a duplicate import.
    assert "items put ITEM123" in calls
    assert "import" not in calls
    assert "ITEM123" in (tmp_path / ".voice" / ".candlekeep-id").read_text()


def test_push_creates_via_items_import_when_no_remote(tmp_path):
    log = tmp_path / "ck.log"
    stub = _CK_STUB.replace('{"items":[{"id":"ITEM123","title":"Voice Profile — test-writer"}]}',
                            '{"items":[]}')
    env = _env_for(tmp_path, _bin_with_ck(tmp_path, "bin-ck", stub), log)
    (tmp_path / "AUTHOR_VOICE.md").write_text("# local\n")
    _write_profile_with_author_key(tmp_path)

    r = subprocess.run([str(SCRIPT), "push"], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    calls = log.read_text()
    assert "items import" in calls
    assert "--title" in calls
    assert (tmp_path / ".voice" / ".candlekeep-id").read_text().strip() == "NEWITEM456"


def test_pull_reads_via_items_get(tmp_path):
    log = tmp_path / "ck.log"
    env = _env_for(tmp_path, _bin_with_ck(tmp_path, "bin-ck", _CK_STUB), log)
    (tmp_path / "AUTHOR_VOICE.md").write_text("# local\n\n> Updated 2000-01-01\n")
    _write_profile_with_author_key(tmp_path)

    r = subprocess.run([str(SCRIPT), "pull"], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "items get ITEM123" in log.read_text()
    assert "remote body" in (tmp_path / "AUTHOR_VOICE.md").read_text()


def test_real_ck_error_is_surfaced_not_reported_as_local_only(tmp_path):
    """A working `ck` that returns an error must NOT be reported as an absent
    or unsupported CandleKeep — that sends the user to debug their install."""
    env = _env_for(tmp_path, _bin_with_ck(tmp_path, "bin-broken-ck", _CK_BROKEN))
    (tmp_path / "AUTHOR_VOICE.md").write_text("# local\n")
    _write_profile_with_author_key(tmp_path)

    r = subprocess.run([str(SCRIPT), "push"], env=env, capture_output=True, text=True)
    combined = r.stdout + r.stderr
    assert r.returncode != 0, combined
    assert "Item not found" in combined, combined
    assert "local-only mode" not in combined, combined
