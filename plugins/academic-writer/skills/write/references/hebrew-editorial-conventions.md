# Hebrew editorial conventions — suggestions for the drafter and the proofreader

Distilled from a professional Hebrew editor's review of one seminar paper (about 1,650 edits, 70
rules, each re-checked against the edit counts and against the author's ten past articles). This is
the evidence of **one editor on one paper**. Treat every item as a **suggestion**: the drafter
prefers it, the proofreader proposes it, the author confirms. **Nothing here is auto-replaced.**

Items are tagged `(R-NN)` for traceability. Citation and bibliography conventions are not here: they
live in the opt-in venue profile `bar-ilan-seminar-apa-he` (`src/venues/`).

## How to use this file

- **Drafter:** write toward these preferences; do not over-correct. The author's own wording and
  past articles win: if the author consistently writes the other form, leave it.
- **Proofreader:** propose a change as a candidate, with `after` filled in and `meaningRisk`
  **"medium"**, class `register`, `collocation`, `syntax` or `punctuation`, never `wrong_word`
  and never `low`. Medium risk is reported but not applied. The author decides.
- **Never** touch quotations, citations, footnote markers, bibliography entries or titles, unless
  the item says otherwise. A closed word list must be matched on word boundaries, prefix-aware
  (ו ה ב כ ל מ ש), never as a substring.
- A regex hit is a prompt to read the sentence, not a defect. Most of the hint patterns behind these
  items fire mostly on correct Hebrew in the author's past articles (see the cautions at the end).
- **After any word replacement** (yours, a redraft, or an accepted suggestion), re-check agreement
  and inflected or prefixed forms of the new word (R-15, below).

## Defaults owned elsewhere (one place to read)

Short summaries; the owning file has the detail and the code.

- **Dash.** The spaced em dash ` — ` is the Hebrew dash for an aside. Fix a spaced hyphen used as a
  dash to ` — `. Hyphens inside compounds, numeric en-dash ranges (`עמ׳ 12–14`), bullets and URLs
  stay. Do not overuse dashes: use one only for a true aside, otherwise a comma or a colon.
  BEFORE → AFTER: `מסורת חז״ל - משנה ידיים` → `מסורת חז״ל — משנה ידיים`. (R-02, R-07)
- **Quotes.** Straight `"` around Hebrew quotations, scare-quoted Hebrew terms and Hebrew titles;
  curly `“…”` around Latin-script ones. `״` and `׳` only inside abbreviations and acronyms
  (`הרמב״ם`, `חז״ל`, `ר׳`). A straight quote attached to a one- or two-letter prefix with a
  closing quote later on the line is an opener (`ב"פרשה"`), not gershayim. BEFORE → AFTER:
  `“לא היו”` → `"לא היו"`. (R-01, R-08)
- **Connectives are logic, not a quota.** Each connective states a real relation (reason `שכן`,
  consequence `לכן`, contrast `אולם`, addition `ועוד`). Replace a vague link (`וכך`, `והוא`, `ממנו`)
  with the relation the argument needs; never add a link to meet a count. Do not mint rules about
  `אפוא` or `ראשית/שנית`. BEFORE → AFTER: `הוא אינו מצטט מקור, וכך נוצרת תחושת קרבה` → `הוא אינו
  מצטט מקור, ולכן אין לבסס טענה על קרבה ישירה`. (R-32; list in `words-hebrew.md`)

## 1. Punctuation

### 1.1 No comma before the vav of the last list member (R-04)
- **Principle:** in a list of three or more, and between two coordinated nouns or verbs, no comma
  before the ו of the last member. `לא X, לא Y ולא Z` takes `ולא` with no comma.
- `רובד לשוני, ספרותי, ופרשני` → `רובד לשוני, ספרותי ופרשני`
- `לא בשפה, לא בסגנון, ולא בתוכן` → `לא בשפה, לא בסגנון ולא בתוכן`
- **Scope:** a comma before a ו that opens a new independent clause stays (`הפירוש נדחה, והקריאה
  החלופית התקבלה`). Do not flag `, ו` by pattern: it is correct in most places. Removing a repeated
  vav (polysyndeton) is a judgement call. Do not extend this to "no vav after a semicolon".

### 1.2 Commas around discourse markers (R-05)
- **Principle:** the parenthetical `אפוא` is set off by commas on both sides.
- `פרשה היא אפוא מסגרת ביניים` → `פרשה היא, אפוא, מסגרת ביניים`
- **Optional:** a comma before contrastive `אלא` after a long preceding clause: `אינה ספרותית בלבד
  אלא מוסרית` → `אינה ספרותית בלבד, אלא מוסרית`.
- **Scope:** exclusive `אינו אלא` takes no comma. `כך למשל` and `כך, למשל` are both the author's
  usage; leave either. The comma before `אלא` is the editor's habit in only part of the cases.

### 1.3 A Hebrew letter as an ordinal in running prose (R-06) — weak
- **Principle:** a single letter used as an ordinal in running prose may take a geresh.
- `בסעיף א` → `בסעיף א׳`
- **Scope:** low priority. Suggest it only when the article already uses the geresh form for most
  prose positions. Never in headings, table-of-contents lines, parenthetical locators or the
  bibliography. The author's bare form is common (23 bare against 12 with geresh in the corpus).

### 1.4 Commas between all fields of a source locator (R-42, part a)
- **Principle:** commas between all fields of a locator, extended from Bible references (already in
  `anti-ai-patterns-hebrew.md` §J) to non-Bible text, when the tractate or work is not already named
  in the sentence.
- `(שבועות מח א)` → `(שבועות, מח, א)`; `(במדבר טו טו)` → `(במדבר, טו, טו)`
- **Scope:** when the sentence names the work (`במסכת שבועות נאמר`), `(מח, א)` is fine. `(שם, X)` is
  an ibid reference, not a bare locator. Do not pin geresh or gershayim on the letters. Adding the
  book name to a bare `(chapter, verse)` is a venue option (the bundled profile), not a default.

## 2. Spelling and word forms

### 2.1 Full (Academy) spelling in the author's own prose (R-13)
- **Principle:** in the author's prose only, use full spelling for this **closed** list, matched on
  word boundaries with prefixes: `ידים`→`ידיים`, `תצוה`→`תצווה`, `ארסטו`/`הארסטוטלית`→`אריסטו`/
  `האריסטוטלית`, `מטתו`→`מיטתו`, `המעין`→`המעיין`, `מצדו`→`מצידו`, `לצדן`→`לצידן`,
  `במלים`/`כמלים`→`במילים`/`כמילים`, `ששים`→`שישים` only when it is the number (it is also the valid participle "rejoicing"), `שנדונו`→`שנידונו`,
  `צרכי`→`צורכי`, `ירושלם`→`ירושלים` outside quotations, `כתבי הקדש`→`כתבי הקודש`.
- **Scope:** never inside quotations, citations or the bibliography (source spelling stays). Leave
  `אפריון`/`אפיריון` (biblical and Talmudic forms differ), `מקרו`/`מאקרו`, `פרובנס`/`פרובאנס`, and
  bare `הקדש` (a valid word: `ההקדש`, `הקדש` as an endowment).

### 2.2 Definite article on proper corpora, technical terms and ordinals (R-14)
- **Principle:** in running prose a bare noun that names a corpus, a work or a technical term takes
  the article, and list members stay parallel in definiteness.
- `רמב״ם הוא סמכותו הפילוסופית` → `הרמב״ם הוא סמכותו הפילוסופית`
- `שכל פועל` → `השכל הפועל`; `מבית סוהר` → `מבית הסוהר`
- **Scope:** do not touch titles (course names, `תלמוד בבלי, גיטין ח ע״א`), quotations or citation
  forms. A substring replacement is a hazard here: `הרמב״ם` and `ברמב״ם` are already correct.

### 2.3 Spell out abbreviated titles and locator words (R-16)
- **Principle:** in prose and citations (not in quotations) expand this closed list: `מו״נ`/`מו״ן` and
  a bare `במורה` → `מורה נבוכים`; `שה״ש רבה` → `שיר השירים רבה`; `ע״ז` → `עבודה זרה`; `פס׳` →
  `פסקה`/`פסקאות`; `כ״י` → `כ״י (כתב יד)` at first use.
- `מתודת המשל במו״נ:` → `מתודת המשל במורה נבוכים:`
- **Scope:** leave volume and chapter locators (`ח״א פ״ע`), `ע״א`/`ע״ב` and honorific abbreviations.
  An abbreviation inside a quotation stays as in the source.

### 2.4 Selective niqqud only to disambiguate (R-20) — optional
- **Principle:** a single vowel point on a word the author has not pointed, only where an unpointed
  word is truly ambiguous in context, and only when the author's text already uses selective niqqud.
- `לדוד` (the beloved, in a paper about love poetry) → `לדוֹד`
- **Scope:** never default. Point the same homograph consistently in the paper, or not at all.

### 2.5 A suspected transcription error inside a quotation is flagged, not fixed (R-21)
- **Principle:** when a quotation is not found verbatim, or contains a non-word that looks like an
  OCR or transcription error (`מתחלסין` where the source reads `מתחלפין`), report it to the author
  as a flag: "check against the source". Fix the evidence text in the library (the OCR or ingest
  path), never silently in the article. If the author approves, mark `[כך]` or correct the
  evidence file so the quote check stays verbatim.
- **Scope:** archaic and dialectal spellings in sources look like typos and are genuine readings.

## 3. Agreement and government

### 3.1 Agreement follows the head noun after every lexical change (R-15)
- **Principle:** after any replacement, re-check the verb, adjective, relative clause, possessive
  suffix and demonstrative against the **new** head noun, including its gender and number. A suffix
  on a definite construct chain becomes analytic `שלו`.
- `זהו טיעון על אי-עקביות שיטתית שראוי להציגה` → `זהו טיעון על חוסר עקביות שיטתי שראוי להציגו`
  (`חוסר` is masculine; every dependent form changes with it)
- **Scope:** a verifier check on changed spans, not a deterministic rule. Do not over-flag
  acceptable forms (an adjective with a complement and no ה; `אחדותו` with an ambiguous antecedent).

### 3.2 Correct preposition government (R-17)
- **Principle:** fix only a preposition that is wrong for its head in context: `הסתייגות מ־` (not `ל־`),
  a missing `ב־` before a foreign technical noun after `הבנוי`, `עד ל־` with a deverbal noun.
- `יחידות מקרו הבנויות כיאזם` → `יחידות מקרו הבנויות בכיאזם`
- **Scope:** `בפני` and `לפני` are **both correct**: `בפני` is the idiom for "in the presence of" and
  in `בפני עצמו`. `מאוחר ל־` in a temporal comparison is correct. About 75% of regex hits in the
  author's articles are correct Hebrew; propose only a preposition that is actually wrong.

### 3.3 Formal demonstratives (R-18) — per-author style word only
- **Principle:** `זו`/`זה` after the noun and `אלה` (not `אלו`) are a formal preference. Record
  `אלו`→`אלה` or `אף פעם`→`מעולם` as a style word only when the author repeatedly rewrites it
  (`/learn` offers it). Never a shipped default; never match `אלו` as a substring (`אלוהים`).
- `הנקודה הזאת` → `נקודה זו`

### 3.4 `אי־` and `בלתי` compounds (R-36)
- **Principle:** prefer `חוסר` + noun to a coined `אי־` + abstract noun, then re-check agreement.
- `אי-עקביות שיטתית` → `חוסר עקביות שיטתי`
- **Scope:** lexicalised `אי-נוחות` and `אי-ודאות` stay. Do not rewrite `בלתי` + participle.

## 4. Register and wording

### 4.1 Neutral formal register, precise collocations (R-24)
- **Principle:** a short suggestion list, never a banned list: `אחר כך`→`לאחר מכן`; `ראשית כל`→
  `בראש ובראשונה`; `בצמידות`/`צמוד`→`בסמיכות`/`סמוך`; `כבדפוס`→`כמו בדפוס`; `בלא` before a
  `ש`-clause → `בלי`. `על פני` → `לאורך` only when the object is a whole span (`על פני הספר כולו`→
  `לאורך הספר כולו`).
- **Scope:** not `על פני הדברים` or `על פני כמה פסוקים`. Do not turn these into rules: `בלא`→`ללא`/
  `בלי` for nouns, `אצלו`→`לשיטתו`, `מבלי`→`בלי`, `נדמה`→`נראה` (a shift in meaning).

### 4.2 Cut intensifiers and redundant modifiers (R-26)
- **Principle:** delete a modifier that repeats what its head already says (`ממש` after an identity
  noun, `בדיוק` with `מתי`/`מקום`, `כל כולה`, a repeated modifier, `מעין` before a noun that needs no
  hedge).
- `מסגרת שהיא מעין ביניים בין` → `מסגרת ביניים בין`; `לכלל ההצעות המודרניות` → `להצעות המודרניות`
- **Scope:** keep contrastive and idiomatic uses: `עצמו` in a contrast, `דווקא` marking a choice,
  `של ממש`, `לכלל` meaning "into". Do not list `דווקא` or `עצמו` as filler. Leave `אפוא` alone except
  for its commas (1.2).

### 4.3 Direct assertions instead of clefts (R-27)
- **Principle:** replace a presupposing cleft with a direct assertion; make forward references active.
- `מה שכן ניתן להראות הוא שיש בפירוש מבנה אחיד` → `ניתן להראות שיש בפירוש מבנה אחיד`
- `בסעיף ה יוצג מבט ביקורתי` → `סעיף ה יבחן באופן ביקורתי`
- **Scope:** keep every `לא רק X אלא Y` that carries a real contrast; it is a legitimate move of the
  author's, not a tell. Range and double-negation rewrites are one-off choices, not rules.

### 4.4 Lighter nominal constructions (R-28)
- **Principle:** prefer a plain verb or participle to a light verb plus an abstract noun, and drop a
  padding noun when the head suffices: `יציג מבט ביקורתי על` → `יבחן באופן ביקורתי את`; subject
  relative `אשר` + present verb → `ה` + participle (`הטקסט אשר מתאר` → `הטקסט המתאר`); drop `קיומה של`.
- **Scope:** keep `אשר` with prepositional and object relatives and always inside quotations. Never
  ban `אשר` (the author uses it freely). Judgement only.

### 4.5 English calques (R-30)
- **Principle:** a short table of repairs, not a ban list: `פער פרשני`→`קושי פרשני`; `הדילמות המחקריות`→
  `המחלוקת המחקרית`; `יילקחו כפשוטם`→`יובנו כפשוטם`; `הנמתח`→`הנמשך`/`הנפרש`; `העתק מבני`→`יישום מבני`;
  a bare copula `מהווים` → `הם`.
- **Scope:** `על מנת` is acceptable Hebrew; do not flag it. Do not ban `פער`, `מתודה` or `יוצג`.

### 4.6 Ad hoc hyphenated compounds (R-33)
- **Principle:** write out a hyphen compound that hides a negation (`לא-X`→`שאינו X`) or a
  preposition, and do not coin noun-noun hyphens in new prose.
- `דיכוטומיה גוף-נפש` → `דיכוטומיה של גוף ונפש`; `קישור לא-סמוך` → `קישור שאינו סמוך`;
  `ההיסטורי-ביוגרפי` → `ההיסטורי והביוגרפי`
- **Scope:** adjective pairs (`שכלתני-אלגורי`) and established terms stay. A verse range (`כ-כא`) is
  not a compound.

### 4.7 Adjectives derived from acronyms (R-35) — per-author style word
- **Principle:** offer `X של הרמב״ם` for a coined acronym adjective: `המסגרת הרמב״מית` → `המסגרת של
  הרמב״ם`. A profile-level style word with its replacement, not a shipped list; match longest forms
  first to avoid overlapping edits. `ההישנות`→`חזרה` is a one-off.

## 5. Sentence and paragraph shape

### 5.1 Fragments from the generator (R-22)
- A generated paragraph must not open with a negated copula or a bare participle with no subject
  (`אינה הצעה חמישית מאותו סוג…` as the first words): add the subject. Surface it as a warning, not a
  gate. Openings with `הוא`/`היא`/`הם` are fine. A missing head noun (an adjective pair with no noun)
  is an LLM or auditor check, not code.

### 5.2 Modifiers next to their focus (R-29)
- **Principle:** `רק` and `גם` immediately before their focus; adjectives after nouns (`הנחת יסוד
  משותפת`); front `לדבריו`/`עם זאת` only when it would otherwise sit between a short subject and its
  predicate; a medial parenthetical (`ככל הנראה`, `אם כן`) is set off by commas.
- `אפשר לשאול אם יש לראות בו בכל זאת יצירה אחת` → `אפשר לשאול אם בכל זאת יש לראות בו יצירה אחת`
- **Scope:** every word-order change needs a meaning check; never a regex.

### 5.3 Name whose claim it is (R-31)
- **Principle:** replace an impersonal back-reference with the named source, and give a bare
  interpretive claim its agent and claim verb.
- `כפי שנקבע לעיל` → `לפי תיאורו של X, שהובא לעיל`
- `הדוד הוא השכל הפועל` → `המחבר טוען בספרו כי הדוד הוא השכל הפועל`
- **Scope:** the claim must belong to the source; never attribute the author's own thesis to someone
  else. Judgement only.

### 5.4 Split a comma or dash splice (R-34)
- **Principle:** split at the new subject and drop the joining vav.
- `הפירוש מציע חלוקה לפרשיות, והחלוקה הזו מבוססת על מילות מפתח` → `הפירוש מציע חלוקה לפרשיות. חלוקה
  זו מבוססת על מילות מפתח.`
- **Scope:** no absolute length ceiling and no length gate: a long sentence is long mostly because of
  embedded citations. Sentence length stays governed by the author's own fingerprint.

### 5.5 Scholar names (R-37)
- Full name at the first prose mention, surname alone afterwards (existing profile rule). Footnote
  and bibliography entries keep `Surname, First` and are not shortened.

## 6. Headings and structure (advisory for the outline architect; no scorecard check)

### 6.1 Informative noun-phrase headings (R-57)
- Prefer a topic noun phrase to a question, a quoted term, an adversarial `מול`, a dash-split slogan or
  a one-word generic title. `מהי "פרשה" אצל המחבר?` → `מושג הפרשה בפירוש`.
- The author's own past articles use question headings; advisory only, never a gate.

### 6.2 The introduction has its own heading (R-58)
- A long paper has a visible, TOC-reachable `מבוא` heading at level 1. Whether it is lettered
  (`סעיף א: מבוא`) or an unnumbered `מבוא` is the author's choice: do not flag either form.

### 6.3 Roadmap equals the final heading list (R-66)
- After any added, removed or reordered section, re-derive the introduction's roadmap from the final
  headings: the number of stages and every section letter it names must match, whatever the label form
  (`סעיף ג` / `ג.` / `ג'`). `המאמר בנוי בשישה סעיפים` → `בשבעה סעיפים` after a seventh section is added.

### 6.4 Calibrate claims to the evidence (R-65)
- Framing sentences (abstract, introduction, conclusion, headings, TOC) may not claim more than the
  body shows. If the body says the link is `מבנית בלבד`, the introduction says so too, and a changed
  hedge is propagated to every repeat, headings and the TOC included.
- `מגלה זיקה לאפלטון` → `מגלה זיקה מבנית בלבד לאפלטון`
- **Scope:** an exclusive or universal quantifier (`אך ורק`, `תמיד`, `מעולם`, `כל`) is a cue for the
  reviewer to check against the evidence, never an automatic failure; it stands when the text lists
  its support. A hedge does not repair an unsourced claim (auditor Checks E and F still apply).

## 7. Project terms: one canonical form per named figure (R-25, R-69)

No article name is hardcoded in the plugin. The principle: a first-name-only medieval figure takes the
same honorific (`ר׳`, with a geresh, not an ASCII apostrophe) at **every prose mention**, including
sentence-initial and prefixed forms (`שר׳`, `לר׳`); a foreign name has **one** Hebrew spelling
(`ארסטו`→`אריסטו`); a surname keeps one form (`שורץ`→`שוורץ`). Inside quotations, bibliographic
references and cited titles, the bibliographic form stays as printed.

- **Where it lives:** the per-project registry `.academic-helper/terms.json`
  (`{"canon":[{"form":…,"variants":[…]}]}`, schema `src/schemas/terms.schema.json`), filled at outline
  time. `aw proofread` runs `must-catch.py` over it.
- **Caution:** `must-catch.py` replaces each variant as a raw **substring**, with no word boundary and
  no skipping of quotations or titles, and it applies the result automatically. Register only
  variants that cannot occur inside another word or a cited title (a bare `שורץ` also matches
  `שורצים`; a bare `האקריטי` sits inside a cited article title). Until the script gains boundaries and
  quote skipping, treat the registry as a check for the author to confirm, not an auto-fix. Flag a
  name inside a cited title for the author to verify against the publication.

## Cautions that apply to every item (from the false-positive checks)

- `בפני`/`לפני`, `על מנת`, `אשר`, `דווקא`, `לא רק … אלא` and `(שם, …)` are all correct usage in the
  author's past articles. A hit on them is not an error.
- Regexes behind these items (`, ו`, `אלא`, `בסעיף א`, `אי-`, `ממש`, `מעין`) fire mostly on correct
  Hebrew: use them to locate, then read.
- A substring match corrupts inflected and prefixed forms (`ממש` inside `ממשיך`, `הקדש` inside
  `וההקדש`, `שורץ` inside `שורצים`). After **any** replacement, re-scan the result for agreement and
  for inflected or prefixed variants.
- Evidence is one editor on one paper. When the author's accepted text (a graded article) does the
  opposite, the author's text wins.
