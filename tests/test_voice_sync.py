from pathlib import Path
import os

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "src" / "skills" / "voice" / "voice-sync.sh"

def test_sync_wrapper_exists_and_is_executable():
    assert SCRIPT.is_file()
    assert os.access(SCRIPT, os.X_OK)

def test_sync_wrapper_passes_explicit_plugin_and_project_paths():
    text = SCRIPT.read_text()
    assert '--data-dir "$data_dir"' in text
    assert '--project-dir "$project_dir"' in text
    assert 'voice "$action"' in text
    # Explicit args win; legacy one-arg callers fall back to the documented data dir (runtime-facts.md).
    assert 'data_dir=${2:-' in text and 'plugins/data/academic-writer-academic-writer' in text
