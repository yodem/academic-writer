# Test integrity gate

The gate asks the test runner which tests exist on the base branch and on the PR, and fails when a test is gone or
newly skipped. The core is `scripts/test_integrity.py` (Python stdlib only); `scripts/test-integrity.json` names the
list commands, the maintainers, the label and the guarded paths.

## What it checks
- Every test id on the base is still listed on the PR, and no test is newly skipped.
- Each id the PR still lists is found in the committed source of its file (a forged list cannot hide a deletion).
  An id whose name is not in the source on base (parametrised tests with run-time titles) counts as verified when its
  file is byte-identical on base and head; otherwise it is listed as a warning (20 per suite, then a count). A suite
  where nothing could be verified by either method fails with exit 2.
  Playwright file paths are resolved to tree-relative paths from the report's `rootDir` and each project's `testDir`.
- No file with tests gains skip markers (`skip`, `todo`, `only`, `xfail` and similar, see `skip_markers`).
- No guarded file changed: the CI workflow, the gate itself, test config and this document.

## Excusing a test
Put a line in the PR body: `tests-removed: <test id> — <reason>` (a long dash or ` -- `; reason of 8+ characters).
The line counts only while the `tests-removed` label is on the PR and its most recent application was by a
maintainer, after the last push or edit (a job removes the label on every push and edit). The same label also
approves guarded-path changes and added skip markers.

## The three CI jobs
- `test-integrity-label`: on push, reopen and edit, removes the `tests-removed` label.
- `test-integrity-list`: runs the PR's tests in list mode with a read-only token and uploads the list.
- `test-integrity`: judges, using the base commit's copy of the gate, the event's PR body and head sha, and live
  labels; it never runs PR code (except in the bootstrap case below).

## Known limits
- (a) Agents currently use the maintainer's GitHub token, so the label stops mistakes, not a deliberate
  self-approval (it stays visible in the PR timeline).
- (b) Approval is not bound to the exact head sha or body revision; it relies on the label reset job.
- (c) The skip check counts markers per file, so imported skip aliases or markers moved between tests are missed.
- (d) The source check is text-based.
- (e) Skips decided at run time (`skipTest()`, a `setUpClass` SkipTest, `pytest.skip()`) are not visible to listing.
- (f) The workflow file is PR-controlled until `test-integrity` is a required check on main.
- (g) The first PR (bootstrap) judges itself and is reviewed by hand.
- (h) Fork PRs fail closed.
- (i) A parametrised test case deleted from a test file the PR also changed is not caught by the source check when
  the PR's own list still reports it.
