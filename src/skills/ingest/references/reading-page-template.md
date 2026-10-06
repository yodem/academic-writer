# Reading-page template — "How to read and cite this book"

Every book uploaded by `/academic-writer:ingest` or `/academic-writer:ingest-book`
starts with this page as its **page 1**. Fill in every bracket; never leave a
placeholder. Write the page in the document's primary language (use the Hebrew
template for Hebrew sources).

The page must carry five things:

1. The full bibliographic record of the exact edition in hand.
2. How the printed page markers work and the citation rule.
3. Ready-made footnote templates in **three** citation styles.
4. For a primary text, a structural-locus citation form.
5. The printed pages actually covered, and any gaps.

## Choosing the third citation style

Always include **Chicago notes-bibliography** and the **Hebrew academic
convention**. Choose the third style from the profile's `citationStyle` in
`.academic-helper/profile.md` so the author's own style always appears:

- profile style `mla` → include the **MLA** template (skip APA);
- profile style `apa` → include the **APA** template (skip MLA);
- profile style `chicago` → include the **APA** template (Chicago is already
  covered);
- anything else (`inline-parenthetical`, unset) → include the **MLA** template.

Never invent a style variant; if the profile names a style this page does not
know, include the three above and note the profile style on the page.

## English template

```markdown
# How to read and cite this book

## Bibliographic record
**Author:** [full author name(s)]
**Title:** [full title]
**Edition:** [edition / editor / translator, volume(s), place: publisher, year]
**Pages covered:** [e.g. printed pp. 31–45, 160–185, 215–224, 249]
**Not included:** [the gaps, e.g. printed pp. 46–159, 186–214, 217, 225–248]

## How the page markers work
Each page in this book carries its original printed page number in the header,
in the form **[Original print page: NNN]**, and the reading guide refers to
pages as `(orig. N)`. The book's own sequential numbering starts at 1 (this
guide) and differs from the printed numbering. **When you cite this work, use
the printed page number, never the book's sequential page number.**

## Footnote templates for this book
**Chicago notes-bibliography** — first note:
> [Author first name Last name], *[Title]* ([edition: place: publisher, year]), [NNN].
Short note:
> [Last name], *[Short title]*, [NNN].

**Hebrew academic convention** (Israeli humanities journals) — first note:
> [שם המחבר], [שם הספר] ([מקום: מוציא לאור], תשנ״ה), עמ׳ [N].
Short form:
> [שם המשפחה], [שם הספר], עמ׳ [N].

**[MLA or APA, chosen per the rule above]** —
> [the filled-in template for this book, in that style's exact form]

## Citing by structural locus (primary texts)
This is a primary text, so it can also be cited by its internal structure:
> [Author], *[Title]*, [chapter/premise/paragraph, e.g. "ch. 14, premise ט״ו"]
([edition]), [printed page NNN as a secondary locator].
```

## Hebrew template

```markdown
# כיצד לקרוא ולצטט ספר זה

## רשומה ביבליוגרפית
**מחבר:** [שם המחבר המלא]
**כותרת:** [כותרת מלאה]
**מהדורה:** [מהדורה / עורך / מתרגם, כרכים, מקום: הוצאה, שנה]
**עמודים שנכללו:** [למשל עמודים 31–45, 160–185, 215–224, 249 בדפוס]
**לא נכללו:** [הפערים, למשל עמודים 46–159, 186–214, 217, 225–248 בדפוס]

## כיצד פועלים סימני העמודים
כל עמוד בספר זה נושא בראשו את מספר העמוד המודפס המקורי, בצורה
**[עמוד מקורי מהפרסום המודפס: NNN]**, ומדריך הקריאה מפנה לעמודים בצורת
(מקורי N). המספור הרציף של הספר מתחיל ב־1 (מדריך זה) ואינו זהה למספור
המודפס. **בעת ציטוט היצירה יש להשתמש במספר העמוד המודפס, ולעולם לא במספר
העמוד הרציף של הספר.**

## תבניות הערת שוליים לספר זה
**שיקגו (הערות וביבליוגרפיה)** — הערה ראשונה:
> [First name Last name], *[Title]* ([place: publisher, year]), [NNN].
בקצרה:
> [Last name], *[Short title]*, [NNN].

**המוסכמה האקדמית העברית** — הערה ראשונה:
> [שם המחבר], [שם הספר] ([מקום: הוצאה], תשנ״ה), עמ׳ [N].
בקצרה:
> [שם המשפחה], [שם הספר], עמ׳ [N].

**[MLA או APA, לפי הכלל לעיל]** —
> [התבנית הממולאת לספר זה, בצורתו המדויקת של סגנון זה]

## ציטוט באמצעות מקום מבני (טקסט ראשוני)
זהו טקסט ראשוני, וניתן לצטטו גם לפי מבנהו הפנימי:
> [מחבר], [כותרת], [פרק/פרמיסה/פסקה, למשל "פרק יד, פרמיסה ט״ו"] ([מהדורה]),
[עמוד מודפס NNN כמקור משני].
```

Omit the structural-locus section when the work is a secondary source
(a modern monograph or article).

For OCR-derived pages that were not verified against the image, add one more
line at the bottom of the record section, exactly:
`**Warning:** pages marked "OCR, not image-verified" were transcribed by OCR and
not checked line by line against the original image; check them before quoting
verbatim.` (Hebrew sources get the equivalent sentence in Hebrew.)
