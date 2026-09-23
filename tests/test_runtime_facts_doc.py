import re, pathlib
DOC = pathlib.Path(__file__).parent.parent / "docs/refactor/runtime-facts.md"
FACTS = {"DATA_DIR_RESOLUTION": {"env", "skill-substitution-arg", "documented-path"},
         "KEY_RESOLUTION": {"CLAUDE_PLUGIN_OPTION", "skill-substitution", "env-only"},
         "FORK_MODEL": {"yes", "no"}, "OMIT_CLAUDE_MD": {"yes", "no"}, "PLUGIN_EVAL": {"yes", "no"},
         "PI_ISOLATION": {"yes", "no"}, "PI_JSON_USAGE": {"yes", "no"}, "JEV_CALL": {"yes", "no"}}

def test_every_fact_answered_from_vocabulary():
    text = DOC.read_text(encoding="utf-8")
    for fact, vocab in FACTS.items():
        m = re.search(rf"## {fact}\n(.*?)\nAnswer: (\S+)", text, re.S)
        assert m, f"{fact} missing"
        assert m.group(2) in vocab, f"{fact}: {m.group(2)} not in {vocab}"
        assert "```" in m.group(1), f"{fact}: no observed output block"
