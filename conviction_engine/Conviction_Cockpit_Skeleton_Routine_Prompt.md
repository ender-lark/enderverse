# Conviction Cockpit — Skeleton Run (Cloud Routine Prompt)

**Pairs with** `Conviction_Engine_Runtime_Setup.md` (the overview). This is the **runnable prompt** — paste the block below into a Claude Code cloud routine.

Skeleton-first: only the two critical sources (**portfolio + prices**). SCOUT posture — read and display only; never trade, never write canonical state. Macro / fresh-signal / most per-name conviction render thin until later phases (that's expected and still valid).

---

## Setup (one-time)

- **Where:** a Claude Code cloud routine, repo `github.com/ender-lark/enderverse` cloned (engine in `conviction_engine/`).
- **Connectors:** Notion (for 📊 Latest Portfolio) + UW (for prices) — already connected in your other routines.
- **Cadence:** after Morning Scan, or on-demand.
- **Credentials:** handled by the connectors; nothing to put in the prompt.

---

## THE PROMPT  (copy everything in this block into the routine)

```
You are running the Conviction Cockpit skeleton routine.
POSTURE: SCOUT — read and display only. Never place trades, never write to any
canonical Notion page/DB (📊 Latest Portfolio, 🧠 Live Theses, etc.), never size
positions. Your only output is the rendered cockpit plus a short report.

Work in the enderverse repo clone; the engine is in conviction_engine/. Run all
Python from that folder.

STEP 1 — Fetch the book.
Use the Notion connector to fetch page 35ac5031-4bb6-81fc-b792-e50bf86d63f4
(📊 Latest Portfolio). Keep the FULL returned text verbatim — the parser needs
the "Per-Ticker Aggregation" table. Note the "As of:" date near the top.

STEP 2 — Pull prices.
For EACH of these 10 tickers, call get_ticker_close_prices(ticker, "1Y") on the
UW connector (timeframe MUST be "1Y" — "3M" is too short for the lookback):
    SMH, IGV, GRNY, IBIT, URA, REMX, XLF, GDX, VOLT, SPY
Collect them as a dict {ticker: response}.

STEP 3 — Build the feed (code execution, in conviction_engine/).
    import json, re
    from runtime_skeleton import build_skeleton_feed, SkeletonFeedError
    theses = json.load(open("theses.json"))          # skeleton: committed theses
    page   = <<the STEP 1 page text>>
    uw     = <<the STEP 2 {ticker: response} dict>>
    try:
        feed = build_skeleton_feed(page, uw, theses, as_of="<<book As-of date YYYY-MM-DD>>")
    except SkeletonFeedError as e:
        # a critical source delivered no data, or the feed failed validation
        print("ABORT:", e); raise SystemExit(1)      # do NOT render a partial cockpit
    json.dump(feed, open("/tmp/cockpit_feed.json", "w"))

STEP 4 — Render the cockpit.
Embed the live feed into the cockpit component, then present it:
    src = open("conviction_cockpit_v5.jsx").read()
    src = re.sub(r"const FEED = \{[\s\S]*?\n\};",
                 "const FEED = " + json.dumps(feed, indent=2) + ";",
                 src, count=1)
    open("/tmp/conviction_cockpit_live.jsx", "w").write(src)
Present /tmp/conviction_cockpit_live.jsx as the cockpit (it renders the live feed).

STEP 5 — Report (one short paragraph, no trading language).
State: holdings group count + total positions, the leading sleeves from rotation,
and the source-stamp date. Note that macro and fresh-signals are thin because this
is the skeleton (uw_macro and the Fundstrat plugs come in later phases).

FIRST RUN ONLY — ratify:
Cross-check the holdings and the sleeve rotation against the live Investing 2026
read. If they agree, say the skeleton is ratified. If they disagree, trust the
canonical Investing 2026 system and report the discrepancy (do not "fix" by
overriding the canonical state).
```

---

## Notes

- **`theses.json` is the committed snapshot (~14 names with stance).** Held names not in it render as Tier-C "unassessed" conviction. **Fast-follow upgrade:** fetch 🧠 Live Theses (DB `1286877d625f4b3eb2bedcce9bb81266`) and pass those rows as `theses` for fresh, full conviction.
- **Timeframe is `"1Y"`** on every price pull — `pct_return` needs more than the 63-bar lookback, and `"3M"` returns ~63 closes (one short → NO DATA rows).
- **Critical-missing aborts by design.** If the book table is empty or prices come back denied/empty for a critical source, `build_skeleton_feed` raises `SkeletonFeedError` and the routine stops rather than rendering a partial cockpit.
- **Phased rollout** (each phase = add one plug + its adapter, re-run, eyeball the new section):
  - **Phase 1 (this routine):** `portfolio` + `uw_price` → Holdings + sleeve rotation.
  - **Phase 2:** `uw_macro` → the Market-read macro block.
  - **Phase 3:** `fundstrat_bible` + `fundstrat_daily` → Today's actions / fresh signals + per-name conviction.
  - **Phase 4:** `meridian` → thematic context.

---

## First-run ratification checklist

1. STEP 3 produced a feed with no `SkeletonFeedError` (book + all 10 prices delivered).
2. The cockpit renders; the source-stamp date matches the book's "As of" date.
3. Holdings groups + the names within them match the live Investing 2026 read.
4. Sleeve rotation leaders look right vs the tape (AI/semis leading, the burned sleeves lagging, etc.).
5. Log the ratification (Build Plan / 📖 Decisions Log, Research Update) and move to Phase 2.
