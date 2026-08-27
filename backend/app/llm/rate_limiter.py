"""In-memory rolling-window call budget for LLM calls made by the live agent
loop subprocess. Single-process by design — only scripts/run_agent_loop.py's
subprocess makes budgeted calls; the Controls tab's "Test API" button calls
llm.client.test_provider() directly and is low-volume/manual, so it
deliberately doesn't share this budget."""

import time

from app.rate_limits import MAX_LLM_CALLS_PER_DAY, MAX_LLM_CALLS_PER_HOUR

HOUR_SECONDS = 3600
DAY_SECONDS = 86400


class LLMBudgetExceededError(Exception):
    pass


class _RollingWindowLimiter:
    def __init__(self) -> None:
        self._call_times: list[float] = []

    def check_and_record(self) -> None:
        now = time.monotonic()
        # Trim to the longer window; the shorter window's count is a subset.
        self._call_times = [t for t in self._call_times if now - t < DAY_SECONDS]

        hour_count = sum(1 for t in self._call_times if now - t < HOUR_SECONDS)
        day_count = len(self._call_times)

        if hour_count >= MAX_LLM_CALLS_PER_HOUR:
            raise LLMBudgetExceededError(f"{hour_count} LLM calls in the last hour >= cap {MAX_LLM_CALLS_PER_HOUR}")
        if day_count >= MAX_LLM_CALLS_PER_DAY:
            raise LLMBudgetExceededError(f"{day_count} LLM calls in the last 24h >= cap {MAX_LLM_CALLS_PER_DAY}")

        self._call_times.append(now)


_limiter = _RollingWindowLimiter()


def check_and_record() -> None:
    _limiter.check_and_record()
