<!-- Eval availability is not yet confirmed; use the repo e2e runner if `claude plugin eval` is unavailable. -->
Run /academic-writer:proofread on fixture/article.md with --only mechanical.

Command grader: `python3 evals/graders/applied_recall.py <proofed.md> evals/proofread-recall/fixture/expected.json`
