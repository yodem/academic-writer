#!/usr/bin/env python3
"""Deterministic setup checks: one source for /academic-writer:setup health, setup and the dashboard's Setup page.

Read-only: no installs, no writes, no model calls. The Gemini key is only tested for presence and its value
is never read into any output.

Usage:
  python3 setup_checks.py [--json]
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

MIN_PYTHON = (3, 9)
MIN_NODE = 20
SETUP_FIX = "/academic-writer:setup"
ADDONS = {"python-docx": "docx", "lxml": "lxml", "pdfplumber": "pdfplumber",
          "pymupdf": "fitz", "jsonschema": "jsonschema"}

_PROBE = (
    "import importlib\n"
    "mods = %r\n"
    "missing = []\n"
    "for pkg, mod in mods.items():\n"
    "    try:\n"
    "        importlib.import_module(mod)\n"
    "    except ImportError:\n"
    "        missing.append(pkg)\n"
    "print('MISSING:' + ','.join(missing) if missing else 'ALL_PRESENT')\n"
) % (ADDONS,)

Check = Dict[str, Any]

PIP_ADDONS = "-m pip install --user python-docx lxml pdfplumber pymupdf jsonschema"

# One Windows line and one Mac line for every row (plain words; the Windows lines assume Git Bash, which the
# plugin needs anyway). Shown by health and setup next to the row's own reason.
FIX_LINES = {
    "home": ("Run /academic-writer:setup and pick a folder for your work.",
             "Run /academic-writer:setup and pick a folder for your work."),
    "profile": ("Run /academic-writer:setup init in your project folder.",
                "Run /academic-writer:setup init in your project folder."),
    "git": ("Open PowerShell and run: winget install --id Git.Git -e. Then close Claude Code completely and open it again.",
            "In Terminal run: xcode-select --install (or brew install git). Then restart Claude Code."),
    "node": ("Open PowerShell and run: winget install --id OpenJS.NodeJS.LTS -e. Then close Claude Code completely and open it again.",
             "Install the LTS version from https://nodejs.org (or brew install node). Then restart Claude Code."),
    "python": ("Install from https://www.python.org/downloads and tick \"Add python.exe to PATH\" on the first screen, "
               "or run: winget install --id Python.Python.3.12 -e. Then restart Claude Code.",
               "Install from https://www.python.org/downloads (or brew install python). Then restart Claude Code."),
    "python-addons": ("Run /academic-writer:setup, or in PowerShell: py -3 " + PIP_ADDONS,
                      "Run /academic-writer:setup, or in Terminal: python3 " + PIP_ADDONS),
    "hspell": ("hspell has no Windows installer; work without it, or use WSL (wsl --install, then sudo apt install hspell).",
               "In Terminal run: brew install hspell."),
    "gemini-key": ("Run /academic-writer:setup: it shows where to get a free key (aistudio.google.com/apikey) and "
                   "where to paste it (/plugin, Configure, google_api_key), never in the chat.",
                   "Run /academic-writer:setup: it shows where to get a free key (aistudio.google.com/apikey) and "
                   "where to paste it (/plugin, Configure, google_api_key), never in the chat."),
    "drive": ("In the Claude app or on claude.ai open Customize, then Connectors, and connect Google Drive "
              "(https://support.claude.com/en/articles/10166901).",
              "In the Claude app or on claude.ai open Customize, then Connectors, and connect Google Drive "
              "(https://support.claude.com/en/articles/10166901)."),
    "notebooklm": ("Needs Node.js. In PowerShell: npm install -g notebooklm-mcp-cli, then type ! nlm login in Claude Code.",
                   "Needs Node.js. In Terminal: npm install -g notebooklm-mcp-cli, then type ! nlm login in Claude Code."),
    "trove": ("Open https://heytrove.ai/install, follow the Windows steps, then type ! trove login in Claude Code.",
              "In Terminal: curl -fsSL https://heytrove.ai/install.sh | sh, then type ! trove login in Claude Code."),
    "kotar": ("Install Chrome from https://www.google.com/chrome (or winget install --id Google.Chrome -e), "
              "then sign in to Kotar through your university library.",
              "Install Chrome from https://www.google.com/chrome (or brew install --cask google-chrome), "
              "then sign in to Kotar through your university library."),
    "moodle": ("Sign in to your course site (Moodle) in Chrome with the Claude in Chrome extension; the plugin never asks for your password.",
               "Sign in to your course site (Moodle) in Chrome with the Claude in Chrome extension; the plugin never asks for your password."),
    "pageindex": ("Optional. Run /academic-writer:setup update-tools to add it.",
                  "Optional. Run /academic-writer:setup update-tools to add it."),
    "nightly-job": ("Not available on Windows yet; run the course scan by hand with /academic-writer:courses.",
                    "Run /academic-writer:courses to set the nightly time."),
}


def _run(cmd: List[str]) -> Tuple[int, str]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return 127, ""
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def _check(cid: str, label_he: str, ok: Optional[bool], optional: bool = False, found: Optional[str] = None,
           required: Optional[str] = None, reason_he: Optional[str] = None, fix: Optional[str] = None) -> Check:
    return {"id": cid, "label_he": label_he, "ok": ok, "optional": optional, "found": found,
            "required": required, "reason_he": reason_he, "fix": fix}


def _home_path(env: Mapping[str, str]) -> Optional[Path]:
    """Same order as home.py: ACADEMIC_HOME, then the pointer in the plugin data folder."""
    explicit = env.get("ACADEMIC_HOME")
    if explicit:
        return Path(explicit).expanduser()
    data = env.get("CLAUDE_PLUGIN_DATA")
    if data:
        try:
            pointer = json.loads((Path(data) / "home.json").read_text(encoding="utf-8"))
            path = pointer.get("path") if isinstance(pointer, dict) else None
            if isinstance(path, str) and path:
                return Path(path).expanduser()
        except (OSError, ValueError):
            pass
    return None


def _role(home: Optional[Path]) -> Optional[str]:
    if home is None:
        return None
    try:
        text = (home / ".academic-helper" / "home.md").read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(r"^role:\s*(\S+)\s*$", text, re.M)
    return match.group(1).strip("\"'") if match else None


def _check_home(env: Mapping[str, str], home: Optional[Path]) -> Check:
    label = "תיקיית הבית ופרופיל"
    if home is None:
        return _check("home", label, False, reason_he="עוד לא נבחרה תיקיית בית", fix=SETUP_FIX)
    if not home.is_dir():
        return _check("home", label, False, found=str(home), reason_he="תיקיית הבית לא נמצאה: " + str(home),
                      fix=SETUP_FIX)
    if not (home / ".academic-helper" / "home.md").is_file():
        return _check("home", label, False, found=str(home), reason_he="בתיקיית הבית אין עדיין פרופיל",
                      fix=SETUP_FIX)
    return _check("home", label, True, found=str(home))


def _workspace_folder(env: Mapping[str, str], cwd: Optional[str]) -> Optional[Path]:
    """The workspace this run is about: CLAUDE_PROJECT_DIR, else the working folder if it has a profile.
    Never the server's cwd by accident: a folder without a profile is "no workspace context"."""
    project = env.get("CLAUDE_PROJECT_DIR")
    if project:
        return Path(project)
    folder = Path(cwd if cwd is not None else os.getcwd())
    return folder if (folder / ".academic-helper" / "profile.md").is_file() else None


def _check_profile(env: Mapping[str, str], cwd: Optional[str] = None) -> Check:
    label = "פרופיל התיקייה הנוכחית"
    folder = _workspace_folder(env, cwd)
    if folder is None:
        return _check("profile", label, None, reason_he="הבדיקה רצה מחוץ לתיקיית עבודה, ולכן אין פרופיל לבדוק")
    profile = folder / ".academic-helper" / "profile.md"
    if profile.is_file():
        return _check("profile", label, True, found=str(profile))
    return _check("profile", label, False, reason_he="בתיקייה הזו אין פרופיל", fix="/academic-writer:setup init")


def _target_language(env: Mapping[str, str], home: Optional[Path], cwd: Optional[str]) -> Optional[str]:
    """targetLanguage from the workspace profile, else from home.md; None when neither says."""
    folder = _workspace_folder(env, cwd)
    paths = []
    if folder is not None:
        paths.append(folder / ".academic-helper" / "profile.md")
    if home is not None:
        paths.append(home / ".academic-helper" / "home.md")
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        match = re.search(r"^targetLanguage:[ \t]*(.+?)[ \t]*$", text, re.M)
        if match:
            return match.group(1).strip("\"'")
    return None


def _is_hebrew(language: Optional[str]) -> bool:
    return bool(language) and language.strip().lower() in ("he", "heb", "hebrew", "iw", "עברית")


def _python_candidates(which: Callable[[str], Optional[str]]) -> List[List[str]]:
    """Same order as bin/aw-python: python3, python, then the Windows launcher `py -3`."""
    out = []  # type: List[List[str]]
    for name in ("python3", "python"):
        exe = which(name)
        if exe:
            out.append([exe])
    launcher = which("py")
    if launcher:
        out.append([launcher, "-3"])
    return out


def _python(which: Callable[[str], Optional[str]], run: Callable[[List[str]], Tuple[int, str]]
            ) -> Tuple[Check, Optional[List[str]]]:
    label = "Python"
    required = "%d.%d" % MIN_PYTHON
    old = None  # type: Optional[Tuple[str, List[str]]]
    broken = False
    for cand in _python_candidates(which):
        code, out = run(cand + ["--version"])
        match = re.search(r"Python (\d+)\.(\d+)(?:\.(\d+))?", out)
        # Like bin/aw-python: a candidate counts only when --version exits 0 and prints "Python 3".
        # That skips the Microsoft Store stub that Windows ships as python.exe.
        if code != 0 or not match or match.group(1) != "3":
            broken = True
            continue
        found = ".".join(g for g in match.groups() if g is not None)
        if (int(match.group(1)), int(match.group(2))) < MIN_PYTHON:
            old = old or (found, cand)
            continue
        return _check("python", label, True, found=found, required=required), cand
    if old is not None:
        return _check("python", label, False, found=old[0], required=required,
                      reason_he="הגרסה ישנה מדי, נדרשת %s ומעלה" % required, fix=SETUP_FIX), old[1]
    if broken:
        return _check("python", label, False, required=required,
                      reason_he="Python לא הגיב (ב-Windows זה לרוב קיצור הדרך של Microsoft Store, לא Python אמיתי)",
                      fix=SETUP_FIX), None
    return _check("python", label, False, required=required, reason_he="Python לא מותקן", fix=SETUP_FIX), None


def _addons(exe: Optional[List[str]], run: Callable[[List[str]], Tuple[int, str]]) -> Check:
    label = "תוספות Python"
    required = " ".join(ADDONS)
    if exe is None:
        return _check("python-addons", label, None, required=required, reason_he="אי אפשר לבדוק בלי Python",
                      fix=SETUP_FIX)
    code, out = run(exe + ["-c", _PROBE])
    last = out.splitlines()[-1] if out.splitlines() else ""
    if last == "ALL_PRESENT":
        return _check("python-addons", label, True, found=required, required=required)
    if last.startswith("MISSING:"):
        missing = [m for m in last[len("MISSING:"):].split(",") if m]
        return _check("python-addons", label, False, required=required,
                      reason_he="חסרות: " + ", ".join(missing), fix=SETUP_FIX)
    return _check("python-addons", label, False, required=required, reason_he="הבדיקה לא הצליחה", fix=SETUP_FIX)


def _tool(cid: str, label: str, command: str, which: Callable[[str], Optional[str]], optional: bool,
          reason: str, fix: str) -> Check:
    path = which(command)
    if path:
        return _check(cid, label, True, optional=optional, found=path)
    return _check(cid, label, False, optional=optional, reason_he=reason, fix=fix)


def _node(which: Callable[[str], Optional[str]], run: Callable[[List[str]], Tuple[int, str]]) -> Check:
    label = "Node.js"
    path = which("node")
    if not path:
        return _check("node", label, False, required="%d+" % MIN_NODE,
                      reason_he="Node.js לא מותקן. בלעדיו תוכנת aw והתוספות של Claude Code לא עובדות", fix=SETUP_FIX)
    code, out = run([path, "--version"])
    match = re.match(r"v(\d+)\.", out.strip())
    if code == 0 and match:
        if int(match.group(1)) < MIN_NODE:
            return _check("node", label, False, found=out.strip(), required="%d+" % MIN_NODE,
                          reason_he="הגרסה ישנה מדי, נדרשת %d ומעלה" % MIN_NODE, fix=SETUP_FIX)
        return _check("node", label, True, found=out.strip(), required="%d+" % MIN_NODE)
    # The version command failed or printed something unreadable: do not report a working Node.
    return _check("node", label, False, found=path, required="%d+" % MIN_NODE,
                  reason_he="Node.js נמצא (%s) אבל בדיקת הגרסה נכשלה או לא הובנה, ולכן אי אפשר לדעת אם הוא תקין" % path,
                  fix=SETUP_FIX)


_CHROME_NAMES = ("google-chrome", "google-chrome-stable", "chrome", "chromium", "chromium-browser")


def _chrome_locations(env: Mapping[str, str], platform: str) -> List[str]:
    if platform == "darwin":
        return ["/Applications/Google Chrome.app",
                str(Path(env.get("HOME", str(Path.home()))) / "Applications" / "Google Chrome.app")]
    if platform.startswith("win") or platform in ("cygwin", "msys"):
        roots = [env.get(k) for k in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA")]
        defaults = [r"C:\Program Files", r"C:\Program Files (x86)"]
        return [r + "\\Google\\Chrome\\Application\\chrome.exe" for r in [x for x in roots if x] + defaults]
    return []


def _kotar(env: Mapping[str, str], which: Callable[[str], Optional[str]], platform: str,
           exists: Callable[[str], bool]) -> Check:
    label = "Chrome (לקוטר)"
    for name in _CHROME_NAMES:
        path = which(name)
        if path:
            return _check("kotar", label, True, optional=True, found=path)
    for loc in _chrome_locations(env, platform):
        if exists(loc):
            return _check("kotar", label, True, optional=True, found=loc)
    return _check("kotar", label, False, optional=True,
                  reason_he="Chrome לא נמצא. הורדת ספרים מקוטר עובדת דרך Chrome שמחובר לקוטר",
                  fix=SETUP_FIX)


def _manual(cid: str, label: str, reason: str) -> Check:
    """A connection no script can see (it lives in the Claude app or in the browser): status unknown."""
    return _check(cid, label, None, optional=True, reason_he=reason, fix=SETUP_FIX)


def _pageindex(env: Mapping[str, str], which: Callable[[str], Optional[str]]) -> Check:
    label = "PageIndex"
    data = env.get("CLAUDE_PLUGIN_DATA")
    if data and (Path(data) / "pageindex").is_dir():
        return _check("pageindex", label, True, optional=True, found=str(Path(data) / "pageindex"))
    path = which("pilib")
    if path:
        return _check("pageindex", label, True, optional=True, found=path)
    return _check("pageindex", label, False, optional=True, reason_he="לא מותקן (הספרייה עובדת עם Trove)",
                  fix=SETUP_FIX)


def _nightly(env: Mapping[str, str], platform: str, role: Optional[str]) -> Check:
    label = "משימת הלילה"
    if platform != "darwin" or role in ("lecturer", "researcher"):
        return _check("nightly-job", label, None, optional=True, reason_he="רק ב-macOS")
    agents = Path(env.get("HOME", str(Path.home()))) / "Library" / "LaunchAgents"
    try:
        plists = sorted(agents.glob("*academic*.plist")) if agents.is_dir() else []
    except OSError:
        plists = []
    if plists:
        return _check("nightly-job", label, True, optional=True, found=str(plists[0]))
    return _check("nightly-job", label, False, optional=True, reason_he="משימת הלילה לא הוגדרה",
                  fix="/academic-writer:courses")


def run_checks(env: Mapping[str, str], which: Callable[[str], Optional[str]] = shutil.which,
               run: Callable[[List[str]], Tuple[int, str]] = _run, platform: str = sys.platform,
               cwd: Optional[str] = None, exists: Callable[[str], bool] = os.path.exists) -> List[Check]:
    home = _home_path(env)
    hebrew = _is_hebrew(_target_language(env, home, cwd))
    python_check, exe = _python(which, run)
    key_present = bool(env.get("GOOGLE_API_KEY"))  # presence only; the value is never stored or printed
    checks = [
        _check_home(env, home),
        _check_profile(env, cwd),
        _tool("git", "Git", "git", which, False,
              "Git לא מותקן. הוא נחוץ להתקנת התוסף, ו-Claude Code ב-Windows מפעיל דרכו את הפקודות", SETUP_FIX),
        _node(which, run),
        python_check,
        _addons(exe, run),
        _tool("hspell", "בדיקת איות בעברית", "hspell", which, not hebrew,
              "בודק האיות העברי לא מותקן, והוא נדרש לכתיבה בעברית" if hebrew
              else "בודק האיות העברי לא מותקן (נחוץ רק לכתיבה בעברית)", SETUP_FIX),
        _check("gemini-key", "מפתח Gemini", key_present, optional=True,
               found="קיים" if key_present else None,
               reason_he=None if key_present else "לא הוגדר מפתח",
               fix=None if key_present else SETUP_FIX),
        _manual("drive", "Google Drive (מחבר ב-Claude)",
                "אי אפשר לבדוק מכאן. מחברים ב-Claude: התאמה אישית, מחברים, Google Drive. הוא שומר ומוצא את קבצי הקורסים"),
        _tool("notebooklm", "NotebookLM", "nlm", which, True, "NotebookLM לא מותקן", SETUP_FIX),
        _tool("trove", "Trove", "trove", which, True,
              "Trove לא מותקן. הוא שומר את המקורות והמאמרים שלך בספרייה אחת שאפשר לחפש בה, "
              "ובלעדיו אפשר להמשיך לעבוד", SETUP_FIX),
        _kotar(env, which, platform, exists),
        _manual("moodle", "אתר הקורסים (Moodle) ב-Chrome",
                "אי אפשר לבדוק מכאן. צריך להיות מחוברים לאתר הקורסים ב-Chrome עם התוסף Claude in Chrome"),
        _pageindex(env, which),
        _nightly(env, platform, _role(home)),
    ]
    for c in checks:
        win, mac = FIX_LINES[c["id"]]
        c["fix_windows"] = win
        c["fix_mac"] = mac
    return checks


def main(argv: List[str]) -> int:
    # Windows pipes and files default to the legacy code page (cp1252), which cannot print the Hebrew labels.
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError, OSError):
        pass
    env = dict(os.environ)
    # Skills run this through the Bash tool, which gets no CLAUDE_PLUGIN_DATA; they pass --data-dir instead.
    if "--data-dir" in argv and argv.index("--data-dir") + 1 < len(argv):
        env["CLAUDE_PLUGIN_DATA"] = argv[argv.index("--data-dir") + 1]
    checks = run_checks(env)
    if "--json" in argv:
        print(json.dumps(checks, ensure_ascii=False, indent=2))
        return 0
    for c in checks:
        glyph = "✓" if c["ok"] else "—" if c["ok"] is None else "✗"
        line = "%s %s" % (glyph, c["label_he"])
        if c["found"] and c["id"] != "gemini-key":
            line += " (%s)" % c["found"]
        if c["reason_he"]:
            line += ": " + c["reason_he"]
        if c["fix"] and c["ok"] is not True:
            line += "  [%s]" % c["fix"]
        if c["ok"] is not True and (c["optional"] is False or c["ok"] is False):
            line += "\n    Windows: %s\n    Mac: %s" % (c["fix_windows"], c["fix_mac"])
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
