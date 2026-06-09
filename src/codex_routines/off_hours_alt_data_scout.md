# Off-Hours Alt-Data Scout Routine

## Objective

Use off-hours Codex time to find external evidence that can raise conviction,
lower conviction, or close research loops before trading hours. This routine is
research-only: it routes evidence into Research Queue, Signal Log, Social Watch,
or Event Risk, and never turns alt-data alone into trades, sizing, or execution
instructions.

## Start Of Run

1. Append a started receipt:
   `python src/cloud_routine_receipts.py --routine-id investing-os-off-hours-alt-data-scout --status started --run-source scheduled --summary "off-hours alt-data scout started"`
2. Anchor on current system state before searching:
   - `python src/live_status.py --format text`
   - `python src/uw_action_runbook.py --feed src/latest_cockpit_feed.json --format text`
   - current Research Queue, open reviews, live theses, actions, event-risk rows,
     and material holdings.
3. Treat missing inputs as dark or not_checked. Do not infer checked-clear status
   from a missing connector, API, file, or cache.

## Source Priority

1. Primary filings and events: SEC EDGAR company submissions, fresh 8-Ks,
   prospectus supplements, ATM or dilution updates, Form 4s, 13F-window context,
   legal/regulatory catalysts, and company primary releases.
2. Current portfolio market data: UW broad tape, sector/ETF tide, ticker flow,
   dark pool, OI change, analyst changes, insider flow, institutional ownership,
   and congressional trades when accessible.
3. Prediction markets: UW unusual prediction markets plus public Polymarket or
   Kalshi read endpoints where relevant to active exposures. Insider-like labels
   are leads only; require independent confirmation before escalation.
4. Curated RSS/Substack-style sources: public, explicit feeds only. Summarize
   claims and links, not raw copyrighted or paywalled bodies.
5. Social: use only supplied caches or reliable compliant APIs. Direct Reddit
   remains disabled unless official OAuth access works. Social is watch-only and
   requires non-social confirmation before action escalation.

## Noise Filters

- First ask: does this change act, wait, re-check, research, trim, hedge, or
  reject for a current action, open review, queued item, live thesis, catalyst,
  material holding, or high-impact watch candidate?
- Discard generic politics, election chatter, unrelated celebrity/tech-leader
  prediction markets, meme-stock social noise, promotional posts, and duplicate
  headlines unless they map directly to portfolio exposure.
- For prediction markets with unclear title/outcome fields, use only if the
  market title, URL slug, liquidity, and timing map cleanly to an active
  exposure.
- Broad SPY/QQQ flow can change tape caution; it should not create ticker queue
  rows by itself.
- Ticker flow routes only when it changes the current decision. Mixed or
  ambiguous calls and puts should usually be logged as no action.
- Cap normal runs at two Research Queue rows and three Signal Log rows unless a
  primary-source urgent item clearly needs more.

## Packet Contract

Each routed or proposed item must include:

- ticker or entity
- source and timestamp
- why it matters
- current decision affected
- conviction effect: supports, contradicts, mixed, or inconclusive
- time window
- disconfirmation trigger
- missing evidence
- proposed route: Research Queue, Signal Log, Social Watch, Event Risk, or no
  action

## Write And Verify

- Prefer Notion Research Queue and Signal Log for landed packets when connector
  write access is available.
- After every Notion write, fetch the page or row and verify the title, ticker,
  status, and key findings landed before reporting success.
- When repo cache updates are appropriate, use existing normalizers:
  - `python src/research_queue_intake.py --merge-existing`
  - `python src/signal_log_intake.py --merge-existing`
  - `python src/event_risk_intake.py --merge-existing`
  - `python src/social_watch.py` where applicable
- Validate changed caches before committing:
  - `python src/research_queue_intake.py --validate src/research_queue.json`
  - `python src/signal_log_intake.py --validate src/signal_log.json`
  - `python src/cloud_routine_receipts.py --validate --format text`

## Manual Run Calibration - 2026-06-09

High-signal examples:

- BMNR fresh SEC financing packet: preferred offering proceeds may fund ETH,
  staking/validator infrastructure, strategic Ethereum investments, working
  capital, or repurchases. This is a high-priority thesis-quality and mNAV
  check, not an automatic add.
- GOOGL fresh financing packet: AI infrastructure financing, ATM capacity, and
  Berkshire-linked placement are material to the open review. Treat as
  mixed-positive until dilution, capex ROI, and market reaction are checked.
- Iran/Hormuz prediction-market cluster: reinforces existing oil/rates event-risk
  watch, but is not a standalone trade signal.

Low-signal examples:

- Generic election, celebrity, or unrelated prediction markets.
- Mixed ANET, AVGO, or GOOGL option flow without clear decision impact.
- Social chatter without independent confirmation.

## End Of Run

Append a success or failed receipt with `--run-source scheduled` and a compact
summary of sources checked, candidates found, packets routed, Notion write
verification, cache validation, dark/stale lanes, and blockers.

Use the safe helper when routine-owned files changed:
`python src/cloud_routine_commit.py --message "Off-hours alt-data scout scheduled run" --push --format text`
