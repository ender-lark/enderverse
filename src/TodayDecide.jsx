import { useState } from "react";

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

function SectionTitle({ children }) {
  return <div style={{ fontSize: 11, color: "#94a3b8", fontWeight: 800, letterSpacing: ".04em",
                       textTransform: "uppercase", margin: "8px 0 4px" }}>{children}</div>;
}

function WhyBreakdown({ display }) {
  const why = display.why || {};
  const groups = why.groups || [];
  const factors = why.decisive_factors || [];
  return (
    <>
      {factors.length
        ? factors.map((f) => (
            <div key={f.key} style={{ fontSize: 13, color: f.conflict ? "#fdba74" : "#cbd5e1", margin: "3px 0" }}>
              <strong style={{ color: f.conflict ? "#fdba74" : "#e2e8f0" }}>{f.conflict ? "conflicting" : (f.decisive ? "decisive" : "factor")}:</strong> {f.label || f.key} - {f.value_str}
            </div>
          ))
        : <div style={{ fontSize: 13, color: "#cbd5e1" }}>Battery decisive factors: none surfaced.</div>}
      {groups.length
        ? groups.map((g) => (
            <div key={g.key} style={{ fontSize: 13, color: "#cbd5e1", margin: "3px 0" }}>
              <strong style={{ color: "#e2e8f0" }}>{g.label || g.key}</strong> {Number(g.points || 0) >= 0 ? "+" : ""}{Number(g.points || 0).toFixed(2)}
            </div>
          ))
        : <div style={{ fontSize: 13, color: "#cbd5e1" }}>No scored group has moved the conviction yet.</div>}
    </>
  );
}

function IvHint({ display }) {
  const hint = display.iv_hint || {};
  const text = hint.hint || hint.value || hint.status || "not_checked";
  const status = hint.status ? ` (${hint.status})` : "";
  return <div style={{ fontSize: 13, color: "#cbd5e1", margin: "4px 0" }}>IV options-vs-shares{status}: {text}</div>;
}

function DossierBlock({ dossier, ticker }) {
  if (!dossier || !dossier.reads) return null;
  const labels = ["edge", "price", "timing", "avoid"];
  return (
    <div style={{ border: "1px solid #334155", borderRadius: 8, padding: 8, margin: "8px 0", background: "#0b1220" }}>
      <div style={{ fontSize: 12, color: "#e2e8f0", fontWeight: 800, marginBottom: 4 }}>Decision dossier: {dossier.ticker || ticker}</div>
      <div style={{ fontSize: 11, color: "#94a3b8", margin: "2px 0 6px" }}>
        status: {dossier.status || "not_checked"} | reviewed: {dossier.last_reviewed || "not_checked"} | due: {dossier.next_review_due || "not_checked"} | synced: {dossier.synced_at || "not_checked"}
      </div>
      {dossier.one_liner && <div style={{ fontSize: 13, color: "#cbd5e1", margin: "4px 0" }}>{dossier.one_liner}</div>}
      {dossier.notion_url && <div style={{ fontSize: 13, color: "#cbd5e1", margin: "4px 0" }}><a style={{ color: "#93c5fd" }} href={dossier.notion_url}>open full dossier</a></div>}
      {labels.map((key) => {
        const read = dossier.reads[key] || {};
        const freshness = read.freshness || {};
        return (
          <div key={key} style={{ fontSize: 12, color: "#cbd5e1", margin: "3px 0" }}>
            <strong style={{ color: "#e2e8f0" }}>{read.label || key} ({freshness.status || "not_checked"}):</strong> {read.text || "UNKNOWN"}
          </div>
        );
      })}
    </div>
  );
}

function Card({ card, rank, checkFirst, railState, setRailState }) {
  const dc = card.decision_card || {};
  const move = dc.move || {}, win = card.window || {};
  const ticker = card.ticker;
  const display = card.conviction_display || { text: "Conviction: not checked", band_color: "#94a3b8", why: {}, raises: [], not_checked: [] };
  const dossier = card.dossier || null;
  const ex = card.execution || {}, impact = card.impact || {};
  const sizing = card.sizing || {};
  const cardBlockers = card.card_blockers || [];
  const scopedCheckFirst = checkFirst || Boolean(cardBlockers.length);
  const conflicted = Boolean(display.conflict) || (card.conflicts || []).length > 0;
  const posture = reviewPosture(card, scopedCheckFirst, win.class, move.direction);
  const primaryCopy = posture.copyVerb === "ACT"
    ? `ACT ${card.card_id}`
    : `${posture.copyVerb} ${card.card_id}${posture.copySuffix}`;
  return (
    <details data-ticker={ticker} style={{ border: `1px solid ${conflicted ? "#fb923c" : "#1e293b"}`, borderRadius: 10,
                      padding: 0, margin: "10px 0", background: "#0f172a" }}>
      <summary style={{ listStyle: "none", cursor: "pointer", padding: 12 }}>
        {scopedCheckFirst && <div style={{ color: "#f87171", fontWeight: 700, fontSize: 12, marginBottom: 6 }}>CHECK DATA FIRST - inputs behind/stale</div>}
        <div style={{ fontSize: 18, fontWeight: 750, lineHeight: 1.25 }}>
          <span style={{ display: "block", background: display.band_color || "#94a3b8", color: "#0b1220",
                         borderRadius: 8, padding: "8px 10px" }}>#{rank} {display.text}</span>
        </div>
        {display.conflict && <div style={{ border: "1px solid #fb923c", color: "#fdba74", borderRadius: 8,
                                           padding: "6px 8px", fontSize: 12, margin: "6px 0" }}>CONFLICT - {display.conflict}</div>}
      </summary>
      <div style={{ padding: "2px 12px 12px", borderTop: "1px solid #1e293b", marginTop: 10, paddingTop: 8 }}>
        <SectionTitle>Why it is this</SectionTitle>
        <WhyBreakdown display={display} />
        {(card.conflicts || []).map((c, i) => (
          <div key={i} style={{ border: "1px solid #fb923c", color: "#fdba74", borderRadius: 8,
                                padding: "6px 8px", fontSize: 12, margin: "6px 0" }}>
            SOURCE-CONFLICT - {c.with}: {c.their_claim} vs this card: {c.card_claim} - resolve before acting
          </div>
        ))}
        <SectionTitle>What would make it a confident move</SectionTitle>
        {(display.raises || []).length
          ? (display.raises || []).map((r, i) => <div key={`r${i}`} style={{ fontSize: 13, color: "#cbd5e1", margin: "4px 0" }}>raise: {r}</div>)
          : <div style={{ fontSize: 13, color: "#cbd5e1" }}>No raise condition surfaced.</div>}
        <SectionTitle>IV options-vs-shares</SectionTitle>
        <IvHint display={display} />
        <DossierBlock dossier={dossier} ticker={ticker} />
        {posture.reason && <div style={{ fontSize: 13, color: "#cbd5e1", margin: "4px 0" }}><strong>posture:</strong> {posture.reason}</div>}
        <Rail cardId={card.card_id} verb={posture.stateVerb} copy={primaryCopy} muted={posture.copyVerb !== "ACT"} state={railState} setState={setRailState} />
        <Rail cardId={card.card_id} verb="PASS" copy={`PASS ${card.card_id} â€” reason: `} state={railState} setState={setRailState} />
        {posture.label !== "RECHECK" && <Rail cardId={card.card_id} verb="RECHECK" copy={`RECHECK ${card.card_id} resurface ${card.recheck_date}`} state={railState} setState={setRailState} />}
        {win.named_trigger && <div style={{ fontSize: 13, color: "#cbd5e1" }}>trigger: {win.named_trigger}{win.deadline ? ` - deadline ${win.deadline}` : ""}</div>}
        {(win.reasons || []).slice(0, 2).map((r, i) => <div key={i} style={{ fontSize: 13, color: "#cbd5e1" }}>- {r}</div>)}
        {(win.flips || []).length > 0 && (
          <details style={{ fontSize: 12, color: "#94a3b8" }}>
            <summary>what changes this</summary>
            {(win.flips || []).map((f, i) => <div key={`f${i}`}>flip: {f}</div>)}
          </details>
        )}
        {ex.suggested && <div style={{ fontSize: 13, color: "#cbd5e1" }}>execute: {ex.suggested.owner} {ex.suggested.broker} {ex.suggested.account} - {ex.suggested.tax_flag} - {ex.suggested.why}</div>}
        {(ex.legs || []).map((l, i) => <div key={i} style={{ fontSize: 13, color: "#cbd5e1" }}>execute: sell ${l.sell_usd?.toLocaleString()} in {l.owner} {l.broker} {l.account} - {l.tax_flag}{l.proceeds_constraint ? ` - ${l.proceeds_constraint}` : ""}</div>)}
        {(ex.excluded || []).map((e, i) => <div key={i} style={{ fontSize: 13, color: "#cbd5e1" }}>excluded: {e.account} - {e.why_not}</div>)}
        {ex.cash && <div style={{ fontSize: 13, color: "#cbd5e1" }}>cash: {ex.cash}</div>}
        {sizing.source && <div style={{ fontSize: 13, color: "#cbd5e1" }}>sizing: {sizing.source} suggested ${(sizing.suggested_usd || 0).toLocaleString()} - heat {sizing.heat || "unknown"}</div>}
        {sizing.cap_basis && <div style={{ fontSize: 13, color: "#cbd5e1" }}>cap basis: {sizing.cap_basis}</div>}
        <div style={{ fontSize: 13, color: "#cbd5e1" }}>impact: {impact.band} - material: {impact.material ? "yes" : "no"}</div>
        <div style={{ fontSize: 13, color: "#cbd5e1", margin: "4px 0" }}>not checked: {(display.not_checked || []).length ? (display.not_checked || []).join(", ") : "none"}</div>
      </div>
    </details>
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
        TODAY - DECIDE <span style={{ color: "#94a3b8", fontSize: 12 }}>built {payload.built}</span>
      </h2>
      <div style={{ fontSize: 17, margin: "8px 0 2px" }}>
        {ga.book_value != null
          ? <>${ga.book_value.toLocaleString()} to ${ga.fi_target.toLocaleString()} - {ga.pct_to_target}% there</>
          : "book value: not readable - honest absence"}
      </div>
      <div style={{ color: "#94a3b8", fontStyle: "italic", fontSize: 12, marginBottom: 10 }}>{ga.pace_line}</div>
      <div style={{ color: "#cbd5e1", fontSize: 13, marginBottom: 10 }}>
        plan: {pl.pool_usd != null ? `funding pool $${pl.pool_usd.toLocaleString()}` : "funding pool n/a"}
        {pl.shortfall_usd != null ? ` - shortfall $${pl.shortfall_usd.toLocaleString()}` : ""} - positions as of {pl.positions_as_of}
      </div>
      {(payload.gates || []).map((g, i) => (
        <span key={i} style={{ display: "inline-block", border: `1px solid ${GATE_COLORS[g.state] || "#94a3b8"}`,
                               color: GATE_COLORS[g.state] || "#94a3b8", borderRadius: 999, padding: "2px 10px",
                               fontSize: 12, margin: "0 6px 8px 0" }}>
          {g.symbol} {g.state} - {g.confirm_rule} (as of {g.stated})
        </span>
      ))}
      {(payload.cards || []).map((c, i) => (
        <Card key={c.card_id} card={c} rank={i + 1} checkFirst={Boolean((c.card_blockers || []).length)} railState={railState} setRailState={setRailState} />
      ))}
      <details style={{ fontSize: 12, color: "#94a3b8" }}>
        <summary>Backlog ({(payload.backlog || []).length})</summary>
        {(payload.backlog || []).map((c, i) => (
          <div key={i} style={{ fontSize: 13 }}>{c.ticker} - {c.direction} - ${(c.dollars || 0).toLocaleString()} - p{c.priority}</div>
        ))}
      </details>
      {payload.congruence?.status === "ok"
        ? (payload.congruence.rows || []).map((r, i) => (
            <div key={i} style={{ fontSize: 13, margin: "3px 0" }}>{r.flagged ? "\ud83d\udea9 " : ""}{r.insight_id} - {r.line}</div>))
        : <div style={{ fontSize: 13 }}>congruence: not checked - {payload.congruence?.reason}</div>}
      <div style={{ fontFamily: "ui-monospace,Menlo,monospace", fontSize: 11, color: "#94a3b8",
                    borderTop: "1px solid #1e293b", marginTop: 12, paddingTop: 8 }}>
        {Object.entries(payload.honesty || {}).map(([k, v]) => <div key={k}>{k}: {String(v)}</div>)}
      </div>
    </section>
  );
}
