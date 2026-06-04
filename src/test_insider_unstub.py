"""
test_insider_unstub.py — v12.0 insider feed un-stub.

Covers the producer-side normalizer (insider_activity_scan.normalize_uw_insider:
raw UW get_insider_transactions -> the insider_data.json schema) and the
consumer-side empty-stub honesty guard (session_orchestrator._run_insider).
"""

# insider_activity_scan FIRST: importing session_orchestrator runs a module-level
# sys.path.insert(0, "/mnt/project"), which in a dual-checkout sandbox can shadow the
# repo copy with a stale one. Binding ia first caches the repo copy in sys.modules.
import insider_activity_scan as ia
import session_orchestrator as so


RAW_UW = [
    # CEO open-market purchase, ~$1.2M — discretionary, C-suite, not a plan -> BULLISH
    {"ticker": "NVDA", "transaction_code": "P", "insider_title": "Chief Executive Officer",
     "insider_name": "Jane Doe", "amount": 10000, "price": 120.0,
     "transaction_date": "2026-05-20"},
    # Director sale, $600K — no catalyst supplied, so not bearish here
    {"ticker": "NVDA", "transaction_code": "S", "insider_title": "Director",
     "insider_name": "John Roe", "amount": 5000, "price": 120.0,
     "transaction_date": "2026-05-21"},
    # RSU vesting (code A / type RSU_VEST) -> noise
    {"ticker": "MU", "transaction_code": "A", "transaction_type": "RSU_VEST",
     "insider_title": "CFO", "insider_name": "A B", "amount": 2000, "price": 100.0,
     "transaction_date": "2026-05-19"},
    # 10b5-1 planned buy -> noise (excluded despite being a purchase)
    {"ticker": "MU", "transaction_code": "P", "insider_title": "CEO",
     "insider_name": "C D", "amount": 100, "price": 100.0,
     "transaction_date": "2026-05-18", "rule_10b5_1": True},
]


def test_normalize_computes_value_and_preserves_title():
    data = ia.normalize_uw_insider(RAW_UW)
    assert set(data.keys()) == {"NVDA", "MU"}
    ceo_buy = data["NVDA"][0]
    assert ceo_buy["value"] == 1200000.0          # amount * price (UW gives no value)
    assert ceo_buy["insider_title"] == "Chief Executive Officer"   # preserved verbatim
    assert ceo_buy["transaction_code"] == "P"
    # 10b5-1 flag carried through
    plan_buy = [t for t in data["MU"] if t["transaction_code"] == "P"][0]
    assert plan_buy["rule_10b5_1"] is True


def test_normalize_title_fallback_from_booleans():
    raw = [{"ticker": "XLF", "transaction_code": "P", "is_director": True,
            "amount": 1000, "price": 40.0, "transaction_date": "2026-05-20"}]
    data = ia.normalize_uw_insider(raw)
    assert data["XLF"][0]["insider_title"] == "DIRECTOR"


def test_normalize_handles_ticker_keyed_dict_and_data_wrapper():
    # dict keyed by ticker
    d1 = ia.normalize_uw_insider({"NVDA": [RAW_UW[0]]})
    assert "NVDA" in d1 and len(d1["NVDA"]) == 1
    # raw UW response with a "data" list
    d2 = ia.normalize_uw_insider({"data": RAW_UW})
    assert set(d2.keys()) == {"NVDA", "MU"}


def test_normalized_data_classifies_end_to_end():
    data = ia.normalize_uw_insider(RAW_UW, trump_tickers=[])
    positions = [{"ticker": "NVDA"}, {"ticker": "MU"}]
    report = ia.scan(positions, data)
    # NVDA: the >$500K C-suite purchase makes it a real signal, not noise
    assert any(s.ticker == "NVDA" for s in report.bullish)
    assert not any(s.ticker == "NVDA" for s in report.noise)
    # MU: only RSU vest + 10b5-1 buy -> noise
    assert any(s.ticker == "MU" for s in report.noise)


# ---------- empty-stub honesty guard ----------

def test_empty_stub_surfaces_not_evaluated():
    stub = {"_comment": "populate me", "_schema": "...", "NVDA": [], "MU": []}
    res = so._run_insider([{"ticker": "NVDA"}, {"ticker": "MU"}],
                          stub, None, None, None)
    assert res.available is False
    assert "cache empty (stub)" in res.surface_line


def test_populated_cache_is_evaluated():
    data = ia.normalize_uw_insider([RAW_UW[0]])   # one real CEO buy
    res = so._run_insider([{"ticker": "NVDA"}], data, None, None, None)
    assert res.available is True
    assert "cache empty" not in res.surface_line


def test_no_cache_is_unavailable():
    res = so._run_insider([{"ticker": "NVDA"}], None, None, None, None)
    assert res.available is False
    assert "no insider data" in res.surface_line.lower()


def test_preflight_normalizes_raw_catalyst_rows_for_insider_scan():
    insider = ia.normalize_uw_insider([{
        "ticker": "NVDA",
        "transaction_code": "S",
        "insider_title": "Chief Financial Officer",
        "insider_name": "Jane Roe",
        "amount": 10000,
        "price": 120.0,
        "transaction_date": "2026-06-04",
    }])
    raw_catalysts = [
        {"ticker": "NVDA", "date": "2026-06-10T00:00:00+00:00", "name": "Q2 earnings"}
    ]
    res = so._run_insider([{"ticker": "NVDA"}], insider, raw_catalysts, None, None)
    assert res.available is True
    assert res.priority == "HIGH"
    assert res.payload["flagged"] == 1


def test_orchestrator_normalizes_wrapped_catalyst_cache():
    insider = ia.normalize_uw_insider([{
        "ticker": "NVDA",
        "transaction_code": "S",
        "insider_title": "Chief Financial Officer",
        "insider_name": "Jane Roe",
        "amount": 10000,
        "price": 120.0,
        "transaction_date": "2026-06-04",
    }])
    d = so.orchestrate(
        positions=[{"ticker": "NVDA"}],
        theses=[],
        sleeve_total=1_000_000,
        insider_data=insider,
        catalysts={"catalysts": [
            {"ticker": "NVDA", "date": "2026-06-10T00:00:00+00:00", "name": "Q2 earnings"}
        ]},
    )
    res = next(s for s in d.subsystems if s.name == "INSIDER ACTIVITY")
    assert res.payload["flagged"] == 1
