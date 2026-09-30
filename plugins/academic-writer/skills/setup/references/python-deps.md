# Python packages check

> Loaded on demand by `setup` Step 4b, `init` Phase 0 and `health`.

Python packages are small add-ons that teach Python new skills. Academic Writer needs five of
them. Two have a different name when installed than when used — `python-docx` is used as `docx`,
and `pymupdf` is used as `fitz`.

| Package (install name) | Used as | What it does for you |
|---|---|---|
| `python-docx` | `docx` | Reads your Word files and builds the finished `.docx` |
| `lxml` | `lxml` | Helps `python-docx` read the inside of Word files |
| `pdfplumber` | `pdfplumber` | Pulls the text out of PDF articles for style analysis |
| `pymupdf` | `fitz` | Checks whether a scanned PDF already has a text layer (OCR) |
| `jsonschema` | `jsonschema` | Checks the proofreader's list of corrections is well formed |

## Check (changes nothing, safe to repeat)

```bash
python3 -c "
import importlib
mods = {'python-docx': 'docx', 'lxml': 'lxml', 'pdfplumber': 'pdfplumber', 'pymupdf': 'fitz', 'jsonschema': 'jsonschema'}
missing = []
for pkg, mod in mods.items():
    try:
        importlib.import_module(mod)
    except ImportError:
        missing.append(pkg)
print('MISSING:' + ','.join(missing) if missing else 'ALL_PRESENT')
"
```

## Install (only after the researcher says yes)

The install command itself lives in the skill step that asks first (`setup` Step 4b, `init`
Phase 0). It installs all five packages for the current user only; re-installing one that is
already present does no harm. If it fails, see `troubleshooting.md`.
