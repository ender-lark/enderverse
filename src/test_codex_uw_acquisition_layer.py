from codex_uw.acquisition import _count, build_opportunity_observation, build_parabolic_entry
from codex_uw.merge import merge_opportunity, merge_parabolic
from codex_uw.orchestrator import _availability, _availability_has_blockers
from codex_uw.endpoints import UWEndpoints, validate_endpoint_path


class FakeClient:
    def __init__(self):
        self.calls = []

    def get_json(self, path_template, *, path_params=None, params=None):
        self.calls.append((path_template, path_params or {}, params or {}))
        tk = (path_params or {}).get("ticker", "TST")
        if path_template == UWEndpoints.TICKER_EARNINGS:
            return {"data": [{"reported_eps": "1.2", "surprise_percentage": "15"},
                             {"reported_eps": None, "surprise_percentage": None}]}
        if path_template == UWEndpoints.TICKER_OHLC:
            return {"data": [{"date": "2026-01-01", "c": "10.0"},
                             {"date": "2026-01-02", "c": "10.5"}]}
        if path_template == UWEndpoints.TICKER_INCOME_STATEMENTS:
            return {"data": [{"total_revenue": "100", "operating_income": "20"}]}
        if path_template == UWEndpoints.TICKER_INFO:
            return {"data": {"ticker": tk}, "price": "11.0"}
        if path_template == UWEndpoints.TICKER_FLOW_ALERTS:
            return {"data": [{"type": "call", "total_premium": "900000",
                              "total_ask_side_prem": "800000", "has_sweep": True}]}
        if path_template == UWEndpoints.TICKER_OI_CHANGE:
            return {"data": [{"option_symbol": f"{tk}260605C00010000",
                              "oi_diff_plain": "1000", "oi_change": "0.35"}]}
        if path_template == UWEndpoints.DARKPOOL_TICKER:
            return {"data": [{"premium": "5000000", "executed_at": "2026-06-01T14:30:00Z",
                              "nbbo_ask": "10.1", "nbbo_bid": "9.9", "price": "10.2"}]}
        raise AssertionError(f"unexpected endpoint {path_template}")


def test_parabolic_entry_is_normalized_and_counts_sources():
    pull = build_parabolic_entry(FakeClient(), "tst")
    assert pull.ok
    assert pull.ticker == "TST"
    assert pull.entry["earnings"][0]["reported_eps"] == "1.2"
    assert pull.entry["prices"][0]["close"] == "10.0"
    assert pull.entry["income"][0]["revenue"] == "100"
    assert pull.entry["info"]["price"] == "11.0"
    assert pull.source_counts == {"earnings": 2, "prices": 2, "income": 1, "info": 1}


def test_opportunity_observation_is_normalized_without_raw_wrappers():
    pull = build_opportunity_observation(FakeClient(), "abc")
    assert pull.ok
    assert pull.ticker == "ABC"
    assert "flow" in pull.observation
    assert "oi" in pull.observation
    assert "dark_pool" in pull.observation
    assert "data" not in pull.observation
    assert pull.source_counts["flow"] == 1


def test_merge_outputs_scorer_bundle_shapes():
    para = merge_parabolic([
        {"ticker": "AAA", "ok": True, "entry": {"info": {}}},
        {"ticker": "BBB", "ok": False, "error": "x"},
    ], "2026-06-04")
    assert para["as_of"] == "2026-06-04"
    assert para["tickers"] == {"AAA": {"info": {}}}
    assert para["skipped"][0]["ticker"] == "BBB"

    opp = merge_opportunity([
        {"ticker": "AAA", "ok": True, "observation": {"flow": {}}},
        {"ticker": "CCC", "ok": True, "observation": {}},
    ], "2026-06-04")
    assert opp["universe"] == ["AAA"]
    assert opp["observations"]["AAA"] == {"flow": {}}
    assert opp["skipped"] == [{"ticker": "CCC", "error": "empty normalized observation"}]


def test_endpoint_guard_rejects_common_hallucinations():
    validate_endpoint_path("/api/stock/NVDA/flow-alerts")
    try:
        validate_endpoint_path("/api/v1/options/flow")
    except ValueError:
        return
    raise AssertionError("expected hallucinated endpoint to be rejected")


def test_availability_marks_dark_sources_and_missing_normalized_keys():
    summary = _availability([
        {"ticker": "AAA", "ok": True, "source_counts": {"flow": 2}, "observation": {"flow": {}}},
        {"ticker": "BBB", "ok": True, "source_counts": {"flow": 0}, "observation": {}},
        {"ticker": "CCC", "ok": False},
    ], {"flow"}, {"flow"}, min_source_count=1)
    assert summary["dark_sources"] == {"flow": ["BBB"]}
    assert summary["missing_normalized"] == {"flow": ["AAA"]}
    assert summary["failed_entries"] == ["CCC"]
    assert _availability_has_blockers(summary, allow_empty_sources=True) is True


def test_availability_can_warn_on_empty_sources_without_blocking():
    summary = _availability([
        {"ticker": "BBB", "ok": True, "source_counts": {"flow": 0}, "observation": {}},
    ], {"flow"}, {"flow"}, min_source_count=1)

    assert summary["dark_sources"] == {"flow": ["BBB"]}
    assert summary["missing_normalized"] == {}
    assert _availability_has_blockers(summary, allow_empty_sources=False) is True
    assert _availability_has_blockers(summary, allow_empty_sources=True) is False


def test_count_preserves_empty_wrapped_rows():
    assert _count({"data": []}) == 0
    assert _count({"result": {"data": []}}) == 0
    assert _count({"data": [{"ticker": "ABC"}]}) == 1
    assert _count({"data": {"ticker": "ABC"}}) == 1
