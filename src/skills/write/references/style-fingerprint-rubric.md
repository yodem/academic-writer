# Style Fingerprint Compliance Rubric (10 dimensions)

> Loaded on demand by the section-writer per-paragraph pipeline (Skill 2). Pass threshold is `compliance ≥ 0.70`. Threshold for individual dimensions: `thresholds.json:styleFingerprint.passThreshold` (default 7/10).

## Layers

The fingerprint contains two layers:
1. **Computational metrics** (`computationalMetrics`) — hard numbers from the extraction script
2. **Qualitative analysis** (`qualitativeAnalysis`) — LLM-interpreted patterns and templates

Use BOTH layers for compliance checking.

## Numerical Compliance (Dimensions 1–6)

For the drafted paragraph, **count** the following and compare against the fingerprint's `computationalMetrics`:

1. **Sentence length** — Count words per sentence. Compare the mean against `computationalMetrics.sentenceLevel.length.mean`. Tolerance: ±1 stdev (`computationalMetrics.sentenceLevel.length.stdev`). If outside tolerance, restructure sentences.

2. **Sentence length variation** — Check that sentence lengths vary. Compare distribution against `computationalMetrics.sentenceLevel.distribution`. If all sentences same length (±3 words), flag as AI-like and add variety.

3. **Passive voice** — Count passive constructions (nif'al/pu'al/huf'al patterns). Compare frequency against `computationalMetrics.sentenceLevel.passiveVoiceFrequency`.

4. **First-person usage** — Count first-person markers (אני, לדעתי, אסביר, etc.). Compare against `computationalMetrics.sentenceLevel.firstPersonFrequency`.

5. **Transitions** — Count transition phrases per category. Compare total against `computationalMetrics.transitions.frequencyPerParagraph`. Phrases must come from the researcher's actual vocabulary (`computationalMetrics.transitions.byCategory`). **Do not use transitions the researcher doesn't use.**

6. **Paragraph length** — Count total words. Compare against `computationalMetrics.paragraphStructure.length.mean`. Tolerance: ±1 stdev.

## Qualitative Compliance (Dimensions 7–10)

7. **Paragraph formula** — Does the paragraph follow `qualitativeAnalysis.paragraphFormula`? (e.g., "claim → textual quotation with source → analytical interpretation → thesis connection")

8. **Evidence handling** — Does evidence introduction match `qualitativeAnalysis.evidenceHandling`? (e.g., "direct quotation → interpretation via כלומר → connection to thesis")

9. **Tone & stance** — Does the tone match `qualitativeAnalysis.toneDescriptors`? Is the authorial stance consistent with `qualitativeAnalysis.authorStance`? Use hedging/asserting phrases from `qualitativeAnalysis.hedgingPhrases` and `qualitativeAnalysis.assertingPhrases`.

10. **Templates** — Does the paragraph's rhetorical structure match one of the `templates`? When writing claims, follow `templates.assertiveClaim`. When arguing against a scholar, follow `templates.dialecticalArgument`. When analyzing a text, follow `templates.textualAnalysis`.

## Scoring

**Numerical dimensions (1-6):** Each scores PASS (within tolerance) or FAIL (outside). Compute:
```
numerical_compliance = (# PASS dimensions) / 6
```

**Qualitative dimensions (7-10):** Rate each 1-5. Compute:
```
qualitative_score = sum(dimensions) / 20
```

**Overall compliance:**
```
compliance = (numerical_compliance * 0.5) + (qualitative_score * 0.5)
```

**Pass threshold: compliance ≥ 0.70.** If below 0.70, rewrite the failing dimensions.

## Contrastive Awareness

Check the `contrastive` section of the fingerprint. Any dimension marked `distinctively_high` or `distinctively_low` is what makes this researcher's writing UNIQUE. These are the most important dimensions. If the researcher is "distinctively high" on transition frequency, the paragraph MUST have transitions. If "distinctively low" on passive voice, avoid passive constructions aggressively.

**Always refer to `representativeExcerpts`** as concrete style models. When rewriting, the excerpts are your target.
