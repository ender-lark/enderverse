import React from "react";
import TodayDecide from "./TodayDecide";

// ───────────────────────────────────────────────────────────────
// CONVICTION COCKPIT — v6 (artifact-cockpit port of TODAY — DECIDE)
//
// The v6 artifact cockpit consumes the SAME payload the Python HTML renderer
// (`today_decide.render_today_decide_html`) consumes. The parity contract is:
//
//   payload.{built, goal_anchor, plan_line, gates[], cards[], backlog[],
//            congruence, honesty}
//   card.{card_id, ticker, direction, recheck_date, conflicts[],
//         conviction.{read, points, groups, raises},
//         window.{class, deadline, reasons, flips, named_trigger},
//         decision_card.{move, conviction, window, evidence, impact},
//         execution.{suggested, legs[], excluded[], cash}, sizing, impact}
//
// Rail copy strings (what the second-tap → UNDO and first-tap → verb actions
// place on the clipboard) are the operator-facing parity surface:
//
//   ACT     → "ACT <card_id>"
//   PASS    → "PASS <card_id> — reason: "
//   RECHECK → "RECHECK <card_id> resurface <recheck_date>"
//   UNDO    → "UNDO <card_id>"
//
// Same feed JSON in → same fields out. See `src/test_jsx_parity.py` for the
// enforced contract.
// ───────────────────────────────────────────────────────────────

export default function ConvictionCockpitV6({ payload }) {
  if (!payload) {
    return (
      <section style={{
        fontFamily: "-apple-system,'Segoe UI',Roboto,sans-serif",
        background: "#0b1220", color: "#94a3b8",
        border: "1px solid #1e293b", borderRadius: 12,
        padding: 18, marginBottom: 18,
      }}>
        v6 cockpit: payload missing — honest absence (no silent default)
      </section>
    );
  }
  return (
    <main style={{ background: "#0b1220", color: "#e2e8f0", padding: 16,
                   fontFamily: "-apple-system,'Segoe UI',Roboto,sans-serif" }}>
      {/* The TODAY — DECIDE surface is rendered FIRST, identical contract to
          the Python HTML renderer. Existing V2 cockpit panels can be mounted
          below this section without disturbing the parity contract. */}
      <TodayDecide payload={payload} />
    </main>
  );
}
