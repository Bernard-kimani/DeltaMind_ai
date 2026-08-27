"""Red-Folder News Blackout Gate — the very first node in the graph (see
graph.py's entry point), deliberately before market_ingestion so a blocked
cycle pays for zero REST calls, zero LLM calls, and zero risk of ever
proposing an order during a scheduled high-impact macro release.

Pure Python, no LLM — see app/quant/news_calendar.py for the calendar itself
and why this is a deterministic gate, not something the LLM is asked to
judge. risk_gate.py re-checks this same condition as a backstop, in case a
slow cycle (e.g. a long LLM call) drifts across a blackout boundary between
this gate and final approval.
"""

from app.agents.state import AgentState
from app.quant.news_calendar import check_news_blackout


def run(state: AgentState) -> dict:
    blocked, reason = check_news_blackout()
    return {"news_blackout_reason": reason if blocked else None}
