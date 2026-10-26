#!/usr/bin/env python3
"""Repo-root entry point kept for old invocations: runs the canonical validator in
src/scripts/ (which imports its shared typography library from src/scripts/lib)."""
import runpy
import sys
from pathlib import Path

CANONICAL = Path(__file__).resolve().parent.parent / "src" / "scripts" / "validate-hebrew-punctuation.py"
sys.argv[0] = str(CANONICAL)
sys.path.insert(0, str(CANONICAL.parent))
runpy.run_path(str(CANONICAL), run_name="__main__")
