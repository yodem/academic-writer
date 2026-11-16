"""Every command that builds a path from ${CLAUDE_PLUGIN_ROOT} quotes it.

Windows user folders often contain spaces ("C:\\Users\\Dana Levi\\..."), and an unquoted path splits into two
arguments. A command line is a line inside a fenced code block, or an inline code span that has a space in it
(arguments follow the path). A bare path in a prose span ("see `${CLAUDE_PLUGIN_ROOT}/x.md`") is a reference, not a command.
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
TOKEN = "${CLAUDE_PLUGIN_ROOT}/"


def unquoted(segment):
    """Occurrences of the token in `segment` that are not inside double quotes."""
    out = []
    start = 0
    while True:
        at = segment.find(TOKEN, start)
        if at < 0:
            return out
        # Directly after an opening quote counts as quoted (also inside a nested $(...) that restarts the count).
        if segment[:at].replace('\\"', "").count('"') % 2 == 0 and segment[at - 1:at] != '"':
            out.append(at)
        start = at + len(TOKEN)


def command_segments(text):
    """(line number, command text) for fenced lines and for inline code spans with a space in them."""
    fenced = False
    for number, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            yield number, line
            continue
        for span in re.findall(r"`([^`\n]+)`", line):
            if " " in span.strip():
                yield number, span


def violations():
    found = []
    files = sorted(p for folder in ("skills", "agents") for p in (ROOT / "src" / folder).rglob("*")
                   if p.is_file() and p.suffix in (".md", ".sh"))
    for path in files:
        text = path.read_text(encoding="utf-8")
        for number, segment in command_segments(text):
            if TOKEN in segment and unquoted(segment):
                found.append("%s:%d: %s" % (path.relative_to(ROOT), number, segment.strip()[:140]))
    return found


def test_no_unquoted_plugin_root_path_in_a_command():
    bad = violations()
    assert not bad, "unquoted ${CLAUDE_PLUGIN_ROOT}/ path in a command:\n" + "\n".join(bad)


def test_the_scanner_catches_what_it_should():
    assert unquoted('sh "${CLAUDE_PLUGIN_ROOT}/bin/aw-python" x') == []
    assert unquoted('sh "${CLAUDE_PLUGIN_ROOT}/bin/aw-python" ${CLAUDE_PLUGIN_ROOT}/scripts/a.py')
    assert unquoted('cat ${CLAUDE_PLUGIN_ROOT}/words.md')
    assert unquoted('python -c "open(\'${CLAUDE_PLUGIN_ROOT}/t.json\')"') == []
    assert list(command_segments("see `${CLAUDE_PLUGIN_ROOT}/a.md` now")) == []
    assert list(command_segments("run `sh ${CLAUDE_PLUGIN_ROOT}/a.sh x`"))
