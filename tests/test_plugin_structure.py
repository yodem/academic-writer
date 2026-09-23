"""
Tests for Academic Writer plugin structural integrity.

Validates that all skills, agents, hooks, and configuration files are
well-formed and internally consistent. Run with: python3 -m pytest tests/
"""

import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(ROOT, "src")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _parse_skill_frontmatter(path):
    """Extract YAML frontmatter from a SKILL.md file."""
    text = _read(path)
    m = re.match(r"^---\n(.*?\n)---", text, re.DOTALL)
    if not m:
        return None
    return yaml.safe_load(m.group(1))


def _find_files(directory, pattern):
    """Recursively find files matching a glob-like pattern."""
    results = []
    for dirpath, _, filenames in os.walk(directory):
        for fn in filenames:
            if re.search(pattern, fn):
                results.append(os.path.join(dirpath, fn))
    return results


# ---------------------------------------------------------------------------
# 1. Skill validation
# ---------------------------------------------------------------------------


class TestSkills(unittest.TestCase):
    """Every skill must have valid frontmatter, name, and description."""

    SKILLS_DIR = os.path.join(SRC_DIR, "skills")

    def _skill_dirs(self):
        return [
            d
            for d in os.listdir(self.SKILLS_DIR)
            if os.path.isdir(os.path.join(self.SKILLS_DIR, d))
        ]

    def test_every_skill_has_skill_md(self):
        for d in self._skill_dirs():
            path = os.path.join(self.SKILLS_DIR, d, "SKILL.md")
            self.assertTrue(
                os.path.isfile(path), f"Skill directory '{d}' missing SKILL.md"
            )

    def test_frontmatter_is_valid_yaml(self):
        for d in self._skill_dirs():
            path = os.path.join(self.SKILLS_DIR, d, "SKILL.md")
            fm = _parse_skill_frontmatter(path)
            self.assertIsNotNone(fm, f"{d}/SKILL.md has no YAML frontmatter")

    def test_frontmatter_has_required_fields(self):
        required = {"name", "description"}
        for d in self._skill_dirs():
            path = os.path.join(self.SKILLS_DIR, d, "SKILL.md")
            fm = _parse_skill_frontmatter(path)
            if fm is None:
                continue  # caught by previous test
            missing = required - set(fm.keys())
            self.assertFalse(missing, f"{d}/SKILL.md frontmatter missing: {missing}")

    def test_user_invocable_skills_have_valid_name(self):
        """User-invocable skill names must match their directory name."""
        for d in self._skill_dirs():
            path = os.path.join(self.SKILLS_DIR, d, "SKILL.md")
            fm = _parse_skill_frontmatter(path)
            if fm and fm.get("user-invocable"):
                self.assertEqual(
                    fm["name"],
                    d,
                    f"{d}: name '{fm['name']}' must match directory name '{d}'",
                )

    def test_skill_names_are_unique(self):
        names = []
        for d in self._skill_dirs():
            path = os.path.join(self.SKILLS_DIR, d, "SKILL.md")
            fm = _parse_skill_frontmatter(path)
            if fm:
                names.append(fm["name"])
        self.assertEqual(len(names), len(set(names)), f"Duplicate skill names: {names}")

    def test_skill_body_not_empty(self):
        for d in self._skill_dirs():
            path = os.path.join(self.SKILLS_DIR, d, "SKILL.md")
            text = _read(path)
            # Strip frontmatter
            body = re.sub(r"^---\n.*?\n---\n?", "", text, flags=re.DOTALL).strip()
            self.assertGreater(
                len(body), 50, f"{d}/SKILL.md body is too short ({len(body)} chars)"
            )

    def test_referenced_agents_exist(self):
        """If a skill declares agents in frontmatter, they must exist as .md files."""
        agents_dir = os.path.join(SRC_DIR, "agents")
        for d in self._skill_dirs():
            path = os.path.join(self.SKILLS_DIR, d, "SKILL.md")
            fm = _parse_skill_frontmatter(path)
            if fm and "agents" in fm:
                for agent in fm["agents"]:
                    agent_file = os.path.join(agents_dir, f"{agent}.md")
                    # Allow agents that are used via subagent_type (general-purpose)
                    # Only check agents that should have dedicated .md files
                    if agent in (
                        "deep-reader",
                        "architect",
                        "section-writer",
                        "auditor",
                        "synthesizer",
                        "style-analyzer",
                        "editor",
                        "copyeditor",
                    ):
                        self.assertTrue(
                            os.path.isfile(agent_file),
                            f"Skill '{d}' references agent '{agent}' "
                            f"but '{agent_file}' not found",
                        )


# ---------------------------------------------------------------------------
# 2. Agent validation
# ---------------------------------------------------------------------------


class TestAgents(unittest.TestCase):
    """Agent markdown files must have a title and non-trivial content."""

    AGENTS_DIR = os.path.join(SRC_DIR, "agents")
    REQUIRED_AGENTS = [
        "deep-reader.md",
        "architect.md",
        "section-writer.md",
        "auditor.md",
        "synthesizer.md",
        "editor.md",
        "copyeditor.md",
    ]

    def test_all_required_agents_exist(self):
        for name in self.REQUIRED_AGENTS:
            path = os.path.join(self.AGENTS_DIR, name)
            self.assertTrue(os.path.isfile(path), f"Missing agent: {name}")

    def test_agents_have_title(self):
        for name in self.REQUIRED_AGENTS:
            path = os.path.join(self.AGENTS_DIR, name)
            text = _read(path)
            # Strip YAML frontmatter if present
            body = re.sub(r"^---\n.*?\n---\n?", "", text, flags=re.DOTALL).lstrip()
            self.assertTrue(
                body.startswith("# "),
                f"{name} should have a markdown heading (after frontmatter)",
            )

    def test_agents_have_input_section(self):
        for name in self.REQUIRED_AGENTS:
            path = os.path.join(self.AGENTS_DIR, name)
            text = _read(path)
            self.assertIn("## Input", text, f"{name} missing '## Input' section")

    def test_agents_have_output_section(self):
        for name in self.REQUIRED_AGENTS:
            path = os.path.join(self.AGENTS_DIR, name)
            text = _read(path)
            self.assertIn("## Output", text, f"{name} missing '## Output' section")


# ---------------------------------------------------------------------------
# 3. JSON file validation
# ---------------------------------------------------------------------------


class TestJSON(unittest.TestCase):
    """All .json files must be valid JSON."""

    def _json_files(self):
        results = []
        for dirpath, _, filenames in os.walk(ROOT):
            # Skip .git and node_modules
            if "/.git/" in dirpath or dirpath.endswith("/.git"):
                continue
            if "/node_modules/" in dirpath or dirpath.endswith("/node_modules"):
                continue
            for fn in filenames:
                if fn.endswith(".json"):
                    results.append(os.path.join(dirpath, fn))
        return results

    def test_all_json_files_parse(self):
        for path in self._json_files():
            rel = os.path.relpath(path, ROOT)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    json.load(f)
            except json.JSONDecodeError as e:
                self.fail(f"{rel}: invalid JSON — {e}")


# ---------------------------------------------------------------------------
# 4. Hook validation
# ---------------------------------------------------------------------------


class TestHooks(unittest.TestCase):
    """Hooks config and scripts must be valid."""

    HOOKS_JSON = os.path.join(SRC_DIR, "hooks", "hooks.json")
    BIN_DIR = os.path.join(SRC_DIR, "hooks", "bin")

    def test_hooks_json_is_valid(self):
        with open(self.HOOKS_JSON, "r") as f:
            data = json.load(f)
        self.assertIn("hooks", data)

    def test_hooks_json_references_existing_scripts(self):
        with open(self.HOOKS_JSON, "r") as f:
            data = json.load(f)
        for event, groups in data.get("hooks", {}).items():
            for group in groups:
                for hook in group.get("hooks", []):
                    cmd = hook.get("command", "")
                    # Extract script path from command
                    m = re.search(r"\$\{CLAUDE_PLUGIN_ROOT\}/(.+)", cmd)
                    if m:
                        script_rel = m.group(1)
                        # At runtime CLAUDE_PLUGIN_ROOT points to the
                        # built plugin dir, but at test time we verify
                        # the source equivalents exist under src/hooks/.
                        # The command is e.g. "hooks/bin/run-hook.mjs ..."
                        # so strip the first arg that isn't a file path.
                        script_file = script_rel.split()[0].strip('"')
                        # Map from plugin-relative to src-relative
                        src_path = os.path.join(SRC_DIR, script_file)
                        self.assertTrue(
                            os.path.isfile(src_path),
                            f"Hook references '{script_file}' but not found at '{src_path}'",
                        )

    def test_hook_bin_files_exist(self):
        """The hooks/bin directory should contain the run-hook entry point."""
        self.assertTrue(
            os.path.isdir(self.BIN_DIR), "src/hooks/bin/ directory not found"
        )
        run_hook = os.path.join(self.BIN_DIR, "run-hook.mjs")
        self.assertTrue(
            os.path.isfile(run_hook), "src/hooks/bin/run-hook.mjs not found"
        )


# ---------------------------------------------------------------------------
# 4b. scripts/ referenced by skills and agents must exist
# ---------------------------------------------------------------------------


class TestScriptReferences(unittest.TestCase):
    """Every scripts/*.py referenced from a skill or agent markdown file must
    actually exist under src/scripts/."""

    SCRIPTS_DIR = os.path.join(SRC_DIR, "scripts")

    # Matches "scripts/<name>.py" and "${CLAUDE_PLUGIN_ROOT}/scripts/<name>.py"
    # style references (with or without a "plugins/academic-writer/" prefix).
    SCRIPT_REF_RE = re.compile(
        r"(?:\$\{CLAUDE_PLUGIN_ROOT\}/|plugins/academic-writer/)?"
        r"scripts/([A-Za-z0-9_\-]+\.py)"
    )

    def _all_markdown_files(self):
        for subdir in ("skills", "agents"):
            base = os.path.join(SRC_DIR, subdir)
            if not os.path.isdir(base):
                continue
            for dirpath, _, filenames in os.walk(base):
                for fn in filenames:
                    if fn.endswith(".md"):
                        yield os.path.join(dirpath, fn)

    def test_referenced_scripts_exist(self):
        missing = []
        for path in self._all_markdown_files():
            text = _read(path)
            for m in self.SCRIPT_REF_RE.finditer(text):
                script_name = m.group(1)
                script_path = os.path.join(self.SCRIPTS_DIR, script_name)
                if not os.path.isfile(script_path):
                    missing.append(
                        f"{os.path.relpath(path, ROOT)} references '{script_name}'"
                    )
        self.assertEqual(
            missing,
            [],
            "Skill/agent markdown references scripts that don't exist under "
            f"src/scripts/: {missing}",
        )


# ---------------------------------------------------------------------------
# 5. CLAUDE.md consistency
# ---------------------------------------------------------------------------


class TestClaudeMD(unittest.TestCase):
    """CLAUDE.md must be consistent with actual skills and agents."""

    CLAUDE_MD = os.path.join(ROOT, "CLAUDE.md")
    SKILLS_DIR = os.path.join(SRC_DIR, "skills")
    AGENTS_DIR = os.path.join(SRC_DIR, "agents")

    def test_claude_md_exists(self):
        self.assertTrue(os.path.isfile(self.CLAUDE_MD))

    def test_all_skills_listed_in_claude_md(self):
        text = _read(self.CLAUDE_MD)
        for d in os.listdir(self.SKILLS_DIR):
            skill_path = os.path.join(self.SKILLS_DIR, d, "SKILL.md")
            if not os.path.isfile(skill_path):
                continue
            fm = _parse_skill_frontmatter(skill_path)
            if fm and fm.get("user-invocable"):
                name = fm["name"]
                # Commands use namespace format: /academic-writer:{name}
                slash = f"/academic-writer:{name}"
                self.assertIn(slash, text, f"CLAUDE.md missing slash command: {slash}")

    def test_all_agents_listed_in_claude_md(self):
        text = _read(self.CLAUDE_MD)
        required_agents = [
            "deep-reader",
            "architect",
            "section-writer",
            "auditor",
            "synthesizer",
        ]
        for agent in required_agents:
            self.assertIn(
                f"`src/agents/{agent}.md`",
                text,
                f"CLAUDE.md missing agent reference: {agent}",
            )


# ---------------------------------------------------------------------------
# 7. Plugin mirror validation
# ---------------------------------------------------------------------------


class TestPluginMirror(unittest.TestCase):
    """Plugin directory should mirror the main skills."""

    MAIN_SKILLS = os.path.join(SRC_DIR, "skills")
    PLUGIN_SKILLS = os.path.join(ROOT, "plugins", "academic-writer", "skills")

    def test_plugin_skills_dir_exists(self):
        self.assertTrue(os.path.isdir(self.PLUGIN_SKILLS))

    def test_plugin_has_all_main_skills(self):
        main_skills = set(
            d
            for d in os.listdir(self.MAIN_SKILLS)
            if os.path.isdir(os.path.join(self.MAIN_SKILLS, d))
        )
        plugin_skills = set(
            d
            for d in os.listdir(self.PLUGIN_SKILLS)
            if os.path.isdir(os.path.join(self.PLUGIN_SKILLS, d))
        )
        missing = main_skills - plugin_skills
        self.assertFalse(missing, f"Plugin missing skill mirrors: {missing}")

    def test_plugin_skill_names_match_main(self):
        """Skill names in plugin must match main."""
        for d in os.listdir(self.MAIN_SKILLS):
            main_path = os.path.join(self.MAIN_SKILLS, d, "SKILL.md")
            plugin_path = os.path.join(self.PLUGIN_SKILLS, d, "SKILL.md")
            if not os.path.isfile(main_path):
                continue
            if not os.path.isfile(plugin_path):
                continue  # caught by previous test
            main_fm = _parse_skill_frontmatter(main_path)
            plugin_fm = _parse_skill_frontmatter(plugin_path)
            if main_fm and plugin_fm:
                self.assertEqual(
                    main_fm["name"],
                    plugin_fm["name"],
                    f"Skill '{d}' name mismatch: main='{main_fm['name']}' "
                    f"plugin='{plugin_fm['name']}'",
                )


# ---------------------------------------------------------------------------
# 8. Cross-reference validation
# ---------------------------------------------------------------------------


class TestCrossReferences(unittest.TestCase):
    """Validate references between skills, agents, and CLAUDE.md."""

    def test_section_writer_skill_pipeline_matches_workflow(self):
        """Section writer skill list must match workflow node children."""
        sw_path = os.path.join(SRC_DIR, "agents", "section-writer.md")
        text = _read(sw_path)
        # Check all 5 skills are mentioned
        skills = [
            "DRAFT",
            "STYLE FINGERPRINT COMPLIANCE",
            "GRAMMAR CHECK",
            "REPETITION CHECK",
            "CITATION AUDIT",
        ]
        for skill in skills:
            self.assertIn(skill, text, f"section-writer.md missing skill: {skill}")

    def test_write_article_references_all_pipeline_skills(self):
        wa_path = os.path.join(SRC_DIR, "skills", "write", "SKILL.md")
        text = _read(wa_path)
        skills = [
            "Draft",
            "Style Compliance",
            "Grammar Check",
            "Repetition Check",
            "Citation Audit",
        ]
        for skill in skills:
            self.assertIn(
                skill, text, f"write-article SKILL.md missing reference to: {skill}"
            )

    def test_help_lists_all_slash_commands(self):
        """Help skill must list every user-invocable skill."""
        help_path = os.path.join(SRC_DIR, "skills", "help", "SKILL.md")
        help_text = _read(help_path)
        skills_dir = os.path.join(SRC_DIR, "skills")
        for d in os.listdir(skills_dir):
            skill_path = os.path.join(skills_dir, d, "SKILL.md")
            if not os.path.isfile(skill_path):
                continue
            fm = _parse_skill_frontmatter(skill_path)
            if fm and fm.get("user-invocable"):
                # Commands use namespace format: /academic-writer:{name}
                slash = f"/academic-writer:{fm['name']}"
                self.assertIn(slash, help_text, f"Help skill missing command: {slash}")


# ---------------------------------------------------------------------------
# 9. Marketplace / plugin.json validation
# ---------------------------------------------------------------------------


class TestPluginMetadata(unittest.TestCase):
    """Plugin metadata files must be valid."""

    def test_marketplace_json(self):
        path = os.path.join(ROOT, ".claude-plugin", "marketplace.json")
        with open(path, "r") as f:
            data = json.load(f)
        self.assertIn("name", data)
        self.assertIn("plugins", data)
        self.assertIsInstance(data["plugins"], list)
        self.assertGreater(len(data["plugins"]), 0)

    def test_plugin_json(self):
        path = os.path.join(
            ROOT, "plugins", "academic-writer", ".claude-plugin", "plugin.json"
        )
        with open(path, "r") as f:
            data = json.load(f)
        self.assertIn("name", data)
        self.assertIn("version", data)
        self.assertIn("description", data)


# ---------------------------------------------------------------------------
# 10. Script smoke tests
# ---------------------------------------------------------------------------


class TestScriptSmoke(unittest.TestCase):
    """Basic end-to-end smoke tests for the deterministic Python scripts."""

    SCRIPTS_DIR = os.path.join(SRC_DIR, "scripts")

    def test_detect_ai_typography_fixes_sample_text(self):
        script = os.path.join(self.SCRIPTS_DIR, "detect-ai-typography.py")
        sample = 'זהו משפט לדוגמה — עם "מרכאות" רגילות.'
        proc = subprocess.run(
            [sys.executable, script, "--fix-and-output", "--json"],
            input=sample,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(proc.stdout)
        self.assertIn("fixed_text", data)
        self.assertIn("fixes", data)
        self.assertIsInstance(data["fixes"], list)
        self.assertGreater(len(data["fixes"]), 0, "Expected em-dash fix to be reported")
        self.assertNotIn("—", data["fixed_text"], "em-dash should have been fixed")

    def test_detect_ai_typography_no_fixes_still_valid_json(self):
        script = os.path.join(self.SCRIPTS_DIR, "detect-ai-typography.py")
        sample = "טקסט נקי ללא בעיות טיפוגרפיה."
        proc = subprocess.run(
            [sys.executable, script, "--fix-and-output", "--json"],
            input=sample,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(proc.stdout)
        self.assertEqual(data["fixed_text"], sample)
        self.assertEqual(data["fixes"], [])

    def test_extract_style_metrics_on_temp_corpus(self):
        script = os.path.join(self.SCRIPTS_DIR, "extract-style-metrics.py")
        with tempfile.TemporaryDirectory() as tmpdir:
            article_path = os.path.join(tmpdir, "article1.md")
            with open(article_path, "w", encoding="utf-8") as f:
                f.write(
                    "במאמר זה אבחן את התופעה המרכזית. הטענה שלי היא כי הנושא מורכב.\n\n"
                    "בנוסף, יש לציין כי ישנם מקורות רבים. לעומת זאת, חוקרים אחרים "
                    "טוענים אחרת. לכן יש לבחון את הראיות בזהירות.\n\n"
                    "לסיכום, המאמר מציג ניתוח מקיף של הנושא הנדון.\n"
                )
            proc = subprocess.run(
                [sys.executable, script, "--input", tmpdir, "--aggregate", "--json"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            data = json.loads(proc.stdout)

            self.assertIn("computationalMetrics", data)
            metrics = data["computationalMetrics"]
            self.assertIn("sentenceLevel", metrics)
            self.assertIn("length", metrics["sentenceLevel"])
            self.assertIn("mean", metrics["sentenceLevel"]["length"])
            self.assertIn("stdev", metrics["sentenceLevel"]["length"])
            self.assertIn("distribution", metrics["sentenceLevel"])
            self.assertIn("passiveVoiceFrequency", metrics["sentenceLevel"])
            self.assertIn("firstPersonFrequency", metrics["sentenceLevel"])
            self.assertIn("paragraphStructure", metrics)
            self.assertIn("length", metrics["paragraphStructure"])
            self.assertIn("transitions", metrics)
            self.assertIn("frequencyPerParagraph", metrics["transitions"])
            self.assertIn("byCategory", metrics["transitions"])
            self.assertIn("vocabulary", metrics)

            self.assertIn("frequentTerms", data)
            self.assertIsInstance(data["frequentTerms"], list)
            self.assertGreater(len(data["frequentTerms"]), 0)


if __name__ == "__main__":
    unittest.main()
