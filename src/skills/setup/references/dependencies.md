# Dependencies: what each one is for, and how to install it

> Loaded on demand by `setup` Step 4, `init` Phase 0 and `health`. The rule everywhere: **Claude
> installs something only after the researcher says yes in an `AskUserQuestion`.** Things only the
> researcher can do (install Python itself, install Homebrew, sign in to a website) are given as
> numbered steps for them to follow. Print long steps, then end the turn; never print them and ask a
> question in the same turn (the printed text may not be shown).

## Typing a command yourself

Some commands only the researcher can run, because they open a web page or ask for a password. Give them
this recipe with the actual command filled in (`COMMAND`, for example `trove login`):

1. Click once in the box at the bottom of Claude Code where you normally type to me. This is the **prompt box**.
2. Type an exclamation mark, a space, then the command, exactly as written: `! COMMAND`. Then press Enter.
   The `!` means "run this on my computer instead of sending it to Claude". The command's own text then appears
   in the conversation.
3. Say what will happen for that command (see the tool's section below), for example "your web browser opens
   a sign-in page".
4. Say how they know it worked (a sentence on the screen such as "Logged in", or the browser page saying you can
   close it), and what to do if not: copy what the screen says, paste it to me, and I will explain it.
5. Come back to this conversation and tell me "done".

Commands that need the **Mac password** (Homebrew, `sudo`) do not work from the prompt box, because it cannot
ask for a password. Those run in the Terminal app instead (next section).

## Opening the Terminal app (Mac)

A terminal is a window where you type commands instead of clicking. It is a separate program from Claude Code.

1. Press Cmd+Space (hold the Command key, tap the space bar). A search box opens.
2. Type `Terminal` and press Enter. A window with a blinking cursor opens.
3. Paste the command (Cmd+V) and press Enter. When a password is asked, type it and press Enter; nothing appears while
   you type, which is normal.
4. When the prompt shows again (a line ending in `%`), it has finished. You can close the window with Cmd+Q.

On Windows: Start menu, type `PowerShell`, press Enter. On Linux: Ctrl+Alt+T on most systems.

## Restarting Claude Code

Some changes (a new Python, a stored key, a newly installed tool) are only seen by a **new** Claude Code session.
Your answers are saved in files in your folder, so nothing is lost.

1. Quit Claude Code completely. In a terminal, type `/exit` and press Enter (or press Ctrl+C twice). In the Claude desktop
   app, quit the app (Mac: Cmd+Q; or Claude menu, then Quit). Closing only the window is not enough.
2. Open it again **in the same folder** you used before. Desktop app: open Claude, choose Code, then choose that same folder.
   Terminal: type `cd ` (with a space), drag the folder from Finder into the window, press Enter, type `claude`, press Enter.
3. Type `/academic-writer:setup` and press Enter. Setup sees your saved answers and skips what is done.

## Overview table

| Dependency | Needed for | Required? | Who installs it |
|---|---|---|---|
| Python 3 | Reading Word/PDF files, building the final `.docx`, proofreading checks | Yes | The researcher (steps below) |
| Python packages (`python-docx`, `lxml`, `pdfplumber`, `pymupdf`, `jsonschema`) | Same as above — these are add-ons Python uses to open Word and PDF files | Yes | Claude, after asking |
| Homebrew (macOS only) | A free installer for Mac tools; needed only to install hspell (Trove and NotebookLM do not need it) | Only for hspell | The researcher (steps below) |
| hspell | A Hebrew spelling checker used by `/academic-writer:proofread` | Optional, Hebrew only | Claude on macOS/Linux, after asking |
| Trove (`trove`) | Your online research library — lets the plugin search and quote your sources | Optional | Claude (Trove's own installer), after asking; the researcher creates an account and signs in |
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
1. Open https://www.python.org/downloads/ in your web browser (Safari or Chrome).
2. Click the yellow **Download Python 3.x** button. A file ending in `.pkg` lands in your Downloads folder.
3. Double-click that `.pkg` file (find it in Finder, in **Downloads**). Click **Continue**, **Continue**, **Agree**, **Install**,
   and type your Mac password when asked.
4. When it says "The installation was successful", click **Close**. (A Finder window may open: you can close it.)
5. Quit Claude Code completely and open it again in the same folder (see *Restarting Claude Code* above).
6. Type `/academic-writer:setup`. Your answers are saved, so I pick up from here.

If, before this, a window appeared saying `python3` needs the **command line developer tools**: that is Apple's own
installer and it is safe. Either click **Install** and wait several minutes (it is a large download), or click
**Cancel** and use the python.org installer above. Both work.

**Windows**
1. Open https://www.python.org/downloads/ in your web browser.
2. Click the yellow "Download Python 3.x" button and open the downloaded installer.
3. On the first screen, **tick the box "Add python.exe to PATH"** (this lets other programs find
   Python), then click "Install Now".
4. When it finishes, close Claude Code completely and open it again.
5. Run `/academic-writer:setup` again.

**Linux**: install `python3` and `python3-pip` with your system's package manager (on Ubuntu:
`sudo apt install python3 python3-pip`), then restart Claude Code.

## Homebrew (macOS only) — the researcher installs it

Only needed for hspell (Hebrew writers on a Mac) when `BREW_MISSING`; Trove and NotebookLM do not need it. Say: "Homebrew is a free,
widely used installer for Mac tools. Installing it needs your Mac password, so you have to do this
part yourself."

1. Open https://brew.sh in your web browser.
2. Under **Install Homebrew**, click the copy icon next to the command (a long line starting with `/bin/bash -c`).
3. Open the Terminal app (*Opening the Terminal app*, above), paste the command with Cmd+V, and press Enter.
4. Press Enter again when it says "Press RETURN/ENTER to continue", and type your Mac password when asked. If a window asks to install
   Apple's command line developer tools, click **Install** and wait; it may take several minutes, and Homebrew continues by itself.
5. It finishes with "Installation successful!". It then prints a section called **Next steps** with two or three lines to
   copy and run: paste each into the same Terminal window and press Enter. (This tells Terminal where Homebrew lives.)
6. Check: type `brew --version` and press Enter; it should print `Homebrew 4.x.x` or similar.
7. Close Terminal (Cmd+Q), quit Claude Code completely and open it again in the same folder, then type
   `/academic-writer:setup`.

If step 6 says `command not found: brew`, the **Next steps** lines from step 5 were not run: scroll up in Terminal to find
them, paste each one and press Enter, then try step 6 again. If anything else fails, copy the last lines of the Terminal
window and paste them to me.

## hspell — Claude installs it after asking (Hebrew writers only)

One sentence: "hspell is a free Hebrew spelling dictionary; the proofreader uses it to catch typos
that are easy to miss by eye. Without it, proofreading still works, just with one fewer safety net."

- **macOS with Homebrew**: Claude runs `brew install hspell` after a yes (about a minute). No Homebrew yet: offer
  the steps in the Homebrew section first, or skip.
- **Linux**: installing needs the computer password, so the researcher opens a regular terminal (Ctrl+Alt+T), types
  `sudo apt install hspell`, presses Enter and types their password when asked (nothing shows while typing).
- **Windows**: hspell has no Windows version. Say so plainly and move on — proofreading skips this
  check automatically.

Confirm afterwards with `command -v hspell`.

## Trove (`trove`) — Claude installs it after asking

One sentence: "Trove is an online library for your source PDFs; with it I can search your
sources and quote them with exact page numbers."

- **macOS / Linux**: after a yes, Claude runs Trove's own installer,
  `curl -fsSL https://heytrove.ai/install.sh | sh` (it downloads and runs a script from heytrove.ai; no Homebrew is involved).
- **Windows**: point the researcher to the install page (https://heytrove.ai/install) and re-check
  with `command -v trove` when they say it's done.
- If `command -v trove` finds nothing right after a successful install, the session does not see the new tool yet:
  restart Claude Code (*Restarting Claude Code*, above) and run setup again.

**Sign-up and sign-in (the researcher does this):**
1. Click in the prompt box of Claude Code, type `! trove login` and press Enter (see *Typing a command yourself*).
2. Your web browser opens a Trove page. If you have no account, use the page's option to create one (you can use a
   Google account if the page offers it); otherwise sign in. Whether an account is free or paid, and its limits, is set by
   Trove: check https://heytrove.ai for the current plans before you subscribe.
3. When the page says you are signed in (or you can close the tab), return to Claude Code. The prompt box shows a
   success line.
4. Tell me "done"; I check with `trove auth whoami --no-session`, which prints your account.
If the browser does not open, copy the web address the command printed and paste it into your browser.

## NotebookLM (`nlm`) — Claude installs it after asking

One sentence: "NotebookLM is Google's tool for asking questions about a set of sources; the plugin
can use it as a second research assistant." It is optional: nothing else depends on it.

- Needs `npm` (it comes with Node.js, a free program). If `NPM_MISSING`, skip NotebookLM and say it can be added
  later. To add Node.js now: open https://nodejs.org, click the **LTS** download button, open the downloaded
  `.pkg` (Windows: `.msi`), click Continue/Next through the installer (Mac password when asked), then restart Claude
  Code (*Restarting Claude Code*) and run setup again.
- After a yes, Claude runs `npm install -g notebooklm-mcp-cli` (about a minute). If it says `EACCES` or permission
  denied, do not use `sudo`; read `troubleshooting.md` and tell me what it printed.

**Sign-in (the researcher does this):**
1. Click in the prompt box of Claude Code, type `! nlm login` and press Enter (see *Typing a command yourself*).
2. A browser window opens a Google sign-in page. Choose your Google account and allow access. If no window opens, copy the web address the command printed and paste it into your browser.
3. Return to Claude Code; it prints that you are signed in. Tell me "done"; I check with `nlm login --check`.

## Reporting results

After each install, re-run that tool's detection line and report in plain words: "Done — hspell
is installed." or "That didn't work. Here's the message: … Nothing is broken; you can keep going
without it." Never paste a long error log without a one-line explanation first. See
`troubleshooting.md` for common failures.
