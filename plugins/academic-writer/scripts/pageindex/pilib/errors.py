"""One failure type for the indexing commands.

It is a SystemExit, so a command that does not catch it still prints the message to stderr and exits 1
(the behaviour of the original pilib). The index commands catch it to print the JSON failure object.
"""
from __future__ import annotations

import re

KEY_RE = re.compile(r"AIza[0-9A-Za-z_-]{20,}")


def scrub(text: str, limit: int = 300) -> str:
    """Error text safe to print: no API key, one line, bounded."""
    return KEY_RE.sub("[key]", " ".join(str(text).split()))[:limit]


class IndexFailure(SystemExit):
    def __init__(self, code: str, message: str, **extra):
        super().__init__(f"ERROR library index: {message}")
        self.code_name = code
        self.message = message
        self.extra = extra
