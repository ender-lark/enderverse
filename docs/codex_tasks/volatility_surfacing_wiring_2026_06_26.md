# Codex wiring patch — surface the volatility opportunity converter in TODAY—DECIDE

**Filed:** 2026-06-26 by Claude Code · **Owner to apply:** Codex (owns the in-flight `today_decide` / `full_build_runner` insider + options WIP these seams sit next to) · **Workboard:** `VOL-OPP-CONVERTER-2026-06-25` (surfacing half)

## Context

The converter **engine is already on `main`** (PR #103, `src/volatility_opportunity_converter.py`, self-contained, 61 tests). This patch is the **surfacing wiring only** — an opt-in `volatility` payload in `today_decide` + the `full_build_runner` produce/demote seam. It was fully implemented and validated in the 2026-06-25 session (full suite 1758 pass on `codex/sell-gate-doctrine`) but is currently *uncommitted* in the shared worktree, interleaved with your insider + options WIP. This spec lets you apply it cleanly **after you commit your WIP**.

**Preconditions (all true on `codex/sell-gate-doctrine`):**
- `src/volatility_opportunity_converter.py` present on the branch — it's on `main` (#103) and also sits as an untracked file in the branch worktree; commit it on the branch (identical bytes) or merge `main` so the branch has it.
- The target-drift fix (`cd64af9`, `combined_positions` full-book read in `position_drift_check.load_actuals_from_positions_cache`) — **on the branch, not yet on main** — is required by `from_feed`'s drift read and by the regression tests below.
- Your options seam (`import options_surface as opt_surface`, the `options` payload key, `render_options_block_html`) is committed — the volatility render sits **immediately above** it.

**All changes are ADDITIVE** — they sit alongside the options/insider seams; do not remove or reorder those. Contract-C safe (demotion sets `action_state="WATCH"`, a valid state).

---

## 1. `src/today_decide.py`

**a. Import** — add right after `import options_surface as opt_surface`:
```python
import volatility_opportunity_converter as voc
```

**b. `build_today_decide_payload` signature** — add right after the `options: dict[str, Any] | None = None,` param:
```python
    volatility: dict[str, Any] | None = None,
```

**c. Returned payload dict** — add right after the `"options": options,` entry:
```python
        # Volatility opportunity surface (opt-in): a volatility_opportunity_converter result that
        # fuses Fundstrat calls + tape + target gaps + flow + event-risk into ONE staged command,
        # or None when this build didn't run the converter. Rendered LOUD (lead with the move).
        "volatility": volatility,
```

**d. `render_today_decide_html`** — add immediately **before** the options block (i.e., before the `options_payload = payload.get("options")` lines):
```python
    # Volatility opportunity block (opt-in): LOUD staged command — leads with the sized move,
    # gate + funding + honesty visible; honest-empty never silent. Rendered only when this build
    # ran the converter (payload key present). Placed above options: the regime command is the
    # most decision-forward element when a volatility event is live.
    volatility_payload = payload.get("volatility")
    if volatility_payload is not None:
        h.append(voc.render_command_html(volatility_payload))
```

---

## 2. `src/full_build_runner.py`

**a. Import** — add right after `import today_decide`:
```python
import volatility_opportunity_converter
```

**b. Demote + produce** — add immediately **before** the `feed["today_decide"] = today_decide.build_today_decide_payload(` call (this uses `account_positions`, `feed`, `today`, `now`, all already in scope there):
```python
    # Demote no-position sell-fast rows so a real held decision is never crowded out by loud
    # "sell fast" noise on names we don't own. Held tickers stay loud; avoid-new-exposure notes
    # stay as quiet new-buy-timing context (anti-passivity rail; see WORKBOARD VOL-OPP-CONVERTER).
    _combined_rows = (
        account_positions.get("combined_positions") if isinstance(account_positions, dict) else None
    ) or []
    _held_tickers = {
        str(r.get("ticker") or "").strip().upper()
        for r in _combined_rows if isinstance(r, dict)
    }
    feed["actions"] = volatility_opportunity_converter.demote_no_position_sells(
        feed.get("actions") or [], _held_tickers
    )
    # Fuse the live volatility regime (Fundstrat calls + tape + the fixed target-drift read + flow +
    # event-risk) into ONE staged command. Reads the already-assembled feed — no NEW live pulls —
    # and surfaces LOUD inside the today_decide payload (no build-and-forget).
    volatility_command = volatility_opportunity_converter.from_feed(feed, today=today, generated_at=now)
```

**c. Payload call** — add `volatility=volatility_command,` to the `today_decide.build_today_decide_payload(...)` argument list (alongside `accounts=`, `inst_states=`, `orphan_honesty=`, `today=`):
```python
        volatility=volatility_command,
```

---

## 3. `src/test_today_decide.py`

**a. `_payload` helper** — add `volatility=None` to its signature and pass it through:
```python
def _payload(goal=None, congruence_result=None, tmp_path=None, dispositions_path=None, feed=None, gates=None, today=TODAY, options=None, volatility=None):
    return build_today_decide_payload(
        ...
        options=options,
        volatility=volatility,
    )
```

**b. Append these tests** (mirror the existing options-block tests):
```python
def _volatility_command():
    import volatility_opportunity_converter as voc
    target_drift = {"status": "has_data", "rows": [
        {"ticker": "GOOGL", "direction": "UNDERSIZED", "actual_pct": 3.76, "target_pct": 8.0},
        {"ticker": "MU", "direction": "OVERSIZED", "actual_pct": 3.67, "target_pct": 3.0},
        {"ticker": "GRNY", "direction": "OVERSIZED", "actual_pct": 9.56, "target_pct": 3.0},
    ]}
    return voc.convert(
        target_drift=target_drift, book_value=1_923_513,
        holdings=[{"ticker": t, "market_value": 1} for t in ("GOOGL", "MU", "GRNY")],
        tape={"QQQ": {"pct_1d": -0.4, "reclaimed": False, "held_support": True},
              "SMH": {"pct_1d": -0.5, "reclaimed": False, "held_support": True, "is_wrapper": True},
              "GOOGL": {"pct_1d": -0.2, "held_up": True},
              "MU": {"pct_1d": -0.3, "event_confirmation": True}},
        fundstrat_calls=[{"ticker": "SMH", "stance": "BUY_DIP"}],
        event_risk={"state": "SUPPORTIVE"}, social_watch={"status": "not_checked"},
        as_of="2026-06-24", generated_at="x",
    )


def test_volatility_block_opt_in_does_not_change_default_render():
    assert "VOLATILITY OPPORTUNITY" not in render_today_decide_html(_payload())


def test_volatility_block_leads_with_staged_command():
    html = render_today_decide_html(_payload(volatility=_volatility_command()))
    assert "VOLATILITY OPPORTUNITY" in html
    assert "▶" in html                              # LEAD WITH THE MOVE
    assert "Stage GOOGL add" in html                    # sized add on the face
    assert "Do NOT chase MU" in html                    # what not to chase, loud
    assert "Gate" in html                               # what blocks it, visible
    assert "Funding" in html                            # how it's funded, visible
    assert "never an order" in html                     # no-execution rail on the face


def test_volatility_block_honest_empty_is_never_silent():
    import volatility_opportunity_converter as voc
    html = render_today_decide_html(_payload(volatility=voc.convert(target_drift=None, holdings=None)))
    assert "VOLATILITY OPPORTUNITY" in html             # labelled even when nothing actionable
```

---

## 4. (Include with this, since the branch has the drift fix) `src/test_target_weight_drift_preflight.py`

Add these 2 regression tests (lock the exact `account_positions.json` shape so the MISSING@0% bug can't return). Import `load_actuals_from_positions_cache` from `position_drift_check`, then:
```python
def test_account_positions_shape_reads_full_combined_book_not_tracked_only():
    # combined_positions (full book incl. untracked GOOGL/AVGO/MSFT) co-exists with a tracked-only
    # key that omits them; the drift read must measure the full book — never MISSING@0%.
    account_positions = {
        "snapshot_date": "2026-06-24", "sleeve_value": BOOK,
        "combined_positions": [
            {"ticker": "NVDA", "market_value": 0.12 * BOOK, "tracked": True},
            {"ticker": "GOOGL", "market_value": 0.0376 * BOOK, "tracked": False},
            {"ticker": "AVGO", "market_value": 0.0212 * BOOK, "tracked": False},
            {"ticker": "MSFT", "market_value": 0.0155 * BOOK, "tracked": False},
        ],
        "tracked_combined_positions": [{"ticker": "NVDA", "market_value": 0.12 * BOOK, "tracked": True}],
        "account_positions": [
            {"ticker": "NVDA", "market_value": 0.12 * BOOK, "account": "A", "tracked": True},
            {"ticker": "GOOGL", "market_value": 0.0376 * BOOK, "account": "B", "tracked": False},
        ],
    }
    actuals = {a.ticker: a for a in load_actuals_from_positions_cache(account_positions)}
    assert actuals["GOOGL"].pct_of_portfolio == pytest.approx(0.0376)
    assert "AVGO" in actuals and "MSFT" in actuals
    summary = target_weight_drift_summary(account_positions, BOOK, limit=20)
    by_ticker = {r["ticker"]: r for r in summary["rows"]}
    for tk in ("GOOGL", "AVGO", "MSFT"):
        assert by_ticker[tk]["direction"] == "UNDERSIZED"
        assert by_ticker[tk]["actual_pct"] > 0 and by_ticker[tk]["direction"] != "MISSING"


def test_combined_positions_preferred_over_tracked_only_key():
    account_positions = {
        "sleeve_value": BOOK,
        "combined_positions": [
            {"ticker": "GOOGL", "market_value": 0.04 * BOOK, "tracked": False},
            {"ticker": "NVDA", "market_value": 0.12 * BOOK, "tracked": True},
        ],
        "tracked_combined_positions": [{"ticker": "NVDA", "market_value": 0.12 * BOOK, "tracked": True}],
    }
    assert "GOOGL" in {a.ticker for a in load_actuals_from_positions_cache(account_positions)}
```

---

## Acceptance

- `python -m pytest src/test_today_decide.py src/test_full_build_runner.py src/test_target_weight_drift_preflight.py src/test_volatility_opportunity_converter.py -q` → green.
- In-process build sanity: `build_full_feed_from_files(...)` produces `feed["today_decide"]["volatility"]` (a converter result), demotes no-position sell-fast rows (e.g. RYF/XOP → `surface_role: context/backlog`, `action_state: WATCH`), and — with a fresh positions snapshot — a `⚠ STALE POSITIONS` stamp does NOT appear (guard fires only when the snapshot is >3 days old).
- `python src/verify_standard.py` green modulo the pre-existing `go_live_checklist` failures.
- Do NOT add a new top-level `feed[...]` key for the command (keep it inside the `today_decide` payload) — a top-level key trips `test_dashboard_parity_guardrail`.

## Notes

- These snippets are the exact, validated implementation from the 2026-06-25 session; the design + the corrected 6/24 numbers + the branch-divergence root-cause are in `docs/decision_surface_volatility_converter_2026_06_25.md` (also currently on the branch worktree).
- The converter's production `from_feed` is intentionally thin (reports `regime: NEUTRAL` off the cached feed, since the feed lacks structured tape/Fundstrat-stances/scored-event-risk) — it still surfaces the gap-driven staged adds. Enriching the feed so the scheduled build emits the full regime command is the separate follow-up already noted in the memory + the architecture doc.
