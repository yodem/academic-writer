# Anti-AI Patterns — Hebrew Academic Writing

Reference for detecting and fixing AI-generated writing patterns in Hebrew academic prose.

## Hebrew AI Pattern List

### A. Formulaic Openers (פתיחות שבלוניות)

| AI Pattern | Why it's a tell | Better alternatives |
|-----------|----------------|-------------------|
| `אין ספק כי` | Overly assertive, avoids nuance | `נראה כי`, `ניתן לטעון ש`, direct statement |
| `חשוב לציין ש` | Filler — if it's important, just state it | Delete and state the point directly |
| `ראוי להדגיש כי` | Same — emphasizes nothing | `יש לשים לב ל`, or remove entirely |
| `יש לציין כי` | Throat-clearing opener | Remove — start with the actual content |
| `ראשית יש לומר ש` | Announces structure instead of showing it | Start with the substance |
| `כפי שידוע` | Assumes shared knowledge — vague | Cite the specific source or remove |
| `ברור כי` / `מובן מאליו ש` | Hides lack of evidence | Provide evidence instead |
| `מבחינת ה-X` (as a paragraph opener) | Labels the topic instead of stating content; classic AI tell when AI structures a paragraph by topic-tag | Open the paragraph with the substantive claim; e.g., instead of "מבחינת המבנה הפיזי, הקמת המקדש החלה במזבח" → "הקמת המקדש החלה במזבח". **Per-paragraph cap: 0 as opener.** |
| First-paragraph opener that is NOT the profile-defined `opening_formula` | Article must open with the formula (Hebrew default: "במאמר זה" + first-person singular verb). A historical-context preamble before the formula is a tell that the model added background instead of stating scope. | Open the article literally with the words "במאמר זה אבחן/אסקור/אנתח/אציג…". No prelude. **Per-article cap: 0 violations.** |

### B. Excessive Conjunctive Phrases (מילות קישור עודפות)

| AI Pattern | Problem | Fix |
|-----------|---------|-----|
| `יתרה מכך` (overuse) | AI uses this 3-4x per paragraph | Max once per section; vary with `בנוסף`, `כמו כן`, `אף` |
| `זאת ועוד` (overuse) | Same — becomes a verbal tic | Replace with direct connection or restructure sentence |
| `מצד אחד... מצד שני` | Formulaic binary structure | Present the tension directly without signaling it |
| `לא רק... אלא גם` | Rule-of-two pattern, predictable | Restructure: state both points in a single flowing sentence |
| `בהקשר זה` | Filler transition | Delete — if the paragraph follows logically, no transition needed |

### C. Promotional/Inflated Language (שפה מנופחת)

| AI Pattern | Better |
|-----------|--------|
| `תרומה משמעותית ביותר` | `תרומה` or specify what's significant |
| `חשיבות עליונה` | State why it matters concretely |
| `פריצת דרך מהפכנית` | Describe the specific advance |
| `מכריע` / `קריטי` (overuse) | Use sparingly — when truly critical |
| `ייחודי במינו` | Explain what makes it unique |

### D. Vague Attributions (ייחוסים מעורפלים)

| AI Pattern | Fix |
|-----------|-----|
| `חוקרים רבים טוענים כי` | Name the specific scholars and cite them |
| `כפי שנמצא במחקרים רבים` | Cite 2-3 specific studies |
| `על פי מיטב הידע הקיים` | Remove — all claims should be cited anyway |
| `נהוג לחשוב ש` | Who thinks this? Cite the source |
| `ידוע בספרות המחקר ש` | Which literature? Be specific |

### E. Structural Tells (סממנים מבניים)

| Pattern | Description | Fix |
|---------|------------|-----|
| Identical paragraph lengths | All paragraphs ~100 words | Vary: some 60, some 150 |
| Symmetric sections | Each section has exactly 3 paragraphs | Vary paragraph count per section |
| List-of-three | AI forces three items everywhere | Use 2 or 4 items |
| Mirror conclusions | Conclusion mechanically restates each section | Synthesize — don't recap |
| Uniform sentence length | All sentences ~20 words | Mix short (8-10) with long (30+) |

### F. Editorial Meta-Summary & Unprompted Synthesis (פרשנות לא מתבקשת ומשפטי-מטה)

The model often inserts a "wrap-up" sentence that summarises a figure, motif, or pattern, or projects forward to "future research." These sentences add no source-grounded content; they are filler that signals the model's presence rather than the researcher's analysis. **Cap any of these patterns at 0 unless the researcher's outline explicitly requests interpretation.**

| AI Pattern | Per-paragraph cap | Better |
|-----------|-------------------|--------|
| `דמותו/ה/ם של X מסכמ/ת/ים את Y` | 0 | Delete. If the synthesis matters, state the specific evidence directly. |
| `X משקפ/ת/ים את Y` (as a closer that summarises rather than evidences) | 0 | Delete or replace with the specific verses/sources that ground the claim. |
| `ומכאן עולה דפוס/תופעה/מסקנה...` | 0 | Delete. If a pattern truly emerges, the preceding sentences should already show it. |
| `הראוי לבחינה מדוקדקת` / `ראוי לעיון נוסף` / `ראוי להידרש בעתיד` | 0 | Delete. Future-research punts are AI tells. |
| `ניתן ללמוד כי...` / `ניתן לראות כי...` introducing an interpretation NOT asked for in the assignment | 0 | Delete the sentence, or hedge a claim that IS in the source. **Note:** these phrases ARE part of the researcher's hedging vocabulary when commenting on what a quoted source itself says — the violation is using them to add unprompted opinion beyond the assignment scope. |
| `בכך ניתן לראות` / `מתוך כך נראה` introducing meta-commentary | 0 | Delete. |

### G. Unsourced Factual Assertions (טענות לא מבוססות במקורות)

**Hard rule.** Every non-trivial factual claim in the article must trace either to (a) a quoted primary text in the assignment, or (b) a `sources.json` entry the researcher provided. Claims about archaeology, architectural technique, historical context, dating, geography, or scholarly consensus that are not supported this way are AI hallucinations even when they sound plausible.

**Detection cues:**
- Statements like "טכניקה מוכרת ב…" / "כידוע בארכיאולוגיה של…" / "מקובל לתארך…" / "השוואה לממצאים בני התקופה מלמדת…" without a citation.
- Adjectives that imply scholarly consensus (`מקובל`, `ידוע`, `מוכר`) with no attribution.
- Inferred dating, dimensions, or material-culture claims that go beyond what the verse itself states.

**Action when detected:**
1. If the claim CAN be supported from a source the deep-reader read or from `sources.json`, add the inline citation.
2. If it cannot, either remove the sentence or replace the claim with `[NEEDS REVIEW: source for "<claim>"]` and surface it to the researcher in the self-review report.
3. **Never paraphrase the claim more cautiously and leave it in.** Cautious phrasing of an unsourced assertion is still an unsourced assertion.

**Per-article cap: 0.**

### H. Topic Drift & Padding (סטייה מהנושא ומילוי)

When the assignment specifies the questions to answer, the model often pads with adjacent detail that signals "thoroughness" but was not requested. Cap such material aggressively.

| AI Pattern | Per-section cap | Better |
|-----------|-----------------|--------|
| Quantitative trivia not requested (e.g., "מאה עשרים ושמונה משוררים", "מאה שלשים ותשעה שוערים") when the assignment asks for *roles and what each group did* | 0 | Describe the role and the action: `הכהנים — הקריבו את הקרבנות, נשאו חצוצרות בחנוכת היסוד, נטהרו לקראת הפסח (עזרא, ו, כ).` Drop the headcount. |
| Background context preceding the article's stated scope (e.g., "בשנת 538 לפנה"ס פרסם כורש…" before "במאמר זה…") | 0 | The article opens with scope, not history. If the historical fact matters, fold it into the substantive paragraphs. |
| Sentences explaining what the article will/won't do beyond the roadmap sentence | 0 | The opening roadmap states the plan once. No further meta-narration. |

## Scoring Dimensions

Rate the paragraph 1-10 on each dimension. **Threshold: 35/50 to pass.**

| Dimension | Question | Low score indicators |
|-----------|----------|---------------------|
| **Directness** (ישירות) | Does the text state things directly? | Filler openers, throat-clearing, excessive hedging |
| **Rhythm** (קצב) | Is sentence length varied? | Metronomic sentences, all same length |
| **Trust** (אמון בקורא) | Does it trust the reader's intelligence? | Over-explaining, stating the obvious, hand-holding |
| **Authenticity** (אותנטיות) | Does it sound like the researcher's voice? | Generic academic language, no distinctive voice |
| **Density** (צפיפות) | Is every word earning its place? | Cuttable phrases, redundant connectors, filler |

## Before/After Examples

### Example 1: Filler opener removal

**Before (AI):**
> חשוב לציין כי הגישה הפילוסופית של קאנט תרמה תרומה משמעותית ביותר להבנת מושג המוסר. אין ספק כי הרעיונות שהעלה שינו את פני הפילוסופיה המערבית.

**After (Human):**
> הגישה הפילוסופית של קאנט עיצבה מחדש את הבנת מושג המוסר. הרעיונות שהעלה — בייחוד האימפרטיב הקטגורי — הפכו לאבני יסוד בפילוסופיה המערבית (קאנט, ביקורת התבונה המעשית, עמ' 42).

### Example 2: Breaking binary structure

**Before (AI):**
> מצד אחד, ניתן לראות בטקסט ביטוי לתפיסה דתית מסורתית. מצד שני, ישנם מאפיינים המצביעים על השפעות חילוניות. יתרה מכך, השילוב בין שני הזרמים מעיד על מורכבות הטקסט.

**After (Human):**
> הטקסט שוזר תפיסות דתיות מסורתיות עם מוטיבים חילוניים — שזירה המעידה על המתח התרבותי שבו נוצר. לדוגמה, הפסוקים הראשונים מזכירים מושגים תלמודיים, אך מבנה הטיעון מאזכר רטוריקה משכילית (כהן, בין קודש לחול, עמ' 78).

### Example 3: Removing inflated language

**Before (AI):**
> המחקר מציג תרומה ייחודית במינה להבנת הנושא. חשיבותו העליונה טמונה בכך שהוא מספק פריצת דרך מהפכנית בתחום.

**After (Human):**
> המחקר מציע קריאה חדשה בטקסט, הממקמת אותו בהקשר ההיסטורי של אמצע המאה השמונה עשרה — הקשר שלא נבחן בספרות הקודמת.
