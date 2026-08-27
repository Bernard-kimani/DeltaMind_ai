# Running Continuously on Local Windows (3-Day Test Window)

What the code now handles automatically, and the two things you still need to do by hand.

## What's automatic now

- **Subprocess crash recovery**: if the trading-loop subprocess dies unexpectedly (not from you clicking Stop), `agent_loop_manager.py`'s watchdog thread notices within ~15s and restarts it automatically, with increasing backoff (5s, 15s, 30s, 60s, then 120s per retry), up to 20 attempts. The Controls page's status area shows `auto_restart_count` so you can see if it's been flapping.
- **Circuit breaker**: if every symbol fails for 3 consecutive full passes (a dead API key, a sustained outage — not a one-off blip), the loop deliberately stops itself rather than retrying forever, and the watchdog does **not** auto-restart it (that would just repeat the same failure). The Controls page shows `circuit_breaker_tripped: true` when this happens — check the Logs tab for the actual error, fix it, then click Start again.
- **Auto-resume after a backend restart**: if the FastAPI backend process itself restarts (you restart it, an editor/IDE relaunches it, etc.) while the engine was running, it automatically resumes trading with the same symbols/track/interval/thresholds — no need to notice and click Start again.
- **Rate limiting**: the loop won't exceed 300 LLM calls/hour or 2000/day regardless of how the interval or watchlist is configured, and won't accept an interval below 60 seconds.
- **Sleep prevention**: the loop tells Windows not to go to inactivity sleep while it's running (`SetThreadExecutionState`), re-asserted once per pass.

## What you still need to do

1. **Keep the laptop plugged in and don't close the lid.** `SetThreadExecutionState` only blocks *inactivity* sleep — a closed lid or manual sleep/shutdown stops everything regardless of what the code does.
2. **Set Windows power settings to never sleep on AC power** for the 3-day window, as a belt-and-suspenders alongside the code-level sleep prevention (Settings → System → Power & battery → Screen and sleep → "On battery/plugged in, put my device to sleep" → Never).

## What's explicitly NOT covered

A full Windows reboot (e.g. a forced Windows Update restart) will stop both the backend and the trading loop — there's no Task Scheduler auto-start configured for this window (deliberately skipped as unnecessary scope for a 3-day test; revisit if this becomes a real gap). If the machine reboots unexpectedly, you'll need to manually restart the backend (`uvicorn app.main:app`) — the engine will then auto-resume on its own once the backend is back up, per the auto-resume behavior above.
