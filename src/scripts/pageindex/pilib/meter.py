"""Counts every model call a run makes, sums tokens and cost, and refuses the call over the cap."""
from __future__ import annotations

import threading


class CallCapExceeded(BaseException):
    """BaseException on purpose: retry loops (ours and PageIndex's) catch Exception and would swallow the abort."""


class LLMMeter:
    """Counts every litellm completion call (sync and async), sums usage and cost, and refuses the call that
    would exceed the cap. Patching the module functions covers every call site that goes through the module
    (litellm.completion / litellm.acompletion), which is how both our summaries and PageIndex call it."""

    def __init__(self, cap: int):
        self.cap, self.calls, self.failures = cap, 0, 0
        self.prompt_tokens = self.completion_tokens = self.reasoning_tokens = 0
        self.cost = 0.0
        self.cost_unknown = 0
        self.exceeded = False
        self._lock = threading.Lock()
        self._orig = None

    def _begin(self):
        with self._lock:
            if self.calls >= self.cap:
                self.exceeded = True
                raise CallCapExceeded(f"model call cap {self.cap} reached")
            self.calls += 1

    def _record(self, response):
        import litellm
        usage = getattr(response, "usage", None)
        try:
            cost = float(litellm.completion_cost(completion_response=response) or 0.0)
            known = True
        except Exception:
            cost, known = 0.0, False
        with self._lock:
            if usage is not None:
                self.prompt_tokens += getattr(usage, "prompt_tokens", 0) or 0
                self.completion_tokens += getattr(usage, "completion_tokens", 0) or 0
                details = getattr(usage, "completion_tokens_details", None)
                self.reasoning_tokens += (getattr(details, "reasoning_tokens", 0) or 0) if details else 0
            self.cost += cost
            self.cost_unknown += 0 if known else 1

    def _fail(self):
        with self._lock:
            self.failures += 1

    def __enter__(self):
        import litellm
        self._orig = (litellm.completion, litellm.acompletion)
        sync_fn, async_fn = self._orig
        meter = self

        def completion(*a, **kw):
            meter._begin()
            try:
                r = sync_fn(*a, **kw)
            except Exception:
                meter._fail()
                raise
            meter._record(r)
            return r

        async def acompletion(*a, **kw):
            meter._begin()
            try:
                r = await async_fn(*a, **kw)
            except Exception:
                meter._fail()
                raise
            meter._record(r)
            return r

        litellm.completion, litellm.acompletion = completion, acompletion
        return self

    def __exit__(self, *exc):
        import litellm
        litellm.completion, litellm.acompletion = self._orig
        return False

    def summary(self) -> dict:
        return {"llm_calls": self.calls, "llm_failures": self.failures, "prompt_tokens": self.prompt_tokens,
                "completion_tokens": self.completion_tokens, "reasoning_tokens": self.reasoning_tokens,
                "cost_usd": round(self.cost, 4), "cost_unknown_calls": self.cost_unknown, "call_cap": self.cap}
