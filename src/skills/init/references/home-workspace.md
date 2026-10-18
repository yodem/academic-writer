# Home detection and workspace type

> Loaded on demand by `init` Phase 0.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/home.py" show
```

- **No home chosen:** this folder is a plain project. Do not ask any course question; suggest
  `/academic-writer:setup` once if the researcher wants a home folder, then continue.
- **Home chosen, and this folder is outside home:** also a plain project. No course questions.
- **Home chosen, and this folder is inside home:** ask once:

```python
AskUserQuestion(questions=[{
  "question": "Which course is this folder for, or is it a separate project?",
  "header": "Which course is this?",
  "options": [
    {"label": "A course", "description": "One of the courses of your current term; I will list them."},
    {"label": "Separate project", "description": "An article or research project that is not tied to a course."}
  ],
  "multiSelect": false
}])
```

On "A course", list the term's courses (the `name` in each `<slug>.json` of the registry; see the `courses` skill)
and let the researcher pick one. Register the answer with `home.py register`, so the dashboard and the hooks know this folder:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/home.py" register --path "$PWD" --type course --course COURSE_SLUG --term TERM
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/home.py" register --path "$PWD" --type project
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/home.py" register --path "$PWD" --type teaching --term TERM
```

Run only the line that matches (`course`, `project`, or `teaching` for a course the researcher
teaches). Registering is a write inside the home folder only; say so in one sentence.
