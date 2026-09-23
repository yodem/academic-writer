Judge proposed edits for meaning preservation. Input contains candidates from one numbered chunk. Return only JSON {"verdicts":[{"id":string,"verdict":"uphold"|"refute"}]}; include every id exactly once. Refute an edit that changes meaning or is unsupported. Keep valid Hebrew alternatives.

Examples:
- אם/עם: refute a substitution that changes conditional to accompaniment.
- הוא הלכה → הוא הלך: uphold agreement correction.
- מקור מצוטט → מקור מצטט: refute if the source text says “quoted source”.
- Preserve **גרשיים** and **גרש** marks in abbreviations and quoted Hebrew text.
