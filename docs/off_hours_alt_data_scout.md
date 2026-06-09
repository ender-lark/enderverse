# Off-Hours Alt-Data Scout

Last updated: 2026-06-09.

## Purpose

Use off-hours Codex time to find external evidence that can raise conviction,
lower conviction, or close research loops before trading hours. The scout should
feed open Research Queue items, potential-interest items, Signal Log context,
and Social Watch context. It does not place trades, size positions, or turn weak
signals into buy/sell instructions.

## High-Value Inputs

1. Unusual Whales prediction markets.
   - Use unusual markets, prediction insiders, whales, smart-money, market
     details, liquidity, positions, and user/wallet profile routes when
     available.
   - Prioritize Politics, Finance, and Crypto markets that map to portfolio
     exposures, policy catalysts, regulation, crypto liquidity, rates, defense,
     energy, or AI/semis.
   - Treat "insider" labels as a lead, not proof. Require independent
     confirmation before any action lane.

2. Unusual Whales equity and options evidence.
   - Use scenario-routed endpoint groups from the existing UW runbook:
     broad tape, sector/ETF tide, ticker flow, dark pool, OI change, analyst
     ratings, news headlines, insider flow, institutional ownership, and
     congressional trades where accessible.
   - Best use: confirm or disconfirm current action rows, Fundstrat calls,
     reallocation candidates, and research queue theses.

3. SEC and filing/event sources.
   - Use SEC EDGAR company submissions, RSS/company filing feeds, 8-Ks,
     S-3/ATM updates, insider Form 4s, 13F windows, and material risk-factor
     changes.
   - Best use: disconfirmation, dilution risk, balance-sheet risk, sponsor
     validation, and catalyst timing.

4. Prediction-market public APIs.
   - Use Polymarket public Gamma/Data/CLOB read endpoints for market discovery,
     open interest, prices, trades, holder/user activity, and comments when
     relevant.
   - Use Kalshi public market/orderbook/event endpoints for regulated event
     markets and macro/policy odds.
   - These are research context only. Do not trade prediction markets from this
     routine.

5. Substack/RSS and expert feeds.
   - Use explicit RSS feeds or public posts from a curated allowlist only:
     macro, policy, semis/AI infrastructure, energy/uranium, crypto market
     structure, defense, and high-signal investor/operator writing.
   - Summarize claims and source links, not full articles or paywalled content.
   - Route only specific claims, catalysts, channel checks, or disconfirming
     evidence.

6. Social feeds.
   - Reddit remains disabled unless official OAuth access works, a supplied
     cache is provided, or a third-party proxy is verified reliable and compliant
     enough for watch-only discovery.
   - Stocktwits or other social APIs can be used only as watch-only mention and
     sentiment context. Independent non-social confirmation is required before
     any action escalation.

## Ranking Rules

Score each candidate by:

- Impact on early-retirement outcome: position size, capital allocation, factor
  concentration, downside risk, or asymmetric upside.
- Time sensitivity: same-day, next session, this week, catalyst window, or no
  urgency.
- Evidence quality: primary source or market data beats social echo.
- Disconfirmation value: evidence that could prevent a bad buy, stale hold, or
  missed trim is high priority.
- Open-loop fit: existing action row, open review, Research Queue item, live
  thesis, catalyst, reallocation candidate, or material holding.
- Novelty: avoid repeating already-ingested Fundstrat/news/social points unless
  new evidence changes the decision.

## Landing Rules

- Research Queue: use when the item needs a dossier, thesis work, channel
  check, or structured follow-up.
- Signal Log: use when the item is watch-only context, a market structure clue,
  or a non-action signal that may matter later.
- Social Watch: use only for social/Reddit/Stocktwits-style anomaly rows.
- Event Risk: use for macro, policy, legal, geopolitical, rate, oil, crypto,
  or regulatory events that change exposure timing.
- Do not mark missing sources checked clear. If a feed is unavailable, report it
  as dark or not checked.
- Do not store raw copyrighted or paywalled bodies. Store compact evidence,
  source labels, links, timestamps, and the decision implication.

## Output Packet

Each landed or proposed item should include:

- ticker/entity
- source and timestamp
- why it matters
- current decision affected
- conviction effect: supports, contradicts, mixed, or inconclusive
- time window
- disconfirmation trigger
- missing evidence
- proposed route: Research Queue, Signal Log, Social Watch, Event Risk, or no
  action

## Automation Role

Run as a separate off-hours scout before the existing off-hours worker drains
Research Queue items. The scout discovers and routes useful evidence; the worker
turns the best queued items into dossiers.
