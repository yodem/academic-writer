# Dependencies: what each one is for, and how to install it

> Loaded on demand by `setup` Step 4, `init` Phase 0 and `health`. The rule everywhere: **Claude
> installs something only after the researcher says yes in an `AskUserQuestion`.** Things only the
> researcher can do (install Python itself, install Homebrew, sign in to a website) are given as
> numbered steps for them to follow.

"Command line" below means the Terminal app on a Mac, or the terminal inside Claude Code. When the
researcher has to type a command themselves, they can type it straight into Claude Code with a `!`
in front (for example `! nlm login`): Claude Code runs it and shows the result.

## Overview table

| Dependency | Needed for | Required? | Who installs it |
|---|---|---|---|
| Python 3 | Reading Word/PDF files, building the final `.docx`, proofreading checks | Yes | The researcher (steps below) |
| Python packages (`python-docx`, `lxml`, `pdfplumber`, `pymupdf`, `jsonschema`) | Same as above — these are add-ons Python uses to open Word and PDF files | Yes | Claude, after asking |
| Homebrew (macOS only) | A free installer for Mac tools; needed only to install hspell or Trove | Only if you want those | The researcher (steps below) |
| hspell | A Hebrew spelling checker used by `/academic-writer:proofread` | Optional, Hebrew only | Claude on macOS/Linux, after asking |
| Trove (`trove`) | Your online research library — lets the plugin search and quote your sources | Optional | Claude on macOS (via Homebrew), after asking |
| NotebookLM (`nlm`) | Google's source Q&A tool | Optional | Claude, after asking; the researcher signs in |
| Gemini API key | Lets the plugin use Google's Gemini model for drafting and proofreading | Optional but recommended | The researcher (see `gemini-key.md`) |

## Detection commands (run all at once; none of them change anything)

```bash
uname -s 2>/dev/null || echo "Windows"
command -v python3 >/dev/null 2>&1 && python3 --version || echo "PYTHON_MISSING"
command -v brew >/dev/null 2>&1 && echo "BREW_OK" || echo "BREW_MISSING"
command -v hspell >/dev/null 2>&1 && echo "HSPELL_OK" || echo "HSPELL_MISSING"
command -v trove >/dev/null 2>&1 && echo "TROVE_OK" || echo "TROVE_MISSING"
command -v nlm >/dev/null 2>&1 && echo "NLM_OK" || echo "NLM_MISSING"
command -v npm >/dev/null 2>&1 && echo "NPM_OK" || echo "NPM_MISSING"
```

`uname -s` prints `Darwin` on macOS, `Linux` on Linux, and something starting with `MINGW` or
`MSYS` (or nothing) on Windows.

The Python package check is in `python-deps.md`.

## Python 3 — the researcher installs it

If `PYTHON_MISSING`, say: "Python is a free program that Academic Writer uses behind the scenes to
open Word and PDF files and to build your finished document. I can't install it for you, but it
takes about five minutes." Then give the steps for their system:

**macOS**
1. Open https://www.python.org/downloads/ in your browser.
2. Click the yellow "Download Python 3.x" button.
3. Open the downloaded `.pkg` file and click Continue → Agree → Install (enter your Mac password
   when asked).
4. When it finishes, quit Claude Code completely and open it again.
5. Run `/academic-writer:setup` again — I'll pick up from here.

**Windows**
1. Open https://www.python.org/downloads/ in your browser.
2. Click the yellow "Download Python 3.x" button and open the downloaded installer.
3. On the first screen, **tick the box "Add python.exe to PATH"** (this lets other programs find
   Python), then click "Install Now".
4. When it finishes, close Claude Code completely and open it again.
5. Run `/academic-writer:setup` again.

**Linux**: install `python3` and `python3-pip` with your system's package manager (on Ubuntu:
`sudo apt install python3 python3-pip`), then restart Claude Code.

## Homebrew (macOS only) — the researcher installs it

Only needed if they want hspell or Trove and `BREW_MISSING`. Say: "Homebrew is a free,
widely used installer for Mac tools. Installing it needs your Mac password, so you have to do this
part yourself."

1. Open https://brew.sh in your browser.
2. Copy the one-line command shown under "Install Homebrew".
3. Open the Terminal app (press Cmd+Space, type "Terminal", press Enter), paste the command,
   press Enter, and type your Mac password when asked (nothing appears while you type — that is
   normal).
4. When it says "Installation successful", follow the two or three "Next steps" lines it prints.
5. Quit and reopen Claude Code, then run `/academic-writer:setup` again.

## hspell — Claude installs it after asking (Hebrew writers only)

One sentence: "hspell is a free Hebrew spelling dictionary; the proofreader uses it to catch typos
that are easy to miss by eye. Without it, proofreading still works, just with one fewer safety net."

- **macOS with Homebrew**: Claude runs `brew install hspell` after a yes.
- **Linux**: installing needs the computer password, so the researcher types
  `! sudo apt install hspell` into Claude Code themselves.
- **Windows**: hspell has no Windows version. Say so plainly and move on — proofreading skips this
  check automatically.

Confirm afterwards with `command -v hspell`.

## Trove (`trove`) — Claude installs it after asking

One sentence: "Trove is an online library for your source PDFs; with it I can search your
sources and quote them with exact page numbers."

- **macOS / Linux**: after a yes, Claude runs
  `curl -fsSL https://heytrove.ai/install.sh | sh`.
- **Windows**: point the researcher to the install page (https://heytrove.ai/install) and re-check
  with `command -v trove` when they say it's done.

Then the researcher signs in themselves (it opens a browser): `! trove login`.

## NotebookLM (`nlm`) — Claude installs it after asking

One sentence: "NotebookLM is Google's tool for asking questions about a set of sources; the plugin
can use it as a second research assistant."

- Needs `npm` (it comes with Node.js). If `NPM_MISSING`, skip NotebookLM and say it can be added
  later — it is optional.
- After a yes, Claude runs `npm install -g notebooklm-mcp-cli`.
- Then the researcher signs in (it opens a browser): `! nlm login`.

## Reporting results

After each install, re-run that tool's detection line and report in plain words: "Done — hspell
is installed." or "That didn't work. Here's the message: … Nothing is broken; you can keep going
without it." Never paste a long error log without a one-line explanation first. See
`troubleshooting.md` for common failures.
