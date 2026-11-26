"""pytest plugin for the test-integrity gate: writes one JSON line per collected item to $TI_OUT.

Loaded as `python3 -m pytest --collect-only -q -p ti_pytest_plugin` with PYTHONPATH set to this folder
(see ti-list-pytest.py). skipped is true for a `skip` mark, or a `skipif` mark whose first argument
(or `condition=`) is the bool True; string conditions and imperative pytest.skip() are only known at
run time and count as not skipped.
"""
import json
import os


def _skipped(item):
    # unittest.TestCase items: @unittest.skip* sets __unittest_skip__ on the method or the class
    obj = getattr(item, "obj", None)
    cls = getattr(item, "cls", None)
    if getattr(obj, "__unittest_skip__", False) or getattr(cls, "__unittest_skip__", False):
        return True
    if any(True for _ in item.iter_markers("skip")):
        return True
    for m in item.iter_markers("skipif"):
        cond = m.args[0] if m.args else m.kwargs.get("condition")
        if cond is True:
            return True
    return False


def pytest_collection_finish(session):
    out = os.environ.get("TI_OUT")
    if not out:
        return
    with open(out, "w", encoding="utf-8") as f:
        for item in session.items:
            f.write(json.dumps({"id": item.nodeid, "skipped": _skipped(item)}) + "\n")
