"""Confirms graph.py's news_blackout_gate actually short-circuits the whole
cycle — a blocked cycle should reach END with zero market data fetched and
no order ever proposed, not just "the field gets set somewhere."""

from app.agents.graph import build_graph


def test_blackout_short_circuits_before_any_data_fetch(monkeypatch):
    monkeypatch.setattr(
        "app.agents.news_blackout_gate.check_news_blackout",
        lambda: (True, "within 5min of high-impact release 'Test Event' at 12:30 UTC / 15:30 EAT"),
    )
    graph = build_graph()
    result = graph.invoke({"symbol": "SPY", "track": "track1_alpha_spreads"})

    assert result.get("news_blackout_reason") is not None
    assert "Test Event" in result["news_blackout_reason"]
    # Nothing downstream of the gate should have run at all.
    assert result.get("market_data") is None
    assert result.get("option_chain") is None
    assert result.get("technical_signal") is None
    assert result.get("proposed_order") is None
    assert result.get("risk_approved") is None


def test_clear_reaches_market_ingestion(monkeypatch):
    monkeypatch.setattr("app.agents.news_blackout_gate.check_news_blackout", lambda: (False, None))
    monkeypatch.setattr("app.agents.market_ingestion.get_recent_bars", lambda symbol: [])
    monkeypatch.setattr("app.agents.market_ingestion.get_option_chain", lambda symbol: [])
    monkeypatch.setattr("app.agents.market_ingestion.get_15m_bars", lambda symbol: [])
    monkeypatch.setattr("app.agents.market_ingestion.get_daily_bars", lambda symbol, limit=20: [])

    graph = build_graph()
    result = graph.invoke({"symbol": "SPY", "track": "track1_alpha_spreads"})

    assert result.get("news_blackout_reason") is None
    # market_ingestion ran (even with empty fetches) — proves the gate let
    # a clear cycle through rather than blocking everything unconditionally.
    assert result.get("market_data") == []
