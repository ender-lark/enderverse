# Scheduled Routine Proof Audit - 2026-06-15

## Verdict

The scheduled-routine proof surface was overcounting. It treated every active
helper automation as a core unattended-readiness requirement, even though the
current Investing OS operating loop only needs a smaller set of routines to
prove the daily operator path.

The proof model is now split:

- Core proof: routines that must eventually prove scheduled execution for the
  unattended daily operator loop.
- Support monitored: useful helper, research, or duplicate-source routines that
  should remain visible, but should not by themselves make the whole system
  look unready.

No scheduled proof was backfilled from manual runs. Manual support still stays
separate from true scheduled proof.

## Core Proof Routines

These routines directly protect portfolio truth, Fundstrat/timing intake,
market-open decision quality, UW opportunity capture, dashboard publication,
and post-close account refresh.

| Routine | Why it remains core |
|---|---|
| Pre-Market Source Intake | Early source refresh before the operator cockpit; repaired today because its automation workspace path was malformed. |
| Fundstrat Pre-Market Safety Sweep | Captures overnight and early timing calls before the main morning stack. |
| Broker Position Intake | SnapTrade-first account truth before allocation and risk review. |
| Morning Scan | Watch-only signal/macro context before cockpit publication. |
| Early Cockpit Build | Earliest useful operator surface; later lanes remain visibly pending. |
| Daily Synthesis | Daily decision synthesis from current repo/feed evidence. |
| Post-Open Evidence Gate | Same-session evidence gate for action validity. |
| Fundstrat Daytime Watch | Market-hours action-changing Fundstrat watch and trigger guard. |
| UW Opportunity Cache | Opportunity-flow and live connector proof for time-sensitive setups. |
| Parabolic Cache | Chase-risk/parabolic setup cache for action gating. |
| Full Cockpit Build | Complete mid-morning dashboard publication. |
| Post-Close Refresh | End-of-day dashboard/proof refresh. |
| Positions Sync | Post-close SnapTrade-first position refresh. |
| Fundstrat After-Hours Catch-Up | Late Fundstrat notes and next-session prep. |

## Support-Monitored Routines

These remain useful, but are not core unattended-readiness gates:

| Routine family | Current classification |
|---|---|
| FS Inbox Catch-up Preopen/Midday/Postclose/Evening | Support. These overlap with the Fundstrat pre-market, daytime, and after-hours lanes; keep visible, but do not block core readiness. |
| Off-Hours Research Queue | Support safe-intake from supplied queue exports. It should not imply no research when no export is present. |
| Top Prospects Auto-Research | Support bridge from uncorroborated prospects into the Research Queue. Useful for AI-opportunity capture, but not a daily readiness gate. |
| Off-Hours Alt-Data Scout | Support discovery lane; missing pulls remain dark/not_checked. |
| Off-Hours Worker | Support research/backlog drain. Important, but not required for the daily operator cockpit to be ready. |
| Off-Hours Queue Buffer | Support buffer after the off-hours worker. |
| Deep Synthesis | Strategic weekly support, not daily unattended proof. |
| Weekly Pilot Run | Strategic weekly pilot/calibration support, not daily unattended proof. |

## Current Proof Readout After Fix

As of the 2026-06-15 audit run:

- Total monitored active routines: 25.
- Core proof routines: 14.
- Support monitored routines: 11.
- Core scheduled successes: 13/14.
- Core overdue scheduled receipts: 5.
- Support scheduled successes: 2/11.
- Support overdue receipts: 9.
- Social Watch remains dark and deferred until a compliant normalized cache is
  available.

The system is still not fully unattended because five core scheduled receipts
are overdue: Pre-Market Source Intake, Fundstrat Pre-Market Safety Sweep,
Morning Scan, Early Cockpit Build, and UW Opportunity Cache. Manual support
proved those local paths can run, but it does not prove the scheduler fired.

## Repair Landed

- Corrected the app automation workspace for `investing-os-pre-market-source-intake`.
- Removed stale temporary June 11/12 wording from the pre-market source-intake
  automation prompt.
- Added a core/support proof-scope helper in `cloud_routine_receipts.py`.
- Updated `cloud_ops_status.py` so readiness uses core proof only while keeping
  support routines visible.
- Updated `full_build_runner.py` so dashboard source audits use the same
  core/support proof denominator.

## Remaining Follow-Up

Let the next natural scheduled windows prove the five overdue core routines.
If they miss again after the pre-market path repair, inspect the individual app
automation run logs rather than backfilling proof manually.
