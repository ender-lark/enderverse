# Investing OS Validation Audit - 2026-06-15

## Verdict

The Investing OS is locally build-ready and useful for decision support today, but it is not fully unattended. The code and feed pipeline pass the standard suite, live readiness is green, and the dashboard now shows the fresh 10:32 ET HTML preview. The main calibration gaps are operational: the canonical dashboard server had been serving an older worktree, cloud ops still reports unattended state as not ready, Social Watch remains dark, and the V3 TODAY-DECIDE strip can visually overstate candidate buy/sell cards while lower dashboard sections correctly downgrade them to re-check or backlog.

## Evidence Checked

- Standard verification: `python src/verify_standard.py`
  - Result: 1520 passed, 6 skipped.
  - Standalone checks passed: reallocation rebuild, cockpit injector self-test, broker PDF extractor self-test.
- Live readiness: `python src/live_readiness.py`
  - Result: go-live, rehearsal, build, publish, required inputs, and live data all ready.
  - Dark lane: Social Watch only; correctly marked not checked.
- Cloud ops: `python src/cloud_ops_status.py`
  - Result: local go-live ready, but unattended cloud operating state not ready.
  - Reason: multiple scheduled lanes are still reported overdue or manually supported even though many latest receipts are successful.
- Dashboard browser check:
  - Found stale runtime first: `http://127.0.0.1:8765/dashboard_preview.html` was serving the older `enderverse` worktree built at 08:57 ET with stale Fundstrat daily.
  - Runtime fix applied: stopped the stale dashboard preview process and restarted `src/dashboard_preview_server.py` from `enderverse-held-decisions-strip` on port 8765.
  - Recheck result: default dashboard URL now shows build `06-15 10:32 ET`, data `06-15`, Fundstrat Bible `06-11`, Fundstrat daily `06-14`.

## Calibration Read

- Goal anchor is present and visible: roughly $1.887M book toward $3.0M target, about 62.9% there, with the pace line explicitly display-only.
- The main action feed is aligned with decision usefulness:
  - Re-check Before Acting: event-risk shock around Middle East oil/rates before new buys.
  - Important Backlog: MAGS lean-in/add review, gated by pre-trade checks.
  - Research Now: GOOGL AI infrastructure financing / ATM / Berkshire placement implications.
  - Quiet Watch: RYF and XOP avoid-new-exposure warnings, no position in checked book.
- Source honesty is mostly working:
  - Social Watch is not checked and does not become a no-signal read.
  - Event/rate/oil shock is treated as re-check, not automatic action.
  - Candidate reallocations are labeled candidate-only and gated.
- AI opportunity posture is present:
  - Reallocation brief prioritizes missing/underrepresented AI working-model targets including GOOGL, MSFT, AMZN, AVGO.
  - GOOGL research explicitly routes through thesis confirmation and pre-trade gate.
  - MAGS/AI ETF look-through overlap is surfaced.

## Gaps That Matter

1. Runtime drift can make the default operator URL stale even when the current repo artifact is fresh.
   - Fix applied today for the local session.
   - Follow-up: add a server-origin check that reports which worktree owns port 8765 and whether the served stamp matches `tmp/dashboard_preview.html`.

2. Cloud ops is still not fully unattended.
   - Several latest receipts are successful, but some are manual support receipts and cloud ops still reports `cloud_operating_state: not_ready`.
   - Follow-up: separate "manual support proof" from true scheduled proof in the dashboard so the operator can trust unattended status at a glance.

3. V3 TODAY-DECIDE needs stronger visual guardrails.
   - It shows `SELL MAGS` as a tiny funding leg and `BUY GOOGL` as a staged candidate while also showing CHECK DATA FIRST and source-conflict warnings.
   - This is honest, but too easy to misread as direct action in a first-screen decision surface.
   - Follow-up: when a card is conflicted, stage-only, or check-first, replace the primary verb with `RECHECK` or `CANDIDATE`, and disable/de-emphasize ACT copy until blockers clear.

4. Notion mirror drift exists.
   - The repo and current operating memory say the local HTML dashboard is the default operator surface.
   - The Notion mirror fetched during this audit still says JSX is the default.
   - Follow-up: mirror the current repo doctrine to Notion and mark the old JSX-default language superseded.

5. Social Watch remains dark.
   - This is acceptable for honesty, but it means early social/anomaly signals are not part of the current AI-opportunity capture loop.
   - Follow-up: keep it dark until the compliant social cache is available; do not treat missing social data as quiet.

## Recommended Next Slice

Implement a focused runtime/dashboard-hardening slice:

1. Add `dashboard_preview_server.py --check-origin` or equivalent to verify the serving worktree and preview stamp.
2. Add a dashboard warning when port 8765 serves a stale or wrong-worktree preview.
3. Tighten TODAY-DECIDE conflicted/stage-only cards so the first visible verb is `RECHECK` or `CANDIDATE`, not `BUY`/`SELL`, until blockers clear.
4. Update the Notion mirror to HTML-dashboard default after the repo doc stays canonical.
