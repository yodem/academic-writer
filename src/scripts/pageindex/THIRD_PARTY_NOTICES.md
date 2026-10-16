# Third-party notices

`pilib` (this folder) is part of academic-writer and carries the plugin's own MIT license.

It does not contain or redistribute any code from the projects below. The installer downloads them into a
virtual environment in the plugin's data folder, at the exact versions and file hashes listed in
`PINNED.json`, `requirements-core.txt` and `requirements-structure.txt`. Each keeps its own license.

| Project | Used for | License | Pinned |
|---|---|---|---|
| PageIndex (VectifyAI/PageIndex) | structure detection for a book without a table of contents (structure tier only) | MIT, Copyright (c) 2025 Vectify AI | commit `af92d9658a6a9c0ae31171b43198db28951af2f4`, tarball sha256 in `PINNED.json` |
| LiteLLM | the model client for node summaries (both tiers) | MIT | `requirements-core.txt`, `requirements-structure.txt` |
| PyPDF2 | reading text back from the rendered PDF (structure tier) | BSD-3-Clause | `requirements-structure.txt` |
| pypdfium2 | PDF parsing inside PageIndex (structure tier) | Apache-2.0 or BSD-3-Clause | `requirements-structure.txt` |
| WeasyPrint | rendering Trove text to a PDF for structure detection (structure tier) | BSD-3-Clause | not pinned; installed separately |

The other packages in the requirements files are transitive dependencies of the projects above and keep their own licenses.

If a file of PageIndex is ever copied into this repository, it must keep its MIT notice and be listed here.

## What leaves the computer

To write node summaries, the text of a book is sent to Google (Gemini) through LiteLLM, with the researcher's own
Gemini key. `--summaries hints` and `--summaries none` send nothing anywhere.
