import { useState } from "react";

const CLASS_COLORS = { "OPEN-NOW": "#34d399", "STAGE-ONLY": "#fbbf24", GATED: "#f87171", WAIT: "#94a3b8" };
const GATE_COLORS = { red: "#f87171", red_but_tested: "#fbbf24", green: "#34d399", context: "#94a3b8" };

const copyText = (t) => {
  if (navigator.clipboard?.writeText) navigator.clipboard.writeText(t);
};

function reviewPosture(card, checkFirst, windowClass, direction) {
  if (checkFirst || (card.conflicts || []).length || ["GATED", "WAIT"].includes(windowClass)) {
    return {
      label: "RECHECK",
      stateVerb: "RECHECK",
      copyVerb: "RECHECK",
      copySuffix: " resolve blockers before action",
      reason: `candidate ${direction}; blockers or conflicts must clear first`,
    };
  }
  if (windowClass === "STAGE-ONLY") {
    return {
      label: "CANDIDATE",
      stateVerb: "CANDIDATE",
      copyVerb: "RECHECK",
      copySuffix: " candidate only; confirm gates before action",
      reason: `candidate ${direction}; stage-only until gates confirm`,
    };
  }
  return { label: direction, stateVerb: "ACT", copyVerb: "ACT", copySuffix: "", reason: "" };
}

function Rail({ cardId, verb, copy, muted, state, setState }) {
  const on = state[cardId] === verb;
  return (
    <button
      style={{ background: on ? "#34d399" : (muted ? "#111827" : "#1e293b"),
               color: on ? "#0b1220" : (muted ? "#cbd5e1" : "#e2e8f0"),
               border: `1px solid ${muted ? "#64748b" : "#334155"}`, borderRadius: 8, padding: "6px 12px",
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

function Card({ card, rank, checkFirst, railState, setRailState }) {
  const dc = card.decision_card || {};
  const move = dc.move || {}, conv = card.conviction || {}, win = card.window || {};
  const ex = card.execution || {}, impact = card.impact || {};
  const sizing = card.sizing || {};
  const cardBlockers = card.card_blockers || [];
  const scopedCheckFirst = checkFirst || Boolean(cardBlockers.length);
  const conflicted = (card.conflicts || []).length > 0;
  const posture = reviewPosture(card, scopedCheckFirst, win.class, move.direction);
  const primaryCopy = posture.copyVerb === "ACT"
    ? `ACT ${card.card_id}`
    : `${posture.copyVerb} ${card.card_id}${posture.copySuffix}`;
  return (
    <div style={{ border: `1px solid ${conflicted ? "#fb923c" : "#1e293b"}`, borderRadius: 10,
                  padding: 12, margin: "10px 0", background: "#0f172a" }}>
      {scopedCheckFirst && <div style={{ color: "#f87171", fontWeight: 700, fontSize: 12, marginBottom: 6 }}>CHECK DATA FIRST - inputs behind/stale</div>}
      <div style={{ fontSize: 16, fontWeight: 600 }}>
        #{rank} {posture.label} {card.ticker} Â· {move.band}
        <span style={{ background: CLASS_COLORS[win.class] || "#94a3b8", color: "#0b1220",
                       borderRadius: 6, padding: "1px 8px", fontSize: 12, marginLeft: 8 }}>{win.class}</span>
        <span style={{ background: "#818cf8", color: "#0b1220", borderRadius: 6,
                       padding: "1px 8px", fontSize: 12, marginLeft: 8 }}>{conv.read} {conv.points}</span>
      </div>
      {posture.reason && <div style={{ fontSize: 13, color: "#cbd5e1", margin: "4px 0" }}><strong>posture:</strong> {posture.reason}</div>}
      <div style={{ fontSize: 13, color: "#cbd5e1", margin: "4px 0" }}>
        evidence: {Object.entries(conv.groups || {}).map(([k, v]) => `${k} ${v >= 0 ? "+" : ""}${v}`).join(" Â· ")}
      </div>
      {win.named_trigger && <div style={{ fontSize: 13, color: "#cbd5e1" }}>trigger: {win.named_trigger}{win.deadline ? ` Â· deadline ${win.deadline}` : ""}</div>}
      {(win.reasons || []).slice(0, 2).map((r, i) => <div key={i} style={{ fontSize: 13, color: "#cbd5e1" }}>â€¢ {r}</div>)}
      <details style={{ fontSize: 12, color: "#94a3b8" }}>
        <summary>what changes this</summary>
        {(win.flips || []).map((f, i) => <div key={`f${i}`}>flip: {f}</div>)}
        {(conv.raises || []).map((r, i) => <div key={`r${i}`}>raise: {r}</div>)}
      </details>
      {ex.suggested && <div style={{ fontSize: 13, color: "#cbd5e1" }}>execute: {ex.suggested.owner} {ex.suggested.broker} {ex.suggested.account} Â· {ex.suggested.tax_flag} Â· {ex.suggested.why}</div>}
      {(ex.legs || []).map((l, i) => <div key={i} style={{ fontSize: 13, color: "#cbd5e1" }}>execute: sell ${"{"}l.sell_usd?.toLocaleString(){"}"} in {l.owner} {l.broker} {l.account} Â· {l.tax_flag}{l.proceeds_constraint ? ` Â· \u26a0 ${l.proceeds_constraint}` : ""}</div>)}
      {(ex.excluded || []).map((e, i) => <div key={i} style={{ fontSize: 13, color: "#cbd5e1" }}>excluded: {e.account} â€” {e.why_not}</div>)}
      {ex.cash && <div style={{ fontSize: 13, color: "#cbd5e1" }}>cash: {ex.cash}</div>}
      {sizing.source && <div style={{ fontSize: 13, color: "#cbd5e1" }}>sizing: {sizing.source} suggested ${"{"}(sizing.suggested_usd || 0).toLocaleString(){"}"} Â· heat {sizing.heat || "unknown"}</div>}
      {sizing.cap_basis && <div style={{ fontSize: 13, color: "#cbd5e1" }}>cap basis: {sizing.cap_basis}</div>}
      <div style={{ fontSize: 13, color: "#cbd5e1" }}>impact: {impact.band} Â· material: {impact.material ? "yes" : "no"}</div>
      {(card.conflicts || []).map((c, i) => (
        <div key={i} style={{ border: "1px solid #fb923c", color: "#fdba74", borderRadius: 8,
                              padding: "6px 8px", fontSize: 12, margin: "6px 0" }}>
          SOURCE-CONFLICT â€” {c.with}: â€œ{c.their_claim}â€ vs this card: {c.card_claim} Â· resolve before acting
        </div>
      ))}
      <Rail cardId={card.card_id} verb={posture.stateVerb} copy={primaryCopy} muted={posture.copyVerb !== "ACT"} state={railState} setState={setRailState} />
      <Rail cardId={card.card_id} verb="PASS" copy={`PASS ${card.card_id} â€” reason: `} state={railState} setState={setRailState} />
      {posture.label !== "RECHECK" && <Rail cardId={card.card_id} verb="RECHECK" copy={`RECHECK ${card.card_id} resurface ${card.recheck_date}`} state={railState} setState={setRailState} />}
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
        TODAY â€” DECIDE <span style={{ color: "#94a3b8", fontSize: 12 }}>built {payload.built}</span>
      </h2>
      <div style={{ fontSize: 17, margin: "8px 0 2px" }}>
        {ga.book_value != null
          ? <>${"{"}ga.book_value.toLocaleString(){"}"} â†’ ${"{"}ga.fi_target.toLocaleString(){"}"} Â· {ga.pct_to_target}% there</>
          : "book value: not readable â€” honest absence"}
      </div>
      <div style={{ color: "#94a3b8", fontStyle: "italic", fontSize: 12, marginBottom: 10 }}>{ga.pace_line}</div>
      <div style={{ color: "#cbd5e1", fontSize: 13, marginBottom: 10 }}>
        plan: {pl.pool_usd != null ? `funding pool $${pl.pool_usd.toLocaleString()}` : "funding pool n/a"}
        {pl.shortfall_usd != null ? ` Â· shortfall $${pl.shortfall_usd.toLocaleString()}` : ""} Â· positions as of {pl.positions_as_of}
      </div>
      {(payload.gates || []).map((g, i) => (
        <span key={i} style={{ display: "inline-block", border: `1px solid ${GATE_COLORS[g.state] || "#94a3b8"}`,
                               color: GATE_COLORS[g.state] || "#94a3b8", borderRadius: 999, padding: "2px 10px",
                               fontSize: 12, margin: "0 6px 8px 0" }}>
          {g.symbol} {g.state} Â· {g.confirm_rule} (as of {g.stated})
        </span>
      ))}
      {(payload.cards || []).map((c, i) => (
        <Card key={c.card_id} card={c} rank={i + 1} checkFirst={Boolean((c.card_blockers || []).length)} railState={railState} setRailState={setRailState} />
      ))}
      <details style={{ fontSize: 12, color: "#94a3b8" }}>
        <summary>Backlog ({(payload.backlog || []).length})</summary>
        {(payload.backlog || []).map((c, i) => (
          <div key={i} style={{ fontSize: 13 }}>{c.ticker} Â· {c.direction} Â· ${"{"}(c.dollars || 0).toLocaleString(){"}"} Â· p{c.priority}</div>
        ))}
      </details>
      {payload.congruence?.status === "ok"
        ? (payload.congruence.rows || []).map((r, i) => (
            <div key={i} style={{ fontSize: 13, margin: "3px 0" }}>{r.flagged ? "\ud83d\udea9 " : ""}{r.insight_id} Â· {r.line}</div>))
        : <div style={{ fontSize: 13 }}>congruence: not checked â€” {payload.congruence?.reason}</div>}
      <div style={{ fontFamily: "ui-monospace,Menlo,monospace", fontSize: 11, color: "#94a3b8",
                    borderTop: "1px solid #1e293b", marginTop: 12, paddingTop: 8 }}>
        {Object.entries(payload.honesty || {}).map(([k, v]) => <div key={k}>{k}: {String(v)}</div>)}
      </div>
    </section>
  );
}
