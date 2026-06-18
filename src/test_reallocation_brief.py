import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from reallocation_brief import build_reallocation_brief


def _feed():
    return {
        "generated_at": "2026-06-07T14:00:00+00:00",
        "uw_action_runbook": {
            "rows": [
                {
                    "mode": "portfolio_reallocation",
                    "market_checks": ["ETF_TIDE", "SECTOR_TIDE"],
                    "ticker_checks": ["TICKER_OHLC", "TICKER_FLOW_RECENT"],
                    "downgrade_when": "live flow/price argues for waiting",
                }
            ]
        },
    }


def _positions(snapshot_date="2026-05-31"):
    total = 1_000_000.0
    weights = {
        "SMH": 9.0,
        "MAGS": 8.0,
        "IGV": 5.5,
        "GRNY": 9.0,
        "GRNJ": 7.0,
        "NVDA": 6.0,
        "MU": 3.0,
        "LEU": 4.0,
        "BMNR": 2.0,
    }
    return {
        "snapshot_date": snapshot_date,
        "sleeve_value": total,
        "positions": [
            {"ticker": ticker, "market_value": pct / 100.0 * total}
            for ticker, pct in weights.items()
        ],
    }


def test_reallocation_brief_labels_stale_positions_as_test_data():
    block = build_reallocation_brief(_feed(), _positions(), as_of="2026-06-07")

    assert block["status"] == "test_data_only"
    assert block["candidate_only"] is True
    assert "test data only" in block["line"]
    assert block["counts"]["adds"] > 0
    assert block["counts"]["trims"] > 0
    assert block["funding"]["allocated_usd"] > 0
    assert all(row["ticker"] != "GRNJ" for row in block["trims"])
    assert all(
        funding["ticker"] != "GRNJ"
        for row in block["rows"]
        for funding in row.get("funded_by") or []
    )
    assert any("GRNJ" in note and "protected" in note for note in block["notes"])
    assert any("positions snapshot 2026-05-31" in blocker for blocker in block["blockers"])
    assert "same-session UW price/flow" in block["rows"][0]["blockers"]
    assert "TICKER_FLOW_RECENT" in block["rows"][0]["uw_ticker_checks"]
    assert block["rows"][0]["capital_efficiency"]["summary"]
    assert "perfect bottom" in block["rows"][0]["capital_efficiency"]["timing_balance"]
    assert block["rows"][0]["options_review_prompt"]["status"] == "review_only"
    assert "Maximum loss" in block["rows"][0]["options_review_prompt"]["max_loss_gate"]
    assert block["rows"][0]["disconfirmation"] == "live flow/price argues for waiting"
    past_sequence_rows = [row for row in block["rows"] if row["sequence_state"] == "past_gate"]
    assert past_sequence_rows
    assert any(
        "legacy catalyst sequencing date has passed" in blocker
        for blocker in past_sequence_rows[0]["blockers"]
    )
    assert "no trades are executed" in block["honesty_rule"]
    assert block["options_gate"]["status"] == "review_only"
    assert "defined-risk review prompts" in block["options_gate"]["line"]
    assert block["capital_efficiency"]["summary"]
    assert any(row["ticker"] == "BMNR" and row["status"] == "undecided_recheck" for row in block["special_reviews"])


def test_reallocation_brief_same_day_positions_are_candidate_only_not_final():
    block = build_reallocation_brief(_feed(), _positions("2026-06-07"), as_of="2026-06-07")

    assert block["status"] == "candidate_only"
    assert block["candidate_only"] is True
    assert "Same-day positions" in block["honesty_rule"]
    assert "test-data" not in block["honesty_rule"]
    assert all("latest current positions" not in row["blockers"] for row in block["rows"])
    assert any("tax/account constraints" in blocker for blocker in block["blockers"])
    assert not any("max-action capacity not supplied" in blocker for blocker in block["blockers"])


def _account_positions(snapshot_date="2026-06-07", total=1_000_000.0):
    """All-account cache where GOOGL (8% target) is HELD but UNTRACKED at ~4.74%
    of book, and MU (3% target) is held ABOVE its target. Mirrors the live
    account_positions.json shape: a tracked sleeve list plus untracked names that
    the brief's current-weight read must still net in.

    The book total here matches the positions cache (both share ``sleeve_value``
    in production: positions.json and account_positions.json both = $1.918M).
    GOOGL = 4.7389% of book -> an 8% target leaves a ~3.26% gap (~$32.6k on a
    $1M book), NOT the full 8% ($80k). MU = 3.5% > its 3% target -> no add. An
    option contract and a crypto coin are present to prove they are excluded
    from the equity-weight read.
    """
    rows = [
        # Untracked held single name at ~4.74% (the GOOGL bug class), split so
        # the multi-account rows must net to ONE row.
        {"ticker": "GOOGL", "market_value": 0.030 * total, "shares": 80.0,
         "account": "Joint *2063", "owner": "Parents", "tracked": False,
         "asset_type": "Common Stock"},
        {"ticker": "GOOGL", "market_value": 0.017389 * total, "shares": 46.0,
         "account": "Individual *1088", "owner": "SKB", "tracked": False,
         "asset_type": "Common Stock"},
        # Held ABOVE its target -> no add expected.
        {"ticker": "MU", "market_value": 0.035 * total, "shares": 100.0,
         "account": "Individual *1088", "owner": "SKB", "tracked": True,
         "asset_type": "Common Stock"},
        # A funding wrapper, sized large enough that the pool reaches GOOGL (the
        # T1 name ranked just under NVDA) so it surfaces as a funded add row.
        {"ticker": "GRNY", "market_value": 0.30 * total, "shares": 300.0,
         "account": "Individual *1088", "owner": "SKB", "tracked": True,
         "asset_type": "ETF"},
        # An OPTION on GOOGL -> must be excluded from the equity-weight read.
        {"ticker": "GOOGL", "market_value": 5_000.0, "shares": 1.0,
         "account": "Individual *1088", "owner": "SKB", "tracked": False,
         "asset_type": "option", "description": "GOOGL 200 Call 2027-01-15",
         "option": {"underlying": "GOOGL"}},
        # A crypto coin -> must be excluded from the equity-weight read.
        {"ticker": "ETH", "market_value": 7_500.0, "shares": 2.0,
         "account": "Robinhood Crypto", "owner": "SKB", "tracked": False,
         "asset_type": "Cryptocurrency"},
    ]
    return {
        "snapshot_date": snapshot_date,
        "sleeve_value": total,
        "account_positions": rows,
    }


def test_reallocation_brief_untracked_held_name_reads_true_weight_and_gap_sizes():
    """Regression for reallocation_current_pct_zero_bug_2026_06_18:

    A held-but-untracked name (GOOGL ~4.7%) with an 8% target must read its TRUE
    current weight (~4.7%, NOT 0) and size the add to the GAP (~3.3% of book,
    ~$62.5k), not the full target ($153k). A name already at/above its target
    produces no add. Options and crypto lots do not count as equity weight.
    """
    feed = dict(_feed(), generated_at="2026-06-07T14:00:00+00:00")
    positions_cache = _positions("2026-06-07")
    account_positions = _account_positions("2026-06-07")

    block = build_reallocation_brief(
        feed,
        positions_cache,
        as_of="2026-06-07",
        account_positions=account_positions,
    )

    rows = {row["ticker"]: row for row in block["rows"]}
    assert "GOOGL" in rows, "held untracked GOOGL should surface as an add candidate"
    googl = rows["GOOGL"]

    # TRUE current weight, not the buggy 0.
    assert abs(googl["current_pct"] - 4.7389) < 0.01
    assert abs(googl["effective_current_pct"] - 4.7389) < 0.01
    assert googl["current_pct"] > 0

    # Gap sizing: ~3.26% of the $1M book book, ~$32.6k -- NOT the full 8% ($80k).
    assert abs(googl["notional_usd"] - 32_611.0) < 1_000.0
    assert googl["notional_usd"] < 60_000.0  # decisively below the full-target bug size

    # The netted GOOGL option/crypto lots must not inflate the equity weight:
    # the $5k option + crypto are excluded, so the read stays at the share weight.
    assert googl["target_pct"] == 8.0

    # A name already above its target gets no add.
    assert "MU" not in rows, "MU is above its 3% target -> no add"


def test_reallocation_brief_falls_back_to_tracked_positions_without_account_cache():
    """Without an account cache, the brief still works off the tracked positions
    cache (no regression for callers that do not supply account_positions)."""
    block = build_reallocation_brief(
        _feed(), _positions("2026-06-07"), as_of="2026-06-07", account_positions=None
    )
    assert block["status"] == "candidate_only"
    assert block["counts"]["adds"] > 0
