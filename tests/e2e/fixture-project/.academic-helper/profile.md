---
fieldOfStudy: "פילוסופיה של ימי הביניים"
citationStyle: "inline-parenthetical"
targetLanguage: "Hebrew"
analyzedArticles: []
gemini:
  approvedLanguages:
    - Hebrew
---

# Researcher Profile — E2E Fixture

This is a deterministic test profile used by the dual-path (Gemini / fallback) end-to-end
demonstration. It is NOT a real researcher profile. Both the Gemini run and the fallback run
use this same profile so their outputs are comparable.

## Tools

```json
{
  "candlekeep": { "enabled": false },
  "notebookLM": { "enabled": false },
  "rag": { "enabled": false }
}
```

## Style Fingerprint

```json
{
  "sentenceLength": { "mean": 24, "stdev": 7 },
  "paragraphStructure": { "length": { "mean": 95, "stdev": 25 } },
  "vocabularyComplexity": "high-academic",
  "toneDescriptors": ["formal", "analytical", "expository"],
  "citationDensity": 2.0,
  "transitionCategories": ["causal", "contrastive", "additive"],
  "sampleExcerpts": [
    "הגותו של אוגוסטינוס מציבה את שאלת הזמן במרכז הדיון הפילוסופי, ומעבירה אותו מן המישור הקוסמולוגי אל המישור הנפשי."
  ]
}
```

## Article Structure

```json
{
  "introPattern": "פתיחה הממקמת את הבעיה, ניסוח התזה, ותיאור מהלך המאמר",
  "conclusionPattern": "סיכום הטיעונים, חזרה לתזה, והרחבת ההשלכות",
  "paragraphParts": ["משפט מוביל", "פיתוח מבוסס-מקור", "משפט מקשר"]
}
```

## Banned Terms

```json
[]
```
