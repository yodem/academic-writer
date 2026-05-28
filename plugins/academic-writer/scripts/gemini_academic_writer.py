#!/usr/bin/env python3
"""
Gemini API writer for academic-writer plugin.

Two modes:
  --mode draft   Generate prose from section context JSON.
  --mode edit    Rewrite existing prose per precise edit instructions.

Usage:
  python scripts/gemini_academic_writer.py \
    --mode draft \
    --voice AUTHOR_VOICE.md \
    --context /tmp/section-context.json

  python scripts/gemini_academic_writer.py \
    --mode edit \
    --voice AUTHOR_VOICE.md \
    --context /tmp/edit-context.json

Reads $GEMINI_API_KEY from environment.
Uses only stdlib (urllib, json) — zero pip dependencies.
Python 3.9+.
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from typing import Optional

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
TIMEOUT = 60
MAX_RETRIES = 3
DEFAULT_MODEL = "gemini-2.5-flash"
DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 3000


# ---------------------------------------------------------------------------
# Voice profile loading
# ---------------------------------------------------------------------------

def load_voice_profile(path: str) -> tuple[str, dict]:
    """Load AUTHOR_VOICE.md.

    Returns:
        (raw_text, writer_config)
        raw_text    — the full markdown file content (used verbatim in system prompts)
        writer_config — extracted writer: YAML block as a dict
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Voice profile not found: {path}")
    with open(path, encoding="utf-8") as f:
        raw_text = f.read()
    writer_config = _extract_writer_config(raw_text)
    return raw_text, writer_config


def _extract_writer_config(text: str) -> dict:
    """Extract the writer: YAML block from AUTHOR_VOICE.md.

    Looks for a block like:
        writer:
          provider: "gemini"
          model: "gemini-2.5-flash"
          temperature: 0.7
          max_tokens: 3000

    Returns a dict with the extracted values, or empty dict if absent.
    """
    # Find the writer: section (handles both indented block under a markdown heading
    # and a top-level yaml block)
    match = re.search(r'(?:^|\n)writer:\s*\n((?:[ \t]+\S[^\n]*\n?)+)', text)
    if not match:
        return {}
    block = match.group(1)
    result = {}
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        if ':' in stripped:
            key, _, val = stripped.partition(':')
            key = key.strip().strip('"\'')
            val = val.strip().strip('"\'')
            if val.lower() == 'true':
                val = True
            elif val.lower() == 'false':
                val = False
            else:
                try:
                    val = int(val)
                except ValueError:
                    try:
                        val = float(val)
                    except ValueError:
                        pass
            result[key] = val
    return result


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def build_draft_prompt(voice_raw: str, context: dict) -> tuple[str, str]:
    """Build system + user prompts for draft mode.

    Args:
        voice_raw: Full content of AUTHOR_VOICE.md.
        context: Parsed section-context.json dict.

    Returns:
        (system_prompt, user_prompt)
    """
    language = context.get("language", "he")
    word_ceiling = context.get("word_ceiling", 220)
    paragraph_index = context.get("paragraph_index", 1)
    section_outline = context.get("section_outline", "")
    evidence = context.get("evidence", [])
    evidence_ownership = context.get("evidence_ownership", {})
    vectorless_context = context.get("vectorless_context", "")

    system_parts = [
        "You are an academic prose writer. Write academic Hebrew prose for a humanities article.",
        "",
        "## Author Voice Profile",
        "",
        voice_raw,
        "",
        "## Evidence Ownership Rules",
        "",
        "- Evidence in `owns` list: describe fully in this paragraph.",
        "- Evidence in `back_reference` list: use a back-reference (e.g., 'כפי שנדון בחלק הקודם') — do NOT re-describe.",
        "- Never fabricate citations. Use only evidence provided below.",
        "",
        f"## Word Ceiling",
        "",
        f"This paragraph must not exceed {word_ceiling} words.",
        "If you exceed this limit, cut hedging, meta-commentary, or split the paragraph.",
        "",
        "## Output Instructions",
        "",
        "Output ONLY the final paragraph text. No commentary, no markdown headers, no JSON.",
        "Write in Hebrew (right-to-left). Use academic register.",
    ]

    user_parts = [
        f"## Section Outline",
        "",
        section_outline,
        "",
        f"## Paragraph Index",
        "",
        f"You are writing paragraph {paragraph_index} of this section.",
        "",
    ]

    if evidence:
        user_parts.extend([
            "## Evidence",
            "",
            json.dumps(evidence, ensure_ascii=False, indent=2),
            "",
        ])

    if evidence_ownership:
        owns = evidence_ownership.get("owns", [])
        back_ref = evidence_ownership.get("back_reference", [])
        user_parts.extend([
            "## Evidence Ownership",
            "",
            f"This paragraph OWNS these evidence items (describe fully): {json.dumps(owns, ensure_ascii=False)}",
            f"These must be BACK-REFERENCED only (do not re-describe): {json.dumps(back_ref, ensure_ascii=False)}",
            "",
        ])

    if vectorless_context:
        user_parts.extend([
            "## Source Passages (from Agentic Search)",
            "",
            vectorless_context,
            "",
        ])

    user_parts.append(
        f"Write paragraph {paragraph_index} now. Stay within {word_ceiling} words."
    )

    return "\n".join(system_parts), "\n".join(user_parts)


def build_edit_prompt(voice_raw: str, context: dict) -> tuple[str, str]:
    """Build system + user prompts for edit mode.

    Args:
        voice_raw: Full content of AUTHOR_VOICE.md.
        context: Parsed edit-context.json dict.

    Returns:
        (system_prompt, user_prompt)
    """
    original_text = context.get("original_text", "")
    edit_instructions = context.get("edit_instructions", "")
    constraints = context.get("constraints", [])
    language = context.get("language", "he")

    system_parts = [
        "You are an academic prose editor. Execute the given edit precisely.",
        "Do NOT change anything else — only what the instructions specify.",
        "",
        "## Author Voice Profile",
        "",
        voice_raw,
        "",
        "## Editing Rules",
        "",
        "- Execute the edit instructions exactly as given. Claude has already decided what to change.",
        "- Preserve all citations verbatim. Never remove or alter a citation.",
        "- Preserve the author's voice as described in the profile above.",
        "- Return ONLY the rewritten text. No commentary, no explanations.",
        "- Write in Hebrew (right-to-left). Maintain academic register.",
    ]

    if constraints:
        system_parts.extend([
            "",
            "## Constraints",
            "",
        ])
        for c in constraints:
            system_parts.append(f"- {c}")

    user_parts = [
        "## Original Text",
        "",
        original_text,
        "",
        "## Edit Instructions",
        "",
        edit_instructions,
        "",
        "Rewrite the text according to the instructions above.",
        "Return ONLY the rewritten text.",
    ]

    return "\n".join(system_parts), "\n".join(user_parts)


# ---------------------------------------------------------------------------
# Gemini API call
# ---------------------------------------------------------------------------

def call_gemini_api(system_prompt: str, user_prompt: str, *,
                    model: str = DEFAULT_MODEL,
                    api_key: Optional[str] = None,
                    temperature: float = DEFAULT_TEMPERATURE,
                    max_tokens: int = DEFAULT_MAX_TOKENS) -> str:
    """Call Gemini REST API and return generated text.

    Retries up to MAX_RETRIES times on 429 with exponential backoff.
    60-second timeout per request.
    API key passed via x-goog-api-key header (not URL query string).
    """
    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY is not set. "
            "Export it in your shell profile: export GEMINI_API_KEY=..."
        )
    url = f"{GEMINI_API_BASE}/{model}:generateContent"
    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"parts": [{"text": user_prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        },
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
    )
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                return body["candidates"][0]["content"]["parts"][0]["text"]
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < MAX_RETRIES - 1:
                wait = 2 ** attempt
                print(
                    f"[gemini_academic_writer] Rate limited (429), "
                    f"retrying in {wait}s (attempt {attempt + 1}/{MAX_RETRIES})...",
                    file=sys.stderr,
                )
                time.sleep(wait)
                last_error = e
                continue
            raise
    # Should not reach here, but just in case
    raise last_error  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Gemini API writer for academic-writer plugin"
    )
    parser.add_argument(
        "--mode",
        required=True,
        choices=["draft", "edit"],
        help="draft: generate new prose | edit: rewrite per instructions",
    )
    parser.add_argument(
        "--voice",
        required=True,
        help="Path to AUTHOR_VOICE.md",
    )
    parser.add_argument(
        "--context",
        required=True,
        help="Path to context JSON (section-context.json or edit-context.json)",
    )
    args = parser.parse_args()

    # Load voice profile
    voice_raw, writer_config = load_voice_profile(args.voice)

    # Read writer config (with defaults)
    model = writer_config.get("model", DEFAULT_MODEL)
    temperature = writer_config.get("temperature", DEFAULT_TEMPERATURE)
    max_tokens = writer_config.get("max_tokens", DEFAULT_MAX_TOKENS)
    api_key = os.environ.get("GEMINI_API_KEY")

    # Load context JSON
    if not os.path.isfile(args.context):
        print(f"ERROR: Context file not found: {args.context}", file=sys.stderr)
        sys.exit(1)
    with open(args.context, encoding="utf-8") as f:
        context = json.load(f)

    # Build prompts
    if args.mode == "draft":
        system_prompt, user_prompt = build_draft_prompt(voice_raw, context)
    else:  # edit
        system_prompt, user_prompt = build_edit_prompt(voice_raw, context)

    # Call Gemini
    result = call_gemini_api(
        system_prompt,
        user_prompt,
        model=model,
        api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    print(result)


if __name__ == "__main__":
    main()
