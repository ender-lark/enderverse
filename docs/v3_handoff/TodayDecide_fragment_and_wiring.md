# TodayDecide.jsx fragment + wiring notes + Task-3 UNDO addendum

**C5/C7 fragment + wiring notes.**

# 1. Wiring (the ONLY repo-eyes steps in Task 2)

- In `cockpit_html_gen.py`: `import today_decide` · build the payload with the production loaders (`weights=load_conviction_weights()`, `goal=load_goal_tunables()`, everything else defaulted so the module loads feed/insights/gates/congruence itself) · **insert `today_decide.build_and_render(weights=..., goal=...)` as the FIRST section** in whatever list/string assembly the generator uses. All existing V2 sections stay below, untouched.
- Honesty footers: additive — the section ships its own footer for the NEW lanes (cash / institutional / uw_same_session / congruence / dispositions); leave the existing V2 global footer exactly as is.
- Golden + parity: refreeze ONCE after this lands (existing freeze-script pattern), then run the docs/index.html parity path.
- Register nothing new in state ownership for this chunk except read-access; `dispositions.jsonl` ownership lands with Task 3.

# 2. Task-3 contract ADDENDUM (binding)

The rails' second tap copies `UNDO <card_id>`. Therefore `disposition_log.append_disposition` must accept verb **UNDO**: it appends a normal row (the log stays append-only — a void is a new row, never a deletion), and `load_open_cards` / `last_disposition` treat a card whose latest row is UNDO as **open / no disposition**. PASS still requires a reason; UNDO requires none.

# 3. JSX parity fragment (Task 7) — `TodayDecide` component for conviction_cockpit v6

Same payload JSON in → same fields out. Adapt class names to the v5 styling convention; the structure and field set below are the parity contract.

```jsx
import { useState } from "react";

const CLASS_COLORS = { "OPEN-NOW": "#34d399", "STAGE-ONLY": "#fbbf24", GATED: "#f87171", WAIT: "#94a3b8" };
const GATE_COLORS = { red: "#f87171", red_but_tested: "#fbbf24", green: "#34d399", context: "#94a3b8" };

const copyText = (t) => {
  if (navigator.clipboard?.writeText) navigator.clipboard.writeText(t);
};

function Rail({ cardId, verb, copy, state, setState }) {
  const on = state[cardId] === verb;
  return (
    <button
      style={{ background: on ? "#34d399" : "#1e293b", color: on ? "#0b1220" : "#e2e8f0",
               border: "1px solid #334155", borderRadius: 8, padding: "6px 12px",
               marginRight: 8, marginTop: 6, cursor: "pointer", fontSize: 13,
               fontWeight: on ? 700 : 400 }}
      onClick={() => {
        if (!on) { copyText(copy); setState({ ...state, [cardId]: verb }); }
        else { copyText(`UNDO ${cardId}`); const s = { ...state }; delete s[cardId]; setState(s); }
      }}
    >
      {on ? `${verb} \u2713 (tap to undo)` : verb}
    </button>
  );
}

function Card({ card, rank, railState, setRailState }) {
  const dc = card.decision_card || {};
  const move = dc.move || {}, conv = card.conviction || {}, win = card.window || {};
  const ex = card.execution || {}, impact = card.impact || {};
  const conflicted = (card.conflicts || []).length > 0;
  return (
    <div style={{ border: `1px solid ${conflicted ? "#fb923c" : "#1e293b"}`, borderRadius: 10,
                  padding: 12, margin: "10px 0", background: "#0f172a" }}>
      <div style={{ fontSize: 16, fontWeight: 600 }}>
        #{rank} {move.direction} {card.ticker} · {move.band}
        <span style={{ background: CLASS_COLORS[win.class] || "#94a3b8", color: "#0b1220",
                       borderRadius: 6, padding: "1px 8px", fontSize: 12, marginLeft: 8 }}>{win.class}</span>
        <span style={{ background: "#818cf8", color: "#0b1220", borderRadius: 6,
                       padding: "1px 8px", fontSize: 12, marginLeft: 8 }}>{conv.read} {conv.points}</span>
      </div>
      <div style={{ fontSize: 13, color: "#cbd5e1", margin: "4px 0" }}>
        evidence: {Object.entries(conv.groups || {}).map(([k, v]) => `${k} ${v >= 0 ? "+" : ""}${v}`).join(" · ")}
      </div>
      {win.named_trigger && <div style={{ fontSize: 13, color: "#cbd5e1" }}>trigger: {win.named_trigger}{win.deadline ? ` · deadline ${win.deadline}` : ""}</div>}
      {(win.reasons || []).slice(0, 2).map((r, i) => <div key={i} style={{ fontSize: 13, color: "#cbd5e1" }}>• {r}</div>)}
      <details style={{ fontSize: 12, color: "#94a3b8" }}>
        <summary>what changes this</summary>
        {(win.flips || []).map((f, i) => <div key={`f${i}`}>flip: {f}</div>)}
        {(conv.raises || []).map((r, i) => <div key={`r${i}`}>raise: {r}</div>)}
      </details>
      {ex.suggested && <div style={{ fontSize: 13, color: "#cbd5e1" }}>execute: {ex.suggested.owner} {ex.suggested.broker} {ex.suggested.account} · {ex.suggested.tax_flag} · {ex.suggested.why}</div>}
      {(ex.legs || []).map((l, i) => <div key={i} style={{ fontSize: 13, color: "#cbd5e1" }}>execute: sell ${"{"}l.sell_usd?.toLocaleString(){"}"} in {l.owner} {l.broker} {l.account} · {l.tax_flag}{l.proceeds_constraint ? ` · \u26a0 ${l.proceeds_constraint}` : ""}</div>)}
      {(ex.excluded || []).map((e, i) => <div key={i} style={{ fontSize: 13, color: "#cbd5e1" }}>excluded: {e.account} — {e.why_not}</div>)}
      {ex.cash && <div style={{ fontSize: 13, color: "#cbd5e1" }}>cash: {ex.cash}</div>}
      <div style={{ fontSize: 13, color: "#cbd5e1" }}>impact: {impact.band} · material: {impact.material ? "yes" : "no"}</div>
      {(card.conflicts || []).map((c, i) => (
        <div key={i} style={{ border: "1px solid #fb923c", color: "#fdba74", borderRadius: 8,
                              padding: "6px 8px", fontSize: 12, margin: "6px 0" }}>
          SOURCE-CONFLICT — {c.with}: “{c.their_claim}” vs this card: {c.card_claim} · resolve before acting
        </div>
      ))}
      <Rail cardId={card.card_id} verb="ACT" copy={`ACT ${card.card_id}`} state={railState} setState={setRailState} />
      <Rail cardId={card.card_id} verb="PASS" copy={`PASS ${card.card_id} — reason: `} state={railState} setState={setRailState} />
      <Rail cardId={card.card_id} verb="RECHECK" copy={`RECHECK ${card.card_id} resurface ${card.recheck_date}`} state={railState} setState={setRailState} />
    </div>
  );
}

export default function TodayDecide({ payload }) {
  const [railState, setRailState] = useState({});
  if (!payload) return null;
  const ga = payload.goal_anchor || {}, pl = payload.plan_line || {};
  return (
    <section style={{ fontFamily: "-apple-system,'Segoe UI',Roboto,sans-serif", background: "#0b1220",
                      color: "#e2e8f0", border: "1px solid #1e293b", borderRadius: 12, padding: 18, marginBottom: 18 }}>
      <h2 style={{ margin: 0, fontSize: 20, letterSpacing: ".04em" }}>
        TODAY — DECIDE <span style={{ color: "#94a3b8", fontSize: 12 }}>built {payload.built}</span>
      </h2>
      <div style={{ fontSize: 17, margin: "8px 0 2px" }}>
        {ga.book_value != null
          ? <>${"{"}ga.book_value.toLocaleString(){"}"} → ${"{"}ga.fi_target.toLocaleString(){"}"} · {ga.pct_to_target}% there</>
          : "book value: not readable — honest absence"}
      </div>
      <div style={{ color: "#94a3b8", fontStyle: "italic", fontSize: 12, marginBottom: 10 }}>{ga.pace_line}</div>
      <div style={{ color: "#cbd5e1", fontSize: 13, marginBottom: 10 }}>
        plan: {pl.pool_usd != null ? `funding pool $${pl.pool_usd.toLocaleString()}` : "funding pool n/a"}
        {pl.shortfall_usd != null ? ` · shortfall $${pl.shortfall_usd.toLocaleString()}` : ""} · positions as of {pl.positions_as_of}
      </div>
      {(payload.gates || []).map((g, i) => (
        <span key={i} style={{ display: "inline-block", border: `1px solid ${GATE_COLORS[g.state] || "#94a3b8"}`,
                               color: GATE_COLORS[g.state] || "#94a3b8", borderRadius: 999, padding: "2px 10px",
                               fontSize: 12, margin: "0 6px 8px 0" }}>
          {g.symbol} {g.state} · {g.confirm_rule} (as of {g.stated})
        </span>
      ))}
      {(payload.cards || []).map((c, i) => (
        <Card key={c.card_id} card={c} rank={i + 1} railState={railState} setRailState={setRailState} />
      ))}
      <details style={{ fontSize: 12, color: "#94a3b8" }}>
        <summary>Backlog ({(payload.backlog || []).length})</summary>
        {(payload.backlog || []).map((c, i) => (
          <div key={i} style={{ fontSize: 13 }}>{c.ticker} · {c.direction} · ${"{"}(c.dollars || 0).toLocaleString(){"}"} · p{c.priority}</div>
        ))}
      </details>
      {payload.congruence?.status === "ok"
        ? (payload.congruence.rows || []).map((r, i) => (
            <div key={i} style={{ fontSize: 13, margin: "3px 0" }}>{r.flagged ? "\ud83d\udea9 " : ""}{r.insight_id} · {r.line}</div>))
        : <div style={{ fontSize: 13 }}>congruence: not checked — {payload.congruence?.reason}</div>}
      <div style={{ fontFamily: "ui-monospace,Menlo,monospace", fontSize: 11, color: "#94a3b8",
                    borderTop: "1px solid #1e293b", marginTop: 12, paddingTop: 8 }}>
        {Object.entries(payload.honesty || {}).map(([k, v]) => <div key={k}>{k}: {String(v)}</div>)}
      </div>
    </section>
  );
}
```

**Parity test (Task 7):** feed the same payload JSON to both renderers; assert identical sets of {ticker, window.class, [conviction.read](http://conviction.read), priority, card_id} and identical rail copy strings.