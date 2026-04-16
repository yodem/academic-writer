# Anti-AI Patterns — English Academic Writing

Reference for detecting and fixing AI-generated writing patterns in English academic prose.

Patterns here have **named numeric caps per article**. The section-writer's repetition check and the synthesizer's full-article sweep both enforce these caps. A pattern is not forbidden — it is capped. The cap is the total count allowed across the entire article, not per paragraph.

## English AI Pattern List

### A. Formulaic Hedging (scope-limiting tells)

Each of these announces what the article is NOT doing. In small doses they're legitimate academic hedging. Repeated, they become a tic.

| AI Pattern | Per-article cap | Better |
|-----------|-----------------|--------|
| "I do not address here…" | 2 | State the actual focus directly; save the caveat for a single summary in the introduction |
| "I do not pursue here…" | 2 | Same — cite once, not per section |
| "This is not my focus" | 2 | Usually redundant with the section's topic sentence |
| "I leave aside…" | 2 | Combine all set-aside topics into one introduction clause |
| "A full treatment lies beyond the scope…" | 1 | Say it once in intro, never again |
| "I do not address X here; nor do I address Y" (chained hedging) | 1 total | Keep only the primary caveat |

### B. Formulaic Author-Voice Assertion (posture tells)

| AI Pattern | Per-article cap | Better |
|-----------|-----------------|--------|
| "I suggest that…" | 3 | Mix with direct assertion: "The archive shows…", "The text reads…" |
| "I posit that…" | 2 | Plain present tense — "X is Y because Z" |
| "I argue that…" | 3 | Reserve for the thesis statement and 1-2 major claims |
| "I propose that…" | 2 | Use when genuinely introducing a new reading; not as a filler |
| Two consecutive paragraphs opening with the same assertion phrase | 0 | Vary — the second paragraph must open differently |

### C. Meta-Scholarship Openers (vague attributions)

| AI Pattern | Fix |
|-----------|-----|
| "Scholarship has tended to…" | Name the specific scholars and cite them |
| "Prior work has largely…" | Cite 2-3 specific studies |
| "It is widely acknowledged that…" | Remove — if it's widely acknowledged it doesn't need saying |
| "Scholars have long debated…" | Who debated? Cite the debate |
| "It is commonly assumed that…" | By whom? Cite or remove |

### D. Inflated Transitions (conjunctive padding)

| AI Pattern | Per-article cap | Fix |
|-----------|-----------------|-----|
| "Taken together," | 2 | Delete most instances — the connection is usually obvious |
| "Read against," | 2 | Use only when literally juxtaposing two sources |
| "In light of the foregoing," | 1 | Delete — the reader just read it |
| "It is worth noting that…" | 1 | If worth noting, note it directly |
| "It bears emphasizing that…" | 0 | Delete — emphasize by position, not meta-comment |
| "What is striking here is…" | 2 | Show the striking thing; don't announce it |

### E. Inflated Language (promotional register)

| AI Pattern | Better |
|-----------|--------|
| "a significant contribution" | State the specific contribution |
| "of paramount importance" | State why it matters concretely |
| "a groundbreaking intervention" | Describe the specific advance |
| "crucial" / "critical" (overuse) | Use sparingly — when truly load-bearing |
| "unique in its kind" | Explain what makes it unique |
| "unprecedented" (unless literally true) | Describe what preceded it |

### F. Structural Tells

| Pattern | Description | Fix |
|---------|-------------|-----|
| Abstract → Intro → Section I opener restatement | Thesis stated verbatim in 3 places | Thesis once in abstract, once in introduction, **never** in a body-section opener |
| Fully re-describing the same evidence in multiple sections | Same tablet/passage/dataset introduced twice | Describe in full in one section (the "owner"); back-reference elsewhere |
| Paragraph length > 220 words | Inflation driven by padding | Split, or cut hedging and meta-commentary |
| Identical paragraph lengths across a section | AI-like symmetry | Vary: some 80-word, some 180-word |
| List-of-three everywhere | Rule-of-three forcing | Use 2 or 4 items when the evidence supports it |
| Conclusion that mechanically recaps each section | Mirror structure | Synthesize — don't recap |
| Uniform sentence length | All sentences ~20 words | Mix short (8-12) with long (28-35) |

### G. Typography (Tier 1, auto-fix)

| Pattern | Fix |
|---------|-----|
| Em-dash (`—`) | Replace with ` - ` or restructure — AI over-uses em-dashes as a rhythm crutch |
| Straight quotes (`"…"`) | Replace with curly quotes (`"…"`) |
| Double spaces | Collapse to single space |
| Trailing whitespace on paragraph | Strip |

## Scoring Dimensions

Rate the paragraph 1–10 on each dimension. **Threshold: 35/50 to pass.**

| Dimension | Question | Low-score indicators |
|-----------|----------|----------------------|
| **Directness** | Does the text state things directly? | Filler openers, throat-clearing, chained hedging |
| **Rhythm** | Is sentence length varied? | Metronomic sentences, all same length, em-dash padding |
| **Trust** | Does it trust the reader's intelligence? | Over-explaining, stating the obvious, meta-comment ("what is striking is…") |
| **Authenticity** | Does it sound like the researcher's voice? | Generic academic register, formulaic posture, no distinctive voice |
| **Density** | Is every word earning its place? | Cuttable phrases, redundant transitions, filler |

## Before/After Examples

### Example 1: Chained hedging removal

**Before (AI):**
> I do not address here the redaction history of 2 Kings 25, nor the complex question of the Al-Yahudu archive's exact geographic relation to Nippur; these questions are not my focus. I do not pursue here the prosopography of individual Yaḫudeans, nor the detailed debate regarding the precise storage locations of individual silos.

**After (Human):**
> Redaction history, the Al-Yahudu–Nippur relation, Yaḫudean prosopography, and silo topography all lie outside the scope of this paper; I flag them once, here, and do not return to them.

### Example 2: Posture rebalancing

**Before (AI):**
> I suggest that the archive documents a standing distribution system. I suggest that this reframes Nebuchadnezzar's role. I suggest that Judah belongs to a wider imperial horizon.

**After (Human):**
> The archive documents a standing distribution system, which reframes Nebuchadnezzar's role and places Judah within a wider imperial horizon.

### Example 3: Evidence back-reference

**Before (AI, Section III re-describes Text 360):**
> Text 360 of Pedersén's 2025 edition, assembled from VAT 16283+16283a+16287+21864+22285+22328+22330 and first published in part by Weidner in 1939, records oil expenditures for Yaʾukīn, king of Yaḫudu, for five sons of the king through Qanaʾama, for eight unnamed Yaḫudeans, and for Mušallim the Yaḫudean…

**After (Human, Section III back-references):**
> The Text 360 entries discussed in Section II — Yaʾukīn, the five sons, the eight Yaḫudeans, and Mušallim — can now be set alongside the biblical deportation list of 2 Kgs 24:14–17.

### Example 4: Inflated transition trimmed

**Before (AI):**
> In light of the foregoing, it bears emphasizing that what is striking here is the administrative continuity of the Babylonian apparatus. Taken together, these tablets present a picture of imperial routine.

**After (Human):**
> These tablets present a picture of imperial routine: the Babylonian apparatus continued its work uninterrupted.

## Application Order

1. **Typography Tier 1** (auto-fix em-dashes, straight quotes).
2. **Per-paragraph scan** (section-writer Skill 6) — catch formulaic openers, inflated language, and structural tells in the paragraph in isolation.
3. **Per-paragraph cross-scan** (section-writer Skill 7) — check named patterns against `priorSectionTexts` so the cap is enforced across already-written sections.
4. **Full-article sweep** (synthesizer) — count every named pattern across the finished article. For each pattern exceeding its cap, rewrite the overflow instances.
