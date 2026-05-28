"""
Tests for scripts/gemini_academic_writer.py

Covers:
- load_voice_profile: success, missing file, writer config extraction
- _extract_writer_config: various YAML block shapes
- build_draft_prompt: key fields appear in prompts
- build_edit_prompt: key fields appear in prompts
- call_gemini_api: success path, missing key error, 429 retry then success,
  429 exhausted (raises)
"""

import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from unittest.mock import MagicMock, patch, call

# Make sure the script is importable from any cwd
sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "scripts"),
)
import gemini_academic_writer as gaw  # noqa: E402


# ---------------------------------------------------------------------------
# Sample fixtures
# ---------------------------------------------------------------------------

VOICE_MD_WITH_WRITER = """\
# Author Voice

## Core Voice

The author writes formal academic Hebrew prose.
Sentences are complex, citations are dense.

## Academic-specific

Use inline-parenthetical citations.
Avoid passive constructions where possible.

## Writer Configuration

writer:
  provider: "gemini"
  model: "gemini-2.5-flash"
  temperature: 0.7
  max_tokens: 3000
"""

VOICE_MD_NO_WRITER = """\
# Author Voice

## Core Voice

The author writes formal academic Hebrew prose.
"""

DRAFT_CONTEXT = {
    "section_outline": "This section examines the role of exile in Second Temple literature.",
    "evidence": [
        {"id": "e1", "text": "ויגל יהויכין מירושלים (2 Kgs 24:15)"},
    ],
    "evidence_ownership": {
        "owns": ["e1"],
        "back_reference": [],
    },
    "vectorless_context": "Passage about deportees from the Elephantine papyri...",
    "paragraph_index": 2,
    "word_ceiling": 200,
    "language": "he",
}

EDIT_CONTEXT = {
    "original_text": "הגולה מהווה גורם מרכזי בתקופת בית שני.",
    "edit_instructions": "Strengthen the transition. The causal link to the next paragraph is missing.",
    "constraints": ["preserve all citations", "keep paragraph count"],
    "language": "he",
}

GEMINI_SUCCESS_RESPONSE = {
    "candidates": [
        {
            "content": {
                "parts": [{"text": "Generated Hebrew prose text here."}]
            }
        }
    ]
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_http_response(body: dict, status: int = 200):
    """Return a mock that behaves like urllib.request.urlopen context manager."""
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(body).encode("utf-8")
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


def _make_http_error(code: int):
    return urllib.error.HTTPError(
        url="https://example.com",
        code=code,
        msg=f"HTTP {code}",
        hdrs={},  # type: ignore[arg-type]
        fp=io.BytesIO(b""),
    )


# ---------------------------------------------------------------------------
# Tests: load_voice_profile
# ---------------------------------------------------------------------------

class TestLoadVoiceProfile(unittest.TestCase):

    def test_load_with_writer_config(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as f:
            f.write(VOICE_MD_WITH_WRITER)
            path = f.name
        try:
            raw, config = gaw.load_voice_profile(path)
            self.assertIn("Core Voice", raw)
            self.assertEqual(config.get("provider"), "gemini")
            self.assertEqual(config.get("model"), "gemini-2.5-flash")
            self.assertAlmostEqual(float(config.get("temperature", 0)), 0.7, places=5)
            self.assertEqual(config.get("max_tokens"), 3000)
        finally:
            os.unlink(path)

    def test_load_without_writer_config(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as f:
            f.write(VOICE_MD_NO_WRITER)
            path = f.name
        try:
            raw, config = gaw.load_voice_profile(path)
            self.assertIn("Core Voice", raw)
            self.assertEqual(config, {})
        finally:
            os.unlink(path)

    def test_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            gaw.load_voice_profile("/nonexistent/path/AUTHOR_VOICE.md")


# ---------------------------------------------------------------------------
# Tests: _extract_writer_config
# ---------------------------------------------------------------------------

class TestExtractWriterConfig(unittest.TestCase):

    def test_full_block(self):
        result = gaw._extract_writer_config(VOICE_MD_WITH_WRITER)
        self.assertEqual(result["provider"], "gemini")
        self.assertEqual(result["model"], "gemini-2.5-flash")
        self.assertEqual(result["max_tokens"], 3000)

    def test_no_writer_block(self):
        result = gaw._extract_writer_config(VOICE_MD_NO_WRITER)
        self.assertEqual(result, {})

    def test_claude_provider(self):
        text = "writer:\n  provider: claude\n  model: claude-sonnet\n"
        result = gaw._extract_writer_config(text)
        self.assertEqual(result["provider"], "claude")
        self.assertEqual(result["model"], "claude-sonnet")

    def test_inline_under_heading(self):
        text = (
            "## Writer Configuration\n\n"
            "writer:\n"
            '  provider: "gemini"\n'
            '  model: "gemini-2.5-flash"\n'
            "  temperature: 0.8\n"
            "  max_tokens: 2000\n"
        )
        result = gaw._extract_writer_config(text)
        self.assertEqual(result["provider"], "gemini")
        self.assertEqual(result["max_tokens"], 2000)


# ---------------------------------------------------------------------------
# Tests: build_draft_prompt
# ---------------------------------------------------------------------------

class TestBuildDraftPrompt(unittest.TestCase):

    def test_system_contains_voice(self):
        system, _ = gaw.build_draft_prompt(VOICE_MD_WITH_WRITER, DRAFT_CONTEXT)
        self.assertIn("Core Voice", system)
        self.assertIn("Writer Configuration", system)

    def test_system_contains_word_ceiling(self):
        system, _ = gaw.build_draft_prompt(VOICE_MD_WITH_WRITER, DRAFT_CONTEXT)
        self.assertIn("200", system)

    def test_user_contains_section_outline(self):
        _, user = gaw.build_draft_prompt(VOICE_MD_WITH_WRITER, DRAFT_CONTEXT)
        self.assertIn("Second Temple", user)

    def test_user_contains_evidence(self):
        _, user = gaw.build_draft_prompt(VOICE_MD_WITH_WRITER, DRAFT_CONTEXT)
        self.assertIn("e1", user)

    def test_user_contains_vectorless_context(self):
        _, user = gaw.build_draft_prompt(VOICE_MD_WITH_WRITER, DRAFT_CONTEXT)
        self.assertIn("Elephantine", user)

    def test_user_contains_paragraph_index(self):
        _, user = gaw.build_draft_prompt(VOICE_MD_WITH_WRITER, DRAFT_CONTEXT)
        self.assertIn("2", user)

    def test_evidence_ownership_owns(self):
        _, user = gaw.build_draft_prompt(VOICE_MD_WITH_WRITER, DRAFT_CONTEXT)
        self.assertIn("e1", user)
        # "owns" should appear in the evidence ownership section
        self.assertIn("OWNS", user.upper())

    def test_no_evidence_ok(self):
        ctx = dict(DRAFT_CONTEXT)
        ctx["evidence"] = []
        ctx["evidence_ownership"] = {"owns": [], "back_reference": []}
        system, user = gaw.build_draft_prompt(VOICE_MD_WITH_WRITER, ctx)
        self.assertIsInstance(system, str)
        self.assertIsInstance(user, str)


# ---------------------------------------------------------------------------
# Tests: build_edit_prompt
# ---------------------------------------------------------------------------

class TestBuildEditPrompt(unittest.TestCase):

    def test_system_contains_voice(self):
        system, _ = gaw.build_edit_prompt(VOICE_MD_WITH_WRITER, EDIT_CONTEXT)
        self.assertIn("Core Voice", system)

    def test_system_contains_no_change_rule(self):
        system, _ = gaw.build_edit_prompt(VOICE_MD_WITH_WRITER, EDIT_CONTEXT)
        # The "do not change anything else" instruction should be present
        lower = system.lower()
        self.assertTrue(
            "do not" in lower or "only what" in lower or "exactly" in lower,
            "System prompt should contain instruction not to change anything else",
        )

    def test_system_contains_constraints(self):
        system, _ = gaw.build_edit_prompt(VOICE_MD_WITH_WRITER, EDIT_CONTEXT)
        self.assertIn("preserve all citations", system)
        self.assertIn("keep paragraph count", system)

    def test_user_contains_original_text(self):
        _, user = gaw.build_edit_prompt(VOICE_MD_WITH_WRITER, EDIT_CONTEXT)
        self.assertIn("הגולה", user)

    def test_user_contains_edit_instructions(self):
        _, user = gaw.build_edit_prompt(VOICE_MD_WITH_WRITER, EDIT_CONTEXT)
        self.assertIn("causal link", user)

    def test_no_constraints_ok(self):
        ctx = dict(EDIT_CONTEXT)
        ctx["constraints"] = []
        system, user = gaw.build_edit_prompt(VOICE_MD_WITH_WRITER, ctx)
        self.assertIsInstance(system, str)
        self.assertIsInstance(user, str)


# ---------------------------------------------------------------------------
# Tests: call_gemini_api
# ---------------------------------------------------------------------------

class TestCallGeminiApi(unittest.TestCase):

    @patch("urllib.request.urlopen")
    def test_success(self, mock_urlopen):
        mock_urlopen.return_value = _make_http_response(GEMINI_SUCCESS_RESPONSE)
        result = gaw.call_gemini_api(
            "system prompt",
            "user prompt",
            model="gemini-2.5-flash",
            api_key="test-key",
        )
        self.assertEqual(result, "Generated Hebrew prose text here.")
        self.assertEqual(mock_urlopen.call_count, 1)

    def test_missing_api_key_raises(self):
        with self.assertRaises(ValueError) as ctx:
            gaw.call_gemini_api(
                "system prompt",
                "user prompt",
                model="gemini-2.5-flash",
                api_key=None,
            )
        self.assertIn("GEMINI_API_KEY", str(ctx.exception))

    def test_empty_api_key_raises(self):
        with self.assertRaises(ValueError):
            gaw.call_gemini_api(
                "system",
                "user",
                model="gemini-2.5-flash",
                api_key="",
            )

    @patch("time.sleep")
    @patch("urllib.request.urlopen")
    def test_retry_on_429_then_success(self, mock_urlopen, mock_sleep):
        """First call returns 429; second call succeeds."""
        mock_urlopen.side_effect = [
            _make_http_error(429),
            _make_http_response(GEMINI_SUCCESS_RESPONSE),
        ]
        result = gaw.call_gemini_api(
            "system",
            "user",
            model="gemini-2.5-flash",
            api_key="test-key",
        )
        self.assertEqual(result, "Generated Hebrew prose text here.")
        self.assertEqual(mock_urlopen.call_count, 2)
        # Should have slept once (2^0 = 1 second)
        mock_sleep.assert_called_once_with(1)

    @patch("time.sleep")
    @patch("urllib.request.urlopen")
    def test_retry_exhausted_raises(self, mock_urlopen, mock_sleep):
        """All MAX_RETRIES attempts return 429; should raise HTTPError."""
        mock_urlopen.side_effect = [
            _make_http_error(429),
            _make_http_error(429),
            _make_http_error(429),
        ]
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            gaw.call_gemini_api(
                "system",
                "user",
                model="gemini-2.5-flash",
                api_key="test-key",
            )
        self.assertEqual(ctx.exception.code, 429)
        # Should have slept MAX_RETRIES - 1 times
        self.assertEqual(mock_sleep.call_count, gaw.MAX_RETRIES - 1)

    @patch("urllib.request.urlopen")
    def test_non_429_http_error_raises_immediately(self, mock_urlopen):
        """A 500 error should not be retried."""
        mock_urlopen.side_effect = _make_http_error(500)
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            gaw.call_gemini_api(
                "system",
                "user",
                model="gemini-2.5-flash",
                api_key="test-key",
            )
        self.assertEqual(ctx.exception.code, 500)
        self.assertEqual(mock_urlopen.call_count, 1)

    @patch("urllib.request.urlopen")
    def test_api_key_sent_as_header(self, mock_urlopen):
        """Verify x-goog-api-key is used as a header, not a query param."""
        mock_urlopen.return_value = _make_http_response(GEMINI_SUCCESS_RESPONSE)
        gaw.call_gemini_api(
            "system",
            "user",
            model="gemini-2.5-flash",
            api_key="my-secret-key",
        )
        req = mock_urlopen.call_args[0][0]
        self.assertEqual(req.get_header("X-goog-api-key"), "my-secret-key")
        # Key must NOT appear in the URL
        self.assertNotIn("my-secret-key", req.full_url)


if __name__ == "__main__":
    unittest.main()
