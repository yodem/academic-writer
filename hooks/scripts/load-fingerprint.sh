#!/bin/bash
# Academic Writer — Load Style Fingerprint at Session Start
# This hook ensures the researcher's fingerprint is always visible and loaded
# into context at the beginning of every session.

PROFILE_PATH=".academic-writer/profile.json"

if [ ! -f "$PROFILE_PATH" ]; then
  exit 0  # No profile yet — check-profile.sh handles the warning
fi

# Extract and display the fingerprint summary
python3 << 'PYTHON'
import json, sys

try:
    with open(".academic-writer/profile.json", "r") as f:
        profile = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    sys.exit(0)

fp = profile.get("styleFingerprint")
if not fp:
    print("Academic Writer: Profile exists but has no style fingerprint. Consider re-running /academic-writer-init.")
    sys.exit(0)

field = profile.get("fieldOfStudy", "Unknown")
citation = profile.get("citationStyle", "Unknown")

print("=" * 60)
print("ACADEMIC WRITER — RESEARCHER PROFILE LOADED")
print("=" * 60)
print(f"Field: {field}")
print(f"Citation style: {citation}")
print()

# Handle both old flat format and new nested format
if isinstance(fp.get("sentenceLevel"), dict):
    # New expanded format
    sl = fp["sentenceLevel"]
    vr = fp.get("vocabularyAndRegister", {})
    ps = fp.get("paragraphStructure", {})
    tv = fp.get("toneAndVoice", {})
    tr = fp.get("transitions", {})
    ci = fp.get("citations", {})
    rp = fp.get("rhetoricalPatterns", {})

    print("STYLE FINGERPRINT:")
    print("-" * 40)
    print(f"  Sentence length: {sl.get('averageLength', 'N/A')}")
    print(f"  Structure variety: {sl.get('structureVariety', 'N/A')}")
    print(f"  Passive voice: {sl.get('passiveVoice', 'N/A')}")
    print(f"  Vocabulary: {vr.get('complexity', 'N/A')}")
    print(f"  Register: {vr.get('registerLevel', 'N/A')}")
    if vr.get("hebrewConventions"):
        print(f"  Hebrew conventions: {vr['hebrewConventions']}")
    print(f"  Paragraph pattern: {ps.get('pattern', 'N/A')}")
    print(f"  Argument progression: {ps.get('argumentProgression', 'N/A')}")
    print(f"  Tone: {', '.join(tv.get('descriptors', [])) or 'N/A'}")
    print(f"  Author stance: {tv.get('authorStance', 'N/A')}")
    print(f"  Citation density: {ci.get('density', 'N/A')} (~{ci.get('footnotesPerParagraph', '?')}/paragraph)")
    print(f"  Quote style: {ci.get('quoteLengthPreference', 'N/A')}")
    if rp.get("common"):
        print(f"  Rhetorical patterns: {', '.join(rp['common'])}")

    # Show preferred transitions grouped
    pref = tr.get("preferred", {})
    if any(pref.values()):
        print()
        print("  Preferred transitions:")
        for cat, phrases in pref.items():
            if phrases:
                print(f"    {cat}: {', '.join(phrases)}")

    # Show representative excerpts
    excerpts = fp.get("representativeExcerpts", [])
    if excerpts:
        print()
        print("  Representative excerpts (style targets):")
        for i, ex in enumerate(excerpts[:3], 1):
            # Truncate long excerpts for display
            display = ex[:150] + "..." if len(ex) > 150 else ex
            print(f"    {i}. \"{display}\"")

else:
    # Old flat format — still display what we can
    print("STYLE FINGERPRINT:")
    print("-" * 40)
    print(f"  Sentence length: {fp.get('averageSentenceLength', 'N/A')} words")
    print(f"  Vocabulary: {fp.get('vocabularyComplexity', 'N/A')}")
    print(f"  Passive voice: {fp.get('passiveVoiceFrequency', 'N/A')}")
    print(f"  Paragraph structure: {fp.get('paragraphStructure', 'N/A')}")
    print(f"  Citation density: {fp.get('citationDensity', 'N/A')}")
    tone = fp.get("toneDescriptors", [])
    if tone:
        print(f"  Tone: {', '.join(tone)}")
    transitions = fp.get("preferredTransitions", [])
    if transitions:
        print(f"  Transitions: {', '.join(transitions[:8])}")
    patterns = fp.get("rhetoricalPatterns", [])
    if patterns:
        print(f"  Rhetorical patterns: {', '.join(patterns)}")
    excerpts = fp.get("sampleExcerpts", [])
    if excerpts:
        print()
        print("  Representative excerpts:")
        for i, ex in enumerate(excerpts[:3], 1):
            display = ex[:150] + "..." if len(ex) > 150 else ex
            print(f"    {i}. \"{display}\"")

print()
print("=" * 60)
print("This fingerprint is checked against every paragraph during writing.")
print("Update with /academic-writer-init (full) or edit .academic-writer/profile.json directly.")
print("=" * 60)
PYTHON
