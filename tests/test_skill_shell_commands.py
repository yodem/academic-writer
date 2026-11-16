"""The shell commands written inside skill and agent Markdown survive the shell they run in.

Two kinds of breakage kept slipping through review, so this test executes the class rather than spot checks:

1. Python passed to the resolver as `sh ".../aw-python" -c "<code>"` (or as a heredoc). The shell parses the
   quoting before Python sees the code: a double-quoted string literal inside a double-quoted `-c` argument loses
   its quotes (`encoding="utf-8"` arrives as `encoding=utf-8`, a NameError on `utf` at run time). Each snippet is
   split as POSIX sh splits it (shlex, posix=True), then compiled; a bare `utf`/`utf8` name fails too.
2. A script run as `sh <path>` must be POSIX sh: a script whose shebang names bash must be run with `bash`
   (Git Bash provides bash on Windows; `sh` there may be a stricter shell).

Script invocations (`aw-python "${CLAUDE_PLUGIN_ROOT}/scripts/x.py"`) are checked too: the script must exist in src/.
"""
import ast
import pathlib
import re
import shlex

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
DUMMY_ROOT = "/plugin-root"
QUOTE_LOSS_NAMES = {"utf", "utf8"}

FENCE = re.compile(r"^\s*(```+|~~~+)")
INLINE = re.compile(r"`([^`\n]+)`")
# The start of a Python invocation: the resolver through sh, or a bare python/python3.
PY_START = re.compile(r'\bsh\s+"\$\{CLAUDE_PLUGIN_ROOT\}/bin/aw-python"|(?<![\w/.-])python3?(?=\s)')
SCRIPT_RUN = re.compile(r'(?<![\w-])(sh|bash)\s+"?\$\{CLAUDE_PLUGIN_ROOT\}/([^"\s`]+)"?')
HEREDOC = re.compile(r"""^\s*<<-?\s*(['"]?)([A-Za-z_]+)\1""")


def markdown_files():
    files = sorted(SRC.glob("skills/**/*.md")) + sorted(SRC.glob("agents/**/*.md"))
    assert files, "no skill or agent Markdown found"
    return files


def segments(path):
    """(label, text) per fenced block (whole block, so multi-line commands stay whole) and per inline code span."""
    lines = path.read_text(encoding="utf-8").splitlines()
    out, block, start, fence = [], None, 0, None
    for i, line in enumerate(lines, 1):
        m = FENCE.match(line)
        if block is None:
            if m:
                block, start, fence = [], i, m.group(1)[0]
                continue
            for span in INLINE.findall(line):
                out.append((f"{path.relative_to(ROOT)}:{i}", span))
        else:
            if m and m.group(1)[0] == fence:
                out.append((f"{path.relative_to(ROOT)}:{start}", "\n".join(block)))
                block = None
                continue
            block.append(line)
    return out


def expand(text):
    """What the shell would substitute before Python sees it: the plugin root becomes a dummy path."""
    return text.replace("${CLAUDE_PLUGIN_ROOT}", DUMMY_ROOT).replace("${CLAUDE_PLUGIN_DATA}", "/plugin-data")


def lex_from(text):
    lex = shlex.shlex(text, posix=True, punctuation_chars=";&|()<>")
    lex.whitespace_split = True
    lex.commenters = ""
    return lex


def python_snippets(label, text):
    """Yield (label, kind, code_or_None, error) for every Python invocation in `text`.

    kind is "c" (a -c argument), "heredoc", "script" (a script path, code None) or "skip" (nothing to check)."""
    for m in PY_START.finditer(text):
        rest = text[m.start():]
        lex = lex_from(expand(rest))
        tokens = []
        try:
            while len(tokens) < 6:
                tok = lex.get_token()
                if tok is None or tok == lex.eof:
                    break
                if tokens and tok in {";", "&&", "||", "|", ")", "&", "("}:
                    break
                tokens.append(tok)
                if len(tokens) >= 2 and tokens[-2] == "-c":
                    break
        except ValueError as e:  # unbalanced quotes before the code argument ends
            yield label, "c", None, f"shell cannot split this command: {e}"
            continue
        args = tokens[2:] if tokens[:1] == ["sh"] else tokens[1:]
        if "-c" in args:
            i = args.index("-c")
            if i + 1 < len(args):
                yield label, "c", args[i + 1], None
            else:  # a prose mention such as `python -c`, not a command
                yield label, "skip", None, None
            continue
        if args and args[0] in {"<", "<<", "-"}:
            # Heredoc: `aw-python << 'EOF'` or `aw-python - <<'EOF'`. Body runs to the delimiter line.
            after = rest.split("\n", 1)
            head = after[0][after[0].find("<<"):] if "<<" in after[0] else ""
            hm = HEREDOC.match(head)
            if hm and len(after) > 1:
                quoted, delim = bool(hm.group(1)), hm.group(2)
                body = []
                for ln in after[1].split("\n"):
                    if ln.strip() == delim:
                        break
                    body.append(ln)
                else:
                    yield label, "heredoc", None, f"heredoc <<{delim} never closes"
                    continue
                code = "\n".join(body)
                yield label, "heredoc", code if quoted else expand(code), None
                continue
            yield label, "skip", None, None
            continue
        if args and args[0].startswith(DUMMY_ROOT + "/") and args[0].endswith(".py"):
            yield label, "script", args[0], None
            continue
        yield label, "skip", None, None


def problems_in(code):
    try:
        tree = compile(code, "<snippet>", "exec", flags=ast.PyCF_ONLY_AST)
    except SyntaxError as e:
        return f"SyntaxError: {e.msg} (line {e.lineno}): {code.strip()[:120]!r}"
    bad = sorted({n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id in QUOTE_LOSS_NAMES})
    if bad:
        return f"bare name {bad} where a quoted string was meant (quotes lost in the shell): {code.strip()[:120]!r}"
    return None


def collect():
    found = []
    for path in markdown_files():
        for label, text in segments(path):
            found.extend(python_snippets(label, text))
    return found


def test_python_snippets_compile_after_shell_quoting():
    found = collect()
    failures, compiled, scripts = [], 0, 0
    for label, kind, code, error in found:
        if error:
            failures.append(f"{label}: {error}")
        elif kind in {"c", "heredoc"}:
            compiled += 1
            problem = problems_in(code)
            if problem:
                failures.append(f"{label}: {problem}")
        elif kind == "script":
            scripts += 1
            rel = code[len(DUMMY_ROOT) + 1:]
            if not (SRC / rel).is_file():
                failures.append(f"{label}: script {rel} does not exist in src/")
    print(f"checked {compiled} Python snippets (-c and heredoc) and {scripts} script invocations")
    assert compiled >= 10, f"only {compiled} Python snippets found; the extractor is broken"
    assert compiled + scripts >= 20, f"only {compiled + scripts} commands checked; the extractor is broken"
    assert not failures, "\n".join(failures)


def shebang_shell(path):
    first = path.read_text(encoding="utf-8").splitlines()[0] if path.stat().st_size else ""
    if not first.startswith("#!"):
        return None
    parts = first[2:].split()
    name = pathlib.Path(parts[0]).name if parts else ""
    if name == "env" and len(parts) > 1:
        name = parts[1]
    return name


def test_scripts_run_with_the_shell_their_shebang_names():
    failures, checked = [], 0
    for path in markdown_files():
        for label, text in segments(path):
            for m in SCRIPT_RUN.finditer(text):
                runner, rel = m.group(1), m.group(2)
                target = SRC / rel
                checked += 1
                if not target.is_file():
                    failures.append(f"{label}: {runner} {rel}: no such file in src/")
                    continue
                wants = shebang_shell(target)
                if wants == "bash" and runner != "bash":
                    failures.append(f"{label}: {rel} is a bash script (shebang) but is run with `{runner}`")
    print(f"checked {checked} sh/bash script invocations")
    assert checked >= 20, f"only {checked} sh/bash invocations found; the extractor is broken"
    assert not failures, "\n".join(failures)


@pytest.mark.parametrize(
    "snippet, ok",
    [
        ('sh "${CLAUDE_PLUGIN_ROOT}/bin/aw-python" -c "open(\'x\', encoding=\'utf-8\')"', True),
        ('sh "${CLAUDE_PLUGIN_ROOT}/bin/aw-python" -c "open(\'x\', encoding="utf-8")"', False),
        ('X=$(sh "${CLAUDE_PLUGIN_ROOT}/bin/aw-python" -c "\nimport re\nprint(1)\n")', True),
        ('sh "${CLAUDE_PLUGIN_ROOT}/bin/aw-python" -c "print("a b")"', False),
    ],
)
def test_detector_catches_quote_loss(snippet, ok):
    results = list(python_snippets("t", snippet))
    assert len(results) == 1
    _, kind, code, error = results[0]
    assert kind == "c" and error is None
    assert (problems_in(code) is None) is ok, code
