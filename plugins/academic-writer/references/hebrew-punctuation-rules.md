# Hebrew Punctuation Rules for RTL Text in DOCX

## Core Principle

Hebrew text flows **right-to-left (RTL)**. When generating DOCX documents with Hebrew academic writing, punctuation and parentheses must follow logical/semantic placement, **not visual placement**. Word/DOCX handles the bidirectional reordering automatically.

---

## 1. Regular Text Flow (No Special Marks Needed)

**Correct approach:**
```
Hebrew text flows naturally. Punctuation appears in logical positions.
```

Use standard Unicode:
- Regular parentheses: `(...)` — DOCX RTL context handles visual reordering
- Periods, commas, colons at logical sentence positions
- **NO manually inserted directional marks** (RLM/LRM)

**Example (correct Hebrew in DOCX):**
```
במאמר זה אנו בוחנים את הטענה המרכזית (ליביא, כל העולם שלי, עמ' 45).
```

Renders as: `במאמר זה אנו בוחנים את הטענה המרכזית (ליביא, כל העולם שלי, עמ' 45).`  
DOCX automatically places the opening `(` visually on the right, closing `)` on the left.

---

## 2. Citation Parentheses (Inline-Parenthetical Format)

**Standard format for Hebrew academic citations:**

```
(Author, Title, עמ' PageNumber)
```

### Structure

| Component | Format | Example |
|-----------|--------|---------|
| Author | Hebrew or transliterated name | קאנט, גנזל, שיינברק |
| Title | Hebrew title (or Hebrew translation) | ביקורת התבונה המעשית |
| Page notation | Always `עמ'` (abbreviation: עמוד) | עמ' 45, עמ' 120-125 |
| Translator (optional) | `[תרגום {Name}]` | [תרגום יעקב הנס] |

### Examples (Correct)

**Simple citation:**
```
(קאנט, ביקורת התבונה המעשית, עמ' 45)
```

**With translator:**
```
(קאנט, ביקורת התבונה המעשית [תרגום יעקב הנס], עמ' 45)
```

**Range of pages:**
```
(גנזל, בין נביא לנבואתו, עמ' 100-105)
```

**Multiple sources (semicolon separator, inside parentheses):**
```
(קאנט, ביקורת התבונה המעשית, עמ' 45; גנזל, בין נביא לנבואתו, עמ' 120)
```

### Placement in Running Text

Citation comes **immediately after the claim** with a period/comma after the closing paren:

```
Claim here (Author, Title, עמ' Page). Next sentence.
```

**Example:**
```
מקדש יחזקאל הוא תיאור עתידי של בניין קודש (גנזל, בין נביא לנבואתו, עמ' 100). טיעון זה מומצא בשל מבנה הטקסט.
```

---

## 3. Punctuation Placement Rules

### Periods (.)
- Placed at the **logical end** of the sentence (in the text order)
- DOCX positions it visually at the left margin in RTL context
- **Never** at the start of a word or inside parentheses

### Commas (,)
- Placed at the **logical position** within the sentence
- NOT forced before/after citations
- DOCX positions it correctly in RTL flow

**Correct:**
```
טקסט, ולאחר מכן עוד טקסט (ציטוט, שם, עמ' 10).
```

**Wrong (don't do this):**
```
טקסט (ציטוט, שם, עמ' 10) , ולאחר מכן עוד טקסט.  ← Comma in wrong place
```

### Semicolons (;)
- Used **only** to separate multiple citations within parentheses
- Placed logically within the citation parentheses

**Correct:**
```
(Author1, Title1, עמ' 10; Author2, Title2, עמ' 20)
```

### Colons (:)
- Introduce lists or explanations
- Placed at logical sentence position

---

## 4. Quotation Marks (Hebrew Gereshayim)

**Use Hebrew quotation marks, not English straight quotes.**

### Standard Format

| Pattern | Unicode | Use Case |
|---------|---------|----------|
| Gereshayim (`״...״`) | U+05F4 | Direct quotes, titles, special terms |
| Single geresh (`׳`) | U+05F3 | Abbreviations (rare in academic writing) |
| English quotes (`"..."`) | U+0022 | **NEVER** in Hebrew academic text |

**Correct Hebrew quotes:**
```
"הברק הוא תופעה טבעית, לא פעם אלוהית"
```

Rendered (with gereshayim): `״הברק הוא תופעה טבעית, לא פעם אלוהית״`

**Wrong (don't use English quotes):**
```
"This is not Hebrew style"  ← Wrong for Hebrew text
```

---

## 5. Hyphens vs. Em-Dashes vs. En-Dashes

### Hyphen (`-`)
- Compound words: `תיאור-ביקורתי` (descriptive-critical)
- Ranges: `עמ' 40-45` or `1995-2000`

### En-Dash (`–`, U+2013)
- For ranges when using full spelling: `עמודים 40 עד 45`
- **Not commonly used in Hebrew academic writing**

### Em-Dash (`—`, U+2014)
- **NEVER use in academic Hebrew** — this is an AI signature
- AI writing tools heavily use em-dashes for pauses and asides
- If you find an em-dash, replace it with space-hyphen-space: ` - `

**Wrong (AI signature):**
```
טקסט כזה — יכול להיות דוגמה — של כתיבה מעוררת חשש.
```

**Correct (human Hebrew):**
```
טקסט כזה - יכול להיות דוגמה - של כתיבה מעוררת חשש.
```

Or better, rewrite to avoid the pause:
```
טקסט כזה, המשמש בתור דוגמה, של כתיבה מעוררת חשש.
```

---

## 6. Directional Marks (RLM/LRM)

### When to Use
**Almost never.** DOCX handles bidirectionality automatically.

### When They're Necessary (Rare)
Only when **LTR text (e.g., English words) appears inside RTL Hebrew text**:

**Example (rare case):**
```
Rosetti's concept (ממש כמו בספר "Metaphor" שלו)
```

In this case, you *might* need marks around the English word/title, but **usually DOCX handles it**.

### When They're Harmful
- RLM/LRM inserted around regular Hebrew parentheses → breaks rendering
- Multiple consecutive marks → visual garbage
- Marks after commas/periods → punctuation floats

**Rule: If you're inserting RLM/LRM, you're probably doing it wrong.**

### What to Do Instead
1. **For Hebrew-only text:** No marks needed. Just write naturally.
2. **For mixed LTR/RTL:** Trust DOCX. It has sophisticated bidi handling.
3. **If rendering is broken:** Check if there are extra marks and **remove them**.

---

## 7. Specific Case: Python-DOCX Library

When using `python-docx` to generate Hebrew DOCX files:

### Correct Approach
```python
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

def add_hebrew_paragraph(doc, text, font_name="David", font_size=11):
    """Add a Hebrew paragraph with proper RTL setup."""
    para = doc.add_paragraph()
    para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    
    # Enable RTL on paragraph
    pPr = para._p.get_or_add_pPr()
    bidi = OxmlElement("w:bidi")
    pPr.append(bidi)
    
    # Add text run
    run = para.add_run(text)  # Just the text, no manual mark insertion
    run.font.name = font_name
    run.font.size = Pt(font_size)
    
    # Enable RTL on run
    rPr = run._element.get_or_add_rPr()
    rtl = OxmlElement("w:rtl")
    rPr.append(rtl)
    
    return para
```

### What NOT to Do
- ❌ Don't insert RLM/LRM manually: `'\u200F(' + text + ')\u200E'`
- ❌ Don't split text into multiple runs for parentheses
- ❌ Don't insert directional marks around punctuation
- ❌ Don't use em-dashes

### What TO Do
- ✅ Write text naturally: `"Hebrew text with (citation) here"`
- ✅ Set `w:bidi` on paragraph (once)
- ✅ Set `w:rtl` on run (once)
- ✅ Let DOCX handle visual reordering

---

## Summary Table

| Element | Hebrew Rule | Example | Do NOT |
|---------|-------------|---------|--------|
| Parentheses | Standard `()` | `(Author, Title, עמ' 10)` | No marks around them |
| Periods | At logical end | `...claim (cite). Next.` | No period inside parens |
| Commas | At logical position | `Text, (cite). Next.` | Not before/after cite |
| Quotes | Gereshayim `״...״` | `״Hebrew quote״` | English `"..."` quotes |
| Em-dash | Never use `—` | Use ` - ` instead | `—` is AI signature |
| Directional marks | Almost never | Trust DOCX | Manual RLM/LRM insertion |

---

## Testing Checklist

When generating Hebrew DOCX documents:

- [ ] No em-dashes (`—`) anywhere
- [ ] All quotes are gereshayim (`״`), not straight quotes (`"`)
- [ ] Parentheses render correctly (opening on right, closing on left visually)
- [ ] Commas don't float or appear orphaned
- [ ] Citations formatted: `(Author, Title, עמ' Page)`
- [ ] Paragraph has `w:bidi` enabled
- [ ] Runs have `w:rtl` enabled
- [ ] No extra RLM/LRM marks visible
- [ ] Text flows naturally without manual breaks

---

## References

- **Unicode Standard:** https://unicode.org/reports/tr9/ (Bidirectional Algorithm)
- **Hebrew Typography:** https://www.sfardata.org/hebraictypography/
- **OOXML (Office Open XML):** Section on bidirectional text
- **python-docx:** https://python-docx.readthedocs.io/ (Text formatting)
