# Venue profile — bar-ilan-seminar-apa-he (bundled, opt-in)

> **Bundled and opt-in.** Use it with `aw proofread --venue bar-ilan-seminar-apa-he`. A file with the
> same slug at `.academic-helper/venues/bar-ilan-seminar-apa-he.md` in the project **wins**: copy this
> file there to adapt it. Without `--venue`, nothing here applies and the author's default style
> (footnotes with `שם` for ibid) is unchanged. The profile is additive: it tightens or adds checks
> and never removes a global editorial check.
>
> **Provenance.** One professional editor's review of one Hebrew seminar paper, every rule re-checked
> against the edit counts and the author's past articles. It is a citation and layout house style,
> not a journal. It is a profile of **suggestions**: propose, the author confirms, nothing is
> auto-replaced. Author, year and page values come from `sources.json` and are never retyped.

- **Name:** Hebrew seminar paper, hybrid citation style (author-year in text, short footnotes, APA 7)
- **Language:** Hebrew, with Latin-script sources
- **Settings (for code that reads this profile):** `citation.inText=author-year-page`,
  `citation.ibid=false`, `citation.footnote.secondary=short`, `citation.footnote.authorForm=
  surname-first-fullname`, `citation.pageRangeDash=–`, `bibliography.style=apa7-he/apa7-en`,
  `bibliography.unreadSources=list-with-note`, `bibliography.onlineSources=url-own-line`,
  `typography.workTitleInText=single-quotes (optional)`, `orthography.divineAdjective=author's form`

## Citation in the text

1. **Author, year as printed, page (R-38).** Every in-text locator to the paper's principal printed
   primary edition is `(Author, yearAsPrinted, עמ׳ N)` with the author's full patronymic form from
   the source record. Drop the work title and the editor of the edition. A Hebrew-letter year takes
   gershayim.
   - `(פלוני בן אלמוני, תשכ״ב, עמ׳ 17)`
   - A digital edition that prints no year takes the author and the paragraph, no year:
     `(פלוני בן אלמוני, פסקה 4)`.
   - Talmud, Mishnah, Midrash and other ancient works that are not in the author-year list keep their
     own locator form and are not converted.
2. **No `שם` in a parenthetical citation (R-39).** Repeat author and year every time:
   `(שם, עמ׳ 19)` → `(פלוני בן אלמוני, תשכ״ב, עמ׳ 19)`. This is for an in-text page reference to an
   edition. Footnote `שם` stays (the editor kept it), and so does `(שם, <verse>)` pointing to the same
   biblical or targumic text.
3. **Page ranges (R-11).** `עמ׳ 12–14`, an en dash, as in the global citation format. If a source
   record truncates a range (`233-45`), fix it as a bibliography-accuracy error, not as typography.
4. **Locators with commas and the book name (R-42, part b).** Commas between all fields is the
   universal rule. In this profile a bare `(chapter, verse)` locator also names the book:
   `(ג, ה)` → `(קהלת, ג, ה)`; this includes the commented book. Exceptions: a multi-verse list, or a
   sentence that already names the book. Keep the author's short or long form of the name; do not
   pin a geresh or gershayim.
5. **A source known only through another work (R-40), footnotes only.** Write a Hebrew sentence, not
   a bibliography-style note:
   `דברי <initials with geresh> <surname> <במאמרו|במאמרה|בספרו> "<Latin title>" [עמ׳ N] מובאים על פי
   <intermediary>, "<short title>". <המאמר|הספר|שני החיבורים> לא נבדק/ו במקורו.`
   - `דברי ד׳ פלוני במאמרו "Original Title" (עמ׳ 12) מובאים על פי א׳ אלמוני, "כותרת קצרה". המאמר לא
     נבדק במקורו.`
   - Do not reproduce the unread work's imprint. Leave bibliography notes alone (see 4 under
     "Reference list").
6. **Short-form footnotes for a printed secondary source (R-41, R-43).** Footnotes only: author
   inverted with the full first name (also for Latin-script authors), short title, pinpoint. Container,
   editors, series, place, publisher, year and the full range live only in the bibliography.
   - `אלמוני, דניאל. "כותרת קצרה", עמ׳ 12.` and `Doe, Jane. "Short Title", pp. 12–14.`
   - `עמ׳` for Hebrew-script sources, `pp.` for Latin-script ones (or `p.`/`pp.` by one decision for
     the whole paper). Authors named inside the Hebrew second-hand sentence keep the `דברי First
     Surname` order. Do not copy the editor's slips: a closing quote glued to a comma, a missing
     period after `pp`, a double comma.
7. **Work title in running text (R-47) — optional.** Name the title with ASCII single quotes and give
   the locator in parentheses after it: `ב'מורה נבוכים' (ג, כ)`. Tested only for this title; other
   titles stay as the author writes them.

## Reference list (bibliography)

1. **Layout (R-49).** Plain paragraphs: no bullets, no numbering, no list style. Sub-headings
   `מקורות ראשוניים` and `מקורות משניים`. Each block is sorted by the first word (Hebrew collation,
   ignoring quotes and punctuation), the same author by year, **Hebrew entries before Latin**; sort
   the two scripts separately. Latin entries are LTR, left-aligned. Italics follow the entry type
   (work title; journal and volume; work and locus for Maagarim). Strip pasted colour and underline.
   Hanging indent is a venue option, off by default. Ranges take an en dash.
2. **English entries in strict APA 7 (R-51).** `Surname, I. I. (year). Sentence-case title: Capital
   after colon. <i>Journal, vol</i>(issue), pp–pp.` or `<i>Book title</i>. Publisher.` Initials replace
   first names; `III` follows a comma; no city; series and `idem` dropped (one entry per work and
   year); journal names in full without quotation marks; chapters `In X & Y (Eds.), <i>Book</i>
   (pp. a–b). Publisher.` The issue number is added only if the source record has it, never invented.
3. **Hebrew entries in APA 7 adapted to Hebrew (R-53).** `Surname, I׳. (year as printed). Title.
   Container (עמ׳ x–y). Publisher.` Initial plus geresh; book and container titles in italics;
   article titles plain, without quotation marks; roles in parentheses (`מהדיר`, `מתרגם`, `עורכים`);
   honorifics dropped; no ISBD punctuation (` : `, ` / `); place of publication dropped. A chapter in
   a volume stays a chapter and is not turned into a journal article.
4. **Unread works (R-52).** `bibliography.unreadSources=list-with-note` (as edited): the work stays in
   the list and a note paragraph follows it, well-formed, with the intermediary taken from the
   record: `(מובא אצל <intermediary surname>; לא נקרא במקורו)`. Strict APA would list the
   intermediary only: ask the author when the venue requires strict APA. The footnote wording uses the
   same phrase.
5. **Online sources (R-48, R-10).** The entry ends with a lead-in that ends in a colon
   (`מתוך אתר על התורה:`, or `מאגרים. אוחזר ב־<תאריך>, מתוך:`), then the **full visible URL as its own
   LTR, left-aligned paragraph**. No `קישור` label and no inline ` - URL`. A remark about the scope of
   the link goes in the lead-in. The URL text comes from the source record or the lookup, never
   retyped. The retrieval phrase takes a maqaf after the prefix letter (`אוחזר ב־<תאריך>`), and so
   do some publisher or author names (`בר־אילן`, `בן־זאב`); not in running text and not in footnote
   titles.
   - `פירוש לשיר השירים. מתוך אתר על התורה:` then, on the next line, `https://example.org/path`
6. **Rabbinic sources from Maagarim by manuscript witness (R-50).**
   `<i>work and locus</i> [נוסח כתב יד <עיר, ספרייה, מס׳ כ״י>]. מאגרים. אוחזר ב־<תאריך>, מתוך:`
   then the URL paragraph. `מהדורת` is not used for a manuscript witness. When the link resolves only
   to the start of the work, a remark follows `מתוך הקישור:`. Brackets are well-formed and balanced.
   - `משנה, מסכת פלונית ג, ה [נוסח כתב יד <עיר, ספרייה, מס׳ כ״י>]. מאגרים. אוחזר ב־<תאריך>, מתוך:`

## Headings, cover and orthography

1. **Heading labels (R-56).** A letter and a period, then the title; the sub-level adds its number:
   `א. הרקע`, `ד.ג. נושא המשנה`. A subtitle follows a colon: `א. הרקע: הסביבה ההיסטורית`. No label
   colon survives (`סעיף א: …` → `א. …`). Keeping the word `סעיף` is the author's choice: be
   consistent. A spaced hyphen between title and subtitle is not kept.
2. **Cover page (R-54).** Opt-in layout, never a blocking check. Title bold 18 pt. A label line, then
   a value line, at 14 pt: `מאת:` / `<שם הסטודנט> (<מספר זהות>)`; `מוגשת:` / `<שם המנחה>`;
   `במסגרת הקורס:` / `<שם הקורס> (<קוד הקורס>)`. The values come from the author's own profile when the
   file is generated; the plugin stores none. No `ת"ז:` caption and no `העבודה מוגשת ל`. The Hebrew
   and Gregorian dates sit on one line at opposite margins (a right tab stop, not runs of spaces).
   University, faculty and department lines are left as they are.
3. **Centuries (R-19).** One form per article. If the article spells ordinals, write feminine
   ordinals in full (`המאה האחת-עשרה`). No global conversion of `המאה ה-19`.
4. **Divine adjective (R-23).** A hyphenated name-avoidance spelling (`א-לוהי`) outside a quotation is
   normalised to the author's own form (`אלוהי`), not to `אלוקי`.

## What this profile flags (for the editorial memo)

- A parenthetical `(שם, עמ׳ N)` that points at a page of the main edition, or an in-text page
  reference with no author and year.
- A second-hand source cited in a footnote as a full bibliography entry instead of the `מובאים על
  פי` sentence.
- A bibliography entry that is numbered or bulleted, unsorted, mixed in script order, with an inline
  `- URL`, a `קישור` label, or a Maagarim text cited as `מהדורת`.
- An English entry with a city, an `idem`, a quoted journal name or initials spelled as first names.
- An unread work in the list with no provenance note.
- A heading label ending in a colon.

## What this profile does not do

- It does not change the default footnote and `שם` style for any project that does not opt in.
- It does not prefer the spaced hyphen or the em dash: the global dash default applies.
- It does not ask the plugin to retype an author, year or URL.
- It never blocks a run; every item is a suggestion for the author to confirm.
