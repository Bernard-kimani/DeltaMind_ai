"""Single source of truth for safety-floor constants shared by the CLI
(scripts/run_agent_loop.py) and the API (api/routes_engine.py) — both
enforcement points need the same floor or they drift apart."""

MIN_INTERVAL_SECONDS = 60

# ~15 minutes of total failure at the recommended 300s interval before the
# loop gives up rather than retrying a dead API key/credential forever.
CONSECUTIVE_FAILED_PASSES_THRESHOLD = 3

# Backstop against a shortened interval or a grown watchlist, not a routine
# limiter at recommended settings (15 symbols x 2 calls/symbol x 300s
# interval = up to 360/hour worst case already).
MAX_LLM_CALLS_PER_HOUR = 300
MAX_LLM_CALLS_PER_DAY = 2000

# Distinct exit code so agent_loop_manager.py's watchdog can tell "the
# circuit breaker tripped, needs a human" apart from "crashed, safe to
# auto-restart."
CIRCUIT_BREAKER_EXIT_CODE = 3
