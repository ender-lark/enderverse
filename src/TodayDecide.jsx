import { useState } from "react";

const GATE_COLORS = { red: "#f87171", red_but_tested: "#fbbf24", green: "#34d399", context: "#94a3b8" };
const TRUST_COLORS = { ok: "#34d399", warn: "#fbbf24", alert: "#f87171", info: "#94a3b8" };
const HEALTH_COLORS = {
  fresh: "#34d399",
  aging: "#fbbf24",
  behind: "#f87171",
  stale: "#f87171",
  missing: "#f87171",
  empty: "#fbbf24",
  not_checked: "#94a3b8",
  context: "#94a3b8",
};

const copyText = (t) => {
  if (navigator.clipboard?.writeText) navigator.clipboard.writeText(t);
};

function reviewPosture(card, checkFirst, windowClass, direction) {
  if (isFundingLeg(card)) {
    return {
      label: "PAIR & FUND",
      stateVerb: "RECHECK",
      copyVerb: "RECHECK",
      copySuffix: " funding sell only; pair with funded add",
      reason: "funding sell only; do not sell standalone",
    };
  }
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
                       textTransform: "uppercase", margin: "12px 0 6px" }}>{children}</div>;
}

const healthSummary = (items) => {
  const alertStatuses = new Set(["behind", "stale", "missing", "empty"]);
  const alerts = (items || []).filter((item) => alertStatuses.has(item.status)).length;
  const fresh = (items || []).filter((item) => item.status === "fresh").length;
  const notChecked = (items || []).filter((item) => item.status === "not_checked").length;
  const parts = [];
  if (alerts) parts.push(`${alerts} alert${alerts === 1 ? "" : "s"}`);
  if (fresh) parts.push(`${fresh} fresh`);
  if (notChecked) parts.push(`${notChecked} not checked`);
  return `data freshness: ${parts.length ? parts.join(", ") : `${(items || []).length} checked`}`;
};

const gateSummary = (gates) => {
  const rows = gates || [];
  if (!rows.length) return "gates: none";
  const bits = rows.slice(0, 3).map((gate) => `${String(gate.state || "unknown").replace("_", " ").toUpperCase()} ${String(gate.symbol || "").toUpperCase()}`.trim());
  if (rows.length > 3) bits.push(`+${rows.length - 3} more`);
  return `gates: ${bits.join("; ")}`;
};

function CompactResponsiveStyles() {
  return (
    <style>{`
      .td-react-health-compact,.td-react-gates-compact{display:none}
      @media (max-width:620px){
        .td-react-shell{padding:12px!important}
        .td-react-anchor{font-size:16px!important}
        .td-react-pace{font-size:10px!important;margin-bottom:8px!important}
        .td-react-plan{font-size:12px!important;margin-bottom:6px!important}
        .td-react-health-full,.td-react-gates-full{display:none!important}
        .td-react-health-compact,.td-react-gates-compact{display:block!important}
      }
    `}</style>
  );
}

function HealthStrips({ items }) {
  const rows = items || [];
  if (!rows.length) return null;
  const chips = rows.map((item, i) => {
    const color = HEALTH_COLORS[item.status] || "#94a3b8";
    return (
      <span key={i} style={{ display: "inline-block", border: `1px solid ${color}`, borderRadius: 7, padding: "1px 7px", fontSize: 11, color: "#cbd5e1", margin: "0 4px 4px 0", background: "#0b1220" }}>
        {item.label}: <span style={{ color }}>{item.detail}</span>
      </span>
    );
  });
  return (
    <>
      <div className="td-react-health-full" style={{ margin: "8px 0 4px", lineHeight: 2 }}>
        <span style={{ fontSize: 11, color: "#64748b", fontWeight: 700, letterSpacing: ".03em" }}>data freshness: </span>{chips}
      </div>
      <details className="td-react-health-compact" style={{ border: "1px solid #334155", borderRadius: 8, background: "#0b1220", padding: "7px 9px", margin: "6px 0", color: "#cbd5e1" }}>
        <summary style={{ cursor: "pointer", fontSize: 12, fontWeight: 800, color: "#e2e8f0" }}>{healthSummary(rows)}</summary>
        <div style={{ marginTop: 7, lineHeight: 1.8 }}>{chips}</div>
      </details>
    </>
  );
}

function GateStrips({ gates }) {
  const rows = gates || [];
  if (!rows.length) return null;
  const chips = rows.map((g, i) => (
    <span key={i} style={{ display: "inline-block", border: `1px solid ${GATE_COLORS[g.state] || "#94a3b8"}`,
                           color: GATE_COLORS[g.state] || "#94a3b8", borderRadius: 999, padding: "2px 10px",
                           fontSize: 12, margin: "0 6px 8px 0" }}>
      {String(g.state || "").replace("_", " ").toUpperCase()} {g.symbol} - {g.confirm_rule} (as of {g.stated})
    </span>
  ));
  return (
    <>
      <div className="td-react-gates-full" style={{ margin: "0 0 2px" }}>{chips}</div>
      <details className="td-react-gates-compact" style={{ border: "1px solid #334155", borderRadius: 8, background: "#0b1220", padding: "7px 9px", margin: "6px 0", color: "#cbd5e1" }}>
        <summary style={{ cursor: "pointer", fontSize: 12, fontWeight: 800, color: "#e2e8f0" }}>{gateSummary(rows)}</summary>
        <div style={{ marginTop: 7, lineHeight: 1.8 }}>{chips}</div>
      </details>
    </>
  );
}

function TrustPanel({ payload }) {
  const panel = payload.trust_panel || {};
  const status = String(panel.status || "info");
  const border = TRUST_COLORS[status] || "#334155";
  const bg = status === "alert" ? "#1f0d12" : status === "warn" ? "#1b1607" : status === "ok" ? "#071910" : "#08111f";
  return (
    <div style={{ border: `1px solid ${border}`, borderRadius: 10, background: bg, padding: "10px 12px", margin: "10px 0 12px" }}>
      <div style={{ fontSize: 15, color: "#f8fafc", fontWeight: 900, marginBottom: 8 }}>Can I trust this screen? {panel.headline || "Trust status not checked"}</div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(190px,1fr))", gap: 8 }}>
        {(panel.items || []).map((item, i) => {
          const color = TRUST_COLORS[item.status] || "#94a3b8";
          return (
            <div key={`${item.label || "status"}-${i}`} style={{ border: "1px solid #334155", borderRadius: 8, background: "#0b1220", padding: 8 }}>
              <div style={{ fontSize: 10, color, textTransform: "uppercase", fontWeight: 900, letterSpacing: ".06em" }}>{item.label || "status"}</div>
              <div style={{ fontSize: 13, color: "#e2e8f0", lineHeight: 1.35, marginTop: 3 }}>{item.detail || ""}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function TopVerdict({ payload }) {
  const cards = payload.cards || [];
  const material = cards.filter(isMaterial);
  const funding = cards.filter(isFundingLeg);
  const starved = cards.filter((card) => cardIsEvidenceStarved(card, card.conviction_display || {}));
  const leanReady = cards.filter((card) => {
    const display = card.conviction_display || {};
    return isMaterial(card) && !(card.card_blockers || []).length && !display.conflict && card.window?.class === "OPEN-NOW";
  });
  const staleOrUnfed = (payload.data_health?.items || []).filter((item) => ["behind", "stale", "missing", "empty", "not_checked"].includes(item.status));
  const signals = cards
    .filter((card) => !isFundingLeg(card))
    .map((card) => {
      const display = card.conviction_display || {};
      return strongestDirectionalFactor(display) ? `${card.ticker}: ${nameSignalText(card, display).replace("Name signal: ", "")}` : null;
    })
    .filter(Boolean);
  const capCards = material.filter((card) => String(card.sizing?.heat || "") === "ABOVE_CAP");
  const levers = [];
  const materialTickers = material.filter((card) => !isFundingLeg(card)).map((card) => String(card.ticker || "").toUpperCase()).filter(Boolean);
  if (materialTickers.length) levers.push(`fresh-check material names (${materialTickers.slice(0, 3).join("/")})`);
  if (staleOrUnfed.length || starved.length) levers.push("load the FS inbox / get a graded call");
  if (capCards.length) levers.push(`revisit the ${String(capCards[0].ticker || "").toUpperCase()} cap if conviction warrants`);
  if (!levers.length) levers.push("write or refresh the dated thesis that would change the action");
  const title = leanReady.length
    ? `${leanReady.length} lean-in-ready material card${leanReady.length === 1 ? "" : "s"}.`
    : `Nothing actionable yet: scorer is starved or blocked, not bearish. Next lever: ${levers.join(" or ")}.`;
  const line = [
    `${material.length} material decision${material.length === 1 ? "" : "s"}`,
    `${funding.length} funding-only leg${funding.length === 1 ? "" : "s"}`,
    `${starved.length} evidence-starved card${starved.length === 1 ? "" : "s"}`,
    staleOrUnfed.length ? `${staleOrUnfed.length} stale/not-checked lane${staleOrUnfed.length === 1 ? "" : "s"}` : "",
    signals.length ? `strongest evidence: ${signals.slice(0, 2).join("; ")}` : "",
  ].filter(Boolean).join(" | ");
  return (
    <div style={{ border: "1px solid #334155", borderLeft: "4px solid #38bdf8", borderRadius: 10, background: "#08111f", padding: "10px 12px", margin: "10px 0 12px" }}>
      <div style={{ fontSize: 15, color: "#f8fafc", fontWeight: 850, marginBottom: 3 }}>{title}</div>
      <div style={{ fontSize: 12, color: "#cbd5e1", lineHeight: 1.4 }}>{line}</div>
    </div>
  );
}

const shortText = (value, limit = 130) => {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  return text.length <= limit ? text : `${text.slice(0, Math.max(0, limit - 1)).trim()}...`;
};

const factorDates = (factors) => {
  const dates = new Set();
  factors.forEach((row) => {
    `${row.value_str || ""} ${row.source || ""}`.match(/20\d{2}-\d{2}-\d{2}/g)?.forEach((date) => dates.add(date));
  });
  return [...dates].sort();
};

const shownNotCountedNote = (display, factors, builtDate) => {
  const groupPoints = (display.why?.groups || []).reduce((acc, row) => acc + Math.abs(Number(row.points || 0)), 0);
  const hasContextFlow = factors.some((row) => String(row.key || row.source || "").includes("uw_opportunity"));
  const needsSameSession = (display.raises || []).some((item) => {
    const low = String(item).toLowerCase();
    return low.includes("same-session") || low.includes("uw proof");
  });
  if (!factors.length || groupPoints >= 0.1 || !(hasContextFlow || needsSameSession)) return "";
  const dates = factorDates(factors);
  const dateText = dates.length ? dates.join(", ") : "earlier cached evidence";
  if (factors.some((row) => factorIsStaleContext(row, builtDate))) {
    return `Stale context, not current edge: these UW signals are from ${dateText}, not this session's 9:40 gate. Treat them as already-played or expired until refreshed; they are not moving the score and should not pull action.`;
  }
  return `Shown but not counted: these signals are from ${dateText} and have not been re-confirmed this session (9:40 gate), so they are context only and are not moving the score yet.`;
};

const factorAsOf = (row) => `${row.value_str || ""} ${row.source || ""}`.match(/20\d{2}-\d{2}-\d{2}/)?.[0] || null;

const factorIsStaleContext = (row, builtDate) => {
  if (!builtDate) return false;
  const keySource = `${row.key || ""} ${row.source || ""}`;
  if (!keySource.includes("uw_opportunity")) return false;
  const asOf = factorAsOf(row);
  return Boolean(asOf && asOf !== builtDate);
};

const actionGerund = (direction) => ({
  BUY: "buying",
  ADD: "adding",
  SELL: "selling",
  TRIM: "trimming",
  REDUCE: "trimming",
}[String(direction || "").toUpperCase()] || "acting on");

const scoreText = (display) => {
  const label = String(display.text || "");
  const scoreMatch = label.match(/([1-5])\s*\/\s*5/);
  const bandMatch = label.match(/\((LOW|MODERATE|HIGH)\)/i);
  const x5 = display.x5 ?? (scoreMatch ? scoreMatch[1] : 1);
  const band = String(display.band || (bandMatch ? bandMatch[1] : "LOW")).toUpperCase();
  return `Conviction ${x5}/5 ${band}`;
};

const moneyText = (value) => (typeof value === "number" ? `$${value.toLocaleString(undefined, { maximumFractionDigits: 0 })}` : "size n/a");

const cardDirection = (card, fallback) => String(card?.decision_card?.move?.direction || card?.direction || fallback || "").toUpperCase();

const isMaterial = (card) => Boolean(card.impact?.material);

const isFundingLeg = (card) => {
  const direction = cardDirection(card);
  if (!["SELL", "TRIM", "REDUCE"].includes(direction)) return false;
  const reasons = (card.window?.reasons || []).join(" ").toLowerCase();
  if (reasons.includes("funding leg") || reasons.includes("paired with the adds")) return true;
  return Boolean((card.execution?.legs || []).length) && !isMaterial(card);
};

const sizeLabel = (card) => `${moneyText(card.dollars)} / ${isMaterial(card) ? "material" : "immaterial"}`;

const fundingSellLabel = (card) => `${moneyText(card.dollars)} funding sell — only if paired with the buy it funds`;

const fundedAdds = (card) => {
  const links = card.decision_card?.evidence?.links || [];
  return links
    .map((link) => {
      const label = String(link?.label || "");
      if (!label.toLowerCase().includes("funds")) return null;
      const match = label.match(/\b([A-Z]{1,6})\b\s+\$?([0-9][0-9,]*(?:\.\d+)?)/);
      return match ? { ticker: match[1], amount: `$${match[2]}` } : null;
    })
    .filter(Boolean);
};

const fundedAddText = (card) => {
  const adds = fundedAdds(card);
  return adds.length ? `the ${adds[0].ticker} ${adds[0].amount} add` : "the paired add it funds";
};

const lookthroughRationale = (card) => {
  const contains = String(card.lookthrough?.contains_line || "").trim();
  if (!contains) return "";
  return `Rationale: this funding sell rotates out of MAG7 basket exposure (${contains.replace("contains ", "")}) to fund the paired single-name add.`;
};

function FundingPairBlock({ card }) {
  if (!isFundingLeg(card)) return null;
  const adds = fundedAdds(card);
  const rationale = lookthroughRationale(card);
  return (
    <div style={{ border: "1px solid #334155", borderRadius: 8, background: "#0b1220", padding: 8, fontSize: 13, color: "#cbd5e1", lineHeight: 1.4, margin: "0 0 8px" }}>
      <strong>Pair this sell with:</strong>{" "}
      {adds.length
        ? adds.map((add, i) => (
            <span key={add.ticker}>
              {i > 0 ? ", " : ""}
              <a href={`#td-card-${add.ticker}`} style={{ color: "#93c5fd" }}>{add.ticker} {add.amount} add</a>
            </span>
          ))
        : "the paired add it funds"}
      . Do not do the sell by itself.
      {rationale && <><br />{rationale}</>}
    </div>
  );
}

const directionSignalWord = (direction) => {
  const value = String(direction || "").toLowerCase();
  if (value === "bull") return "bullish";
  if (value === "bear") return "bearish";
  return "neutral";
};

const strongestDirectionalFactor = (display) => {
  const directional = (display.why?.decisive_factors || []).filter((row) => ["bull", "bear"].includes(String(row.direction || "").toLowerCase()));
  return directional.sort((a, b) => (Number(Boolean(b.decisive)) - Number(Boolean(a.decisive))) || (Number(b.strength || 0) - Number(a.strength || 0)))[0] || null;
};

const nameSignalText = (card, display) => {
  const factor = strongestDirectionalFactor(display);
  if (factor) {
    const text = `${directionSignalWord(factor.direction)} (${factor.label || factor.key || "evidence"})`;
    return `Name signal: ${text}`;
  }
  const moved = (display.why?.groups || []).find((row) => Math.abs(Number(row.points || 0)) >= 0.25);
  if (moved) return `Name signal: ${String(moved.direction || "neutral").toLowerCase()} (${moved.label || moved.key || "source"})`;
  return "Name signal: not fed yet";
};

const layerStatusWord = (row) => {
  if (!row) return "off";
  const status = String(row.status || "not_checked");
  const direction = String(row.direction || "NEUTRAL").toUpperCase();
  const read = String(row.read || "LOW").toUpperCase();
  const points = Math.abs(Number(row.points || 0));
  if (status === "not_checked") return "unfed";
  if (status === "checked_no_signal" || (points < 0.005 && direction === "NEUTRAL")) return "quiet";
  if (status === "not_applicable") return "n/a";
  if (["BUY", "BULL"].includes(direction)) return `supportive ${read}`;
  if (["SELL", "TRIM", "BEAR"].includes(direction)) return `bearish ${read}`;
  return read;
};

const layerRows = (display) => Object.fromEntries((display.layers?.rows || []).map((row) => [row.key, row]));

const layerSummaryText = (display) => {
  const rows = layerRows(display);
  if (!Object.keys(rows).length) return "Name/sector layer: off";
  return `Name: ${layerStatusWord(rows.name)} | Sector: ${layerStatusWord(rows.sector)} | Shadow: ${String(rows.overall?.read || "LOW").toUpperCase()}`;
};

const layersEmpty = (display) => {
  const layers = display.layers || {};
  const rows = layers.rows || [];
  if (!rows.length || layers.mode === "off" || layers.conflict) return false;
  const byKey = layerRows(display);
  if (["active"].includes(byKey.name?.status) || ["active"].includes(byKey.sector?.status)) return false;
  return rows.every((row) => Math.abs(Number(row.points || 0)) < 0.005);
};

const cardIsEvidenceStarved = (card, display) => {
  const groupPoints = (display.why?.groups || []).reduce((acc, row) => acc + Math.abs(Number(row.points || 0)), 0);
  const rows = layerRows(display);
  return groupPoints < 0.1 && ((rows.name?.status || "not_checked") === "not_checked" || (display.not_checked || []).length > 0);
};

const primaryBlockerText = (card, display, checkFirst, windowClass) => {
  if (isFundingLeg(card)) return "Funding sell only; pair it with the add it pays for and do not sell the stock on its own.";
  if (card.sizing?.heat === "ABOVE_CAP") return "Above cap; no size room until thesis/cap is revisited.";
  if (card.sizing?.heat === "CAP_CLIPPED") return "Cap clipped; staged size must stay within room.";
  if ((card.card_blockers || []).length) return `${card.card_blockers[0]} blocks full action.`;
  if (display.conflict) return display.conflict;
  if (windowClass === "STAGE-ONLY") return "Stage only; wait for trigger before full action.";
  return "No blocking reason surfaced.";
};

const faceSentence = (card, display, status, blocker) => {
  const ticker = String(card.ticker || "").toUpperCase();
  if (isFundingLeg(card)) {
    const factor = strongestDirectionalFactor(display);
    const paired = fundedAddText(card);
    if (String(factor?.direction || "").toLowerCase() === "bull") {
      return `Funding sell. Only do this alongside ${paired}; the stock itself looks bullish on flow, so don't sell it on its own.`;
    }
    return `Funding sell. Only do this alongside ${paired}; don't sell it on its own.`;
  }
  if (status === "stage material buy") return `Material buy candidate. Stage ${ticker} only after the blocker clears: ${blocker}`;
  if (status === "needs feed") return `Not actionable yet. Feed the missing evidence first; ${blocker}`;
  if (status === "resolve direction") return `Do not act yet. Resolve the conflicting evidence first: ${blocker}`;
  if (status === "stage only") return "Stage-only candidate. Keep it queued until the trigger and blocker checks clear.";
  if (status === "lean-in candidate") return "Lean-in candidate. Evidence is clear enough to consider action inside the stated rails.";
  return `Review first. ${blocker}`;
};

const splitRaiseActions = (display) => {
  const operator = [];
  const waiting = [];
  const system = [];
  (display.raises || []).forEach((item) => {
    const low = String(item).toLowerCase();
    if (["dated entry", "entry/stop/target", "tier a", "analyst call"].some((token) => low.includes(token))) waiting.push(item);
    else if (["13f", "insider", "lane goes live", "uw proof", "same-session", "wired"].some((token) => low.includes(token))) system.push(item);
    else operator.push(item);
  });
  if (!operator.length) operator.push("Decide whether the surfaced signal is real enough to write or refresh the thesis.");
  if (!system.length) system.push("No separate system wiring task surfaced for this card.");
  return [operator.slice(0, 3), waiting.slice(0, 3), system.slice(0, 3)];
};

const shadowLiftText = (display) => {
  const rows = display.layers?.rows || [];
  const overall = rows.find((row) => row.key === "overall");
  return overall?.detail ? overall.detail.replace("sector lift ", "shadow ") : "shadow layer present";
};

const gateNoteRank = (status) => ({ alert: 0, warn: 1, ok: 2, context: 3, info: 4 }[String(status || "info")] ?? 4);

const firstGateNote = (card) => {
  const notes = (card.gate_notes || []).filter(Boolean);
  if (!notes.length) return null;
  return [...notes].sort((a, b) => gateNoteRank(a.status) - gateNoteRank(b.status))[0];
};

function GateNotes({ card }) {
  const notes = (card.gate_notes || []).filter(Boolean);
  if (!notes.length) return null;
  return (
    <>
      {notes.map((note, i) => {
        const color = note.status === "ok" ? "#34d399" : note.status === "warn" ? "#fbbf24" : "#334155";
        const bg = note.status === "ok" ? "#071910" : note.status === "warn" ? "#1b1607" : "#0b1220";
        return (
          <div key={`${note.label || "gate"}-${i}`} style={{ border: `1px solid ${color}`, borderRadius: 8, background: bg, padding: 8, fontSize: 13, color: note.status === "ok" ? "#bbf7d0" : note.status === "warn" ? "#fde68a" : "#cbd5e1", lineHeight: 1.4, margin: "0 0 8px" }}>
            <strong>{note.label || "Sizing gate"}:</strong> {note.summary || ""}
          </div>
        );
      })}
    </>
  );
}

const conflictTags = (display, card) => {
  const tags = [];
  const conflict = String(display.conflict || "").toLowerCase();
  if (conflict.includes("battery") || conflict.includes("opposes") || conflict.includes("opposition")) tags.push(isFundingLeg(card) ? "positive signal conflicts" : "flow opposes move");
  if (conflict.includes("no directional evidence")) tags.push("no direct score support");
  if (display.conflict && !tags.length) tags.push("evidence conflict");
  if ((card.conflicts || []).length) tags.push("another lane disagrees");
  return tags;
};

function faceModel(card, display, posture, checkFirst, windowClass, direction) {
  const ticker = String(card.ticker || "").toUpperCase();
  const tags = conflictTags(display, card);
  const fundingLeg = isFundingLeg(card);
  const material = isMaterial(card);
  const hasDirectionalConflict = tags.some((tag) => tag !== "no direct score support");
  const noDirectionalSupport = tags.includes("no direct score support") && !hasDirectionalConflict;
  const blockers = card.card_blockers || [];
  const blockersAreGates = blockers.length > 0 && blockers.every((blocker) => String(blocker).toLowerCase().includes("gate"));
  const stageMaterial = ["BUY", "ADD"].includes(String(direction || "").toUpperCase()) && material && windowClass === "STAGE-ONLY";
  let status = "review";
  let title = `Review ${ticker} before acting`;
  if (fundingLeg) {
    status = "funding sell only";
    title = fundingSellLabel(card);
  } else if (hasDirectionalConflict) {
    status = "resolve direction";
    title = `Resolve signal before ${actionGerund(direction)} ${ticker}`;
  } else if (stageMaterial && (!blockers.length || blockersAreGates)) {
    status = "stage material buy";
    title = `Stage ${moneyText(card.dollars)} ${ticker} buy`;
  } else if (checkFirst || blockers.length || noDirectionalSupport) {
    status = "needs feed";
    title = `Feed evidence before ${actionGerund(direction)} ${ticker}`;
  } else if (windowClass === "STAGE-ONLY") {
    status = "stage only";
    title = `Stage ${String(direction || "").toLowerCase()} candidate for ${ticker}`;
  } else if (posture.copyVerb === "ACT") {
    status = "lean-in candidate";
    title = `${String(direction || "Act").toLowerCase()} ${ticker} can be considered`;
  }
  const tagRows = [];
  tagRows.push([material ? "material" : "muted", sizeLabel(card)]);
  if (fundingLeg) tagRows.push(["muted", "funding only"]);
  const blocker = primaryBlockerText(card, display, checkFirst, windowClass);
  const gateNote = firstGateNote(card);
  return {
    status,
    title,
    subtitle: "",
    signal: nameSignalText(card, display),
    layer: layerSummaryText(display),
    blocker,
    sentence: faceSentence(card, display, status, blocker),
    gateNote: gateNote?.summary || "",
    tags: tagRows,
  };
}

const firstRaise = (display) => {
  const [operator, waiting, system] = splitRaiseActions(display);
  if (operator.length) return operator[0];
  if (waiting.length) return `Waiting on: ${waiting[0]}`;
  if (system.length) return system[0];
  return "Fresh confirming evidence that clears the current blocker.";
};

function DecisionReadout({ card, display, posture, checkFirst, windowClass, direction }) {
  const face = faceModel(card, display, posture, checkFirst, windowClass, direction);
  const answer = face.status === "funding sell only"
    ? "Do not treat as a standalone trade"
    : posture.copyVerb === "ACT" && !checkFirst && !display.conflict
      ? "Lean-in candidate"
    : face.status === "stage only"
      ? "Stage only"
      : face.status === "stage material buy"
        ? "Stage material buy; full action still blocked"
        : face.status === "needs feed"
          ? "Feed evidence before action"
        : face.status === "resolve direction"
          ? "Do not act yet"
          : "Review first";
  const why = face.blocker || face.tags.map(([, label]) => label).slice(0, 3).join("; ");
  return (
    <div style={{ border: "1px solid #334155", borderRadius: 8, background: "#0b1220", padding: 10, marginBottom: 10 }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(180px,1fr))", gap: 8 }}>
        {[
          ["Current answer", answer],
          ["Why", why || "No blocker surfaced in the rendered card."],
          ["Next check", firstRaise(display)],
          ["Score", scoreText(display)],
        ].map(([k, v]) => (
          <div key={k}>
            <div style={{ fontSize: 10, color: "#94a3b8", fontWeight: 900, letterSpacing: ".06em", textTransform: "uppercase" }}>{k}</div>
            <div style={{ fontSize: 14, color: "#f8fafc", fontWeight: 750, lineHeight: 1.3, marginTop: 2 }}>{v}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function WhyBreakdown({ display, card, builtDate }) {
  const why = display.why || {};
  const factors = why.decisive_factors || [];
  const factorTag = (f, card) => {
    if (factorIsStaleContext(f, builtDate)) {
      const direction = String(f.direction || "").toLowerCase();
      if (["bull", "bear"].includes(direction)) return `stale ${directionSignalWord(direction)} context`;
      return "stale context";
    }
    const direction = String(f.direction || "").toLowerCase();
    if (card && isFundingLeg(card) && ["bull", "bear"].includes(direction)) return `${directionSignalWord(direction)} name signal`;
    if (f.conflict) return "opposes card action";
    if (["bull", "bear"].includes(direction)) return `${directionSignalWord(direction)} setup`;
    return "context";
  };
  const note = shownNotCountedNote(display, factors, builtDate);
  return (
    <>
      {note && (
        <div style={{ border: "1px solid #334155", borderRadius: 8, background: "#0b1220", padding: 8, fontSize: 13, color: "#cbd5e1", lineHeight: 1.4, margin: "0 0 8px" }}>
          {note}
        </div>
      )}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(210px,1fr))", gap: 8 }}>
        {factors.length
          ? factors.slice(0, 4).map((f) => (
              <div key={f.key} style={{ border: `1px solid ${factorIsStaleContext(f, builtDate) ? "#475569" : f.conflict ? "#f59e0b" : "#334155"}`, borderRadius: 8, padding: 8, background: factorIsStaleContext(f, builtDate) ? "#0b1220" : f.conflict ? "#1f1606" : "#0b1220", opacity: factorIsStaleContext(f, builtDate) ? .74 : 1 }}>
                <div style={{ fontSize: 10, color: "#94a3b8", textTransform: "uppercase", fontWeight: 900, letterSpacing: ".05em" }}>{factorTag(f, card)}</div>
                <div style={{ fontSize: 13, color: "#f8fafc", fontWeight: 800, marginTop: 2 }}>{f.label || f.key}</div>
                <div style={{ fontSize: 12, color: "#cbd5e1", lineHeight: 1.35, marginTop: 3 }}>{shortText(f.value_str)}</div>
              </div>
            ))
          : <div style={{ fontSize: 13, color: "#cbd5e1" }}>Battery decisive factors: none surfaced.</div>}
      </div>
    </>
  );
}

function ScoreInputs({ display }) {
  const groups = display.why?.groups || [];
  return (
    <details style={{ border: "1px solid #243044", borderRadius: 8, background: "#0b1220", padding: 8, margin: "8px 0", fontSize: 12, color: "#94a3b8" }}>
      <summary style={{ cursor: "pointer", fontWeight: 750 }}>Scoring inputs</summary>
      {groups.length
        ? groups.map((g) => (
            <div key={g.key} style={{ fontSize: 13, color: "#cbd5e1", margin: "3px 0" }}>
              <strong style={{ color: "#e2e8f0" }}>{g.label || g.key}</strong> {Number(g.points || 0) >= 0 ? "+" : ""}{Number(g.points || 0).toFixed(2)}
            </div>
          ))
        : <div style={{ fontSize: 13, color: "#cbd5e1" }}>No scored group has moved the conviction yet.</div>}
    </details>
  );
}

function LayerBreakdown({ display }) {
  const layers = display.layers || {};
  const rows = layers.rows || [];
  if (!rows.length || layers.mode === "off") return null;
  const pointText = (points) => {
    const value = Number(points || 0);
    return `${value >= 0 ? "+" : ""}${value.toFixed(2)}`;
  };
  const recheck = layers.sector_only_recheck || {};
  if (layersEmpty(display)) {
    return (
      <>
        <SectionTitle>Name / sector split</SectionTitle>
        <div style={{ border: "1px solid #334155", borderRadius: 8, background: "#0b1220", padding: 8, fontSize: 13, color: "#cbd5e1", lineHeight: 1.35 }}>
          Name/sector evidence not fed yet; no positive layer is active.
        </div>
      </>
    );
  }
  return (
    <>
      <SectionTitle>Name / sector split</SectionTitle>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(160px,1fr))", gap: 8 }}>
        {rows.map((row) => (
          <div key={row.key} style={{ border: "1px solid #334155", borderRadius: 8, background: "#0b1220", padding: 8 }}>
            <div style={{ fontSize: 10, color: "#94a3b8", textTransform: "uppercase", fontWeight: 900, letterSpacing: ".05em" }}>{row.label || row.key}</div>
            <div style={{ fontSize: 14, color: "#f8fafc", fontWeight: 800, marginTop: 2 }}>{row.read || "LOW"} {pointText(row.points)}</div>
            <div style={{ fontSize: 12, color: "#cbd5e1", lineHeight: 1.35, marginTop: 3 }}>{row.status || "not_checked"}{row.detail ? ` | ${row.detail}` : ""}</div>
          </div>
        ))}
      </div>
      {layers.conflict && (
        <div style={{ border: "1px solid #fb923c", color: "#fdba74", borderRadius: 8,
                      padding: "6px 8px", fontSize: 12, margin: "6px 0" }}>
          Layer guard: {layers.conflict}
        </div>
      )}
      {(layers.clamped_reasons || []).map((reason, i) => (
        <div key={`guard${i}`} style={{ fontSize: 13, color: "#cbd5e1", margin: "4px 0" }}>Layer guard: {reason}</div>
      ))}
      {recheck.eligible && (
        <div style={{ fontSize: 13, color: "#cbd5e1", margin: "4px 0" }}>
          Sector-only recheck: {recheck.next_step || "re-check"} ({recheck.alert_enabled ? "alert enabled" : "alert disabled in shadow mode"})
        </div>
      )}
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
  const allUnknown = Object.values(dossier.reads || {}).every((read) => {
    const freshness = read?.freshness || {};
    return (freshness.status || "not_checked") === "not_checked" && String(read?.text || "UNKNOWN").toUpperCase() === "UNKNOWN";
  });
  const content = (
    <>
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
    </>
  );
  if (allUnknown) {
    return (
      <details style={{ border: "1px solid #243044", borderRadius: 8, background: "#0b1220", padding: 8, margin: "8px 0", fontSize: 12, color: "#94a3b8" }}>
        <summary style={{ cursor: "pointer", fontWeight: 750 }}>Decision dossier not checked for {dossier.ticker || ticker}</summary>
        {content}
      </details>
    );
  }
  return (
    <div style={{ border: "1px solid #334155", borderRadius: 8, padding: 8, margin: "8px 0", background: "#0b1220" }}>
      {content}
    </div>
  );
}

function CardFace({ card, rank, display, posture, checkFirst, windowClass, direction }) {
  const face = faceModel(card, display, posture, checkFirst, windowClass, direction);
  const tagStyle = (kind) => ({
    display: "inline-flex", alignItems: "center", borderRadius: 999, border: `1px solid ${kind === "danger" ? "#ef4444" : kind === "warn" ? "#f59e0b" : "#334155"}`,
    color: kind === "danger" ? "#fecaca" : kind === "warn" ? "#fde68a" : kind === "material" ? "#bfdbfe" : "#94a3b8",
    background: kind === "danger" ? "#220b0b" : kind === "warn" ? "#1f1606" : kind === "material" ? "#061321" : "#0b1220",
    padding: "3px 8px", fontSize: 12, fontWeight: 650,
  });
  return (
    <div style={{ display: "grid", gap: 8 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 10, alignItems: "flex-start", flexWrap: "wrap" }}>
        <div>
          <div style={{ fontSize: 12, color: "#94a3b8", fontWeight: 800, letterSpacing: ".04em", textTransform: "uppercase" }}>#{rank} {String(card.ticker || "")}</div>
          <div style={{ fontSize: 12, fontWeight: 900, letterSpacing: ".06em", textTransform: "uppercase" }}>{face.status}</div>
          <div style={{ fontSize: 20, fontWeight: 850, lineHeight: 1.18, color: "#f8fafc", margin: "1px 0" }}>{face.title}</div>
          <div style={{ fontSize: 14, color: "#e2e8f0", lineHeight: 1.4, marginTop: 7, maxWidth: 760 }}>{face.sentence}</div>
          {face.gateNote && <div style={{ fontSize: 12, color: "#fde68a", lineHeight: 1.35, marginTop: 6, maxWidth: 760 }}>{face.gateNote}</div>}
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "flex-end", gap: 6, minWidth: 150 }}>
          <span style={{ display: "inline-flex", alignItems: "center", borderRadius: 999, padding: "4px 9px", fontSize: 12, fontWeight: 850, color: "#0b1220", background: display.band_color || "#94a3b8", whiteSpace: "nowrap" }}>{scoreText(display)}</span>
        </div>
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
        {face.tags.map(([kind, label]) => <span key={label} style={tagStyle(kind)}>{label}</span>)}
      </div>
    </div>
  );
}

function Card({ card, rank, checkFirst, railState, setRailState, builtDate }) {
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
  const [operatorActions, waitingActions, systemActions] = splitRaiseActions(display);
  const primaryCopy = posture.copyVerb === "ACT"
    ? `ACT ${card.card_id}`
    : `${posture.copyVerb} ${card.card_id}${posture.copySuffix}`;
  return (
    <details data-ticker={ticker} style={{ border: `1px solid ${conflicted ? "#f59e0b" : "#243044"}`, borderRadius: 10,
                      padding: 0, margin: "10px 0", background: "#0f172a" }} id={`td-card-${String(ticker || "").toUpperCase()}`}>
      <summary style={{ listStyle: "none", cursor: "pointer", padding: 12 }}>
        <CardFace card={card} rank={rank} display={display} posture={posture} checkFirst={scopedCheckFirst} windowClass={win.class} direction={move.direction} />
      </summary>
      <div style={{ padding: "10px 12px 12px", borderTop: "1px solid #1e293b", marginTop: 8 }}>
        <DecisionReadout card={card} display={display} posture={posture} checkFirst={scopedCheckFirst} windowClass={win.class} direction={move.direction} />
        <GateNotes card={card} />
        <FundingPairBlock card={card} />
        <SectionTitle>Evidence that matters</SectionTitle>
        <WhyBreakdown display={display} card={card} builtDate={builtDate} />
        <LayerBreakdown display={display} />
        {(card.conflicts || []).map((c, i) => (
          <div key={i} style={{ border: "1px solid #f59e0b", color: "#fdba74", borderRadius: 8,
                                padding: "6px 8px", fontSize: 12, margin: "6px 0" }}>
            {isFundingLeg(card)
              ? <>Signal/action split: {c.with} says "{c.their_claim}"; this card is only a funding sell paired with the buy it funds.</>
              : <>Source conflict: {c.with} says "{c.their_claim}"; this card says {c.card_claim}. Resolve before acting.</>}
          </div>
        ))}
        <ScoreInputs display={display} />
        <SectionTitle>What would make this actionable</SectionTitle>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(220px,1fr))", gap: 8 }}>
          <div style={{ border: "1px solid #334155", borderRadius: 8, background: "#0b1220", padding: 8 }}>
            <div style={{ fontSize: 10, color: "#94a3b8", fontWeight: 900, letterSpacing: ".06em", textTransform: "uppercase", marginBottom: 4 }}>Operator can do now</div>
            {operatorActions.map((r, i) => <div key={`op${i}`} style={{ fontSize: 13, color: "#cbd5e1", margin: "4px 0" }}>{r}</div>)}
          </div>
          {waitingActions.length > 0 && (
            <div style={{ border: "1px solid #334155", borderRadius: 8, background: "#0b1220", padding: 8 }}>
              <div style={{ fontSize: 10, color: "#94a3b8", fontWeight: 900, letterSpacing: ".06em", textTransform: "uppercase", marginBottom: 4 }}>Waiting on</div>
              {waitingActions.map((r, i) => <div key={`wait${i}`} style={{ fontSize: 13, color: "#cbd5e1", margin: "4px 0" }}>{r}</div>)}
            </div>
          )}
          <div style={{ border: "1px solid #334155", borderRadius: 8, background: "#0b1220", padding: 8 }}>
            <div style={{ fontSize: 10, color: "#94a3b8", fontWeight: 900, letterSpacing: ".06em", textTransform: "uppercase", marginBottom: 4 }}>System still needs wired</div>
            {systemActions.map((r, i) => <div key={`sys${i}`} style={{ fontSize: 13, color: "#cbd5e1", margin: "4px 0" }}>{r}</div>)}
          </div>
        </div>
        <DossierBlock dossier={dossier} ticker={ticker} />
        {posture.reason && <div style={{ fontSize: 13, color: "#cbd5e1", margin: "4px 0" }}><strong>Rail:</strong> {posture.reason}</div>}
        <Rail cardId={card.card_id} verb={posture.stateVerb} copy={primaryCopy} muted={posture.copyVerb !== "ACT"} state={railState} setState={setRailState} />
        <Rail cardId={card.card_id} verb="PASS" copy={`PASS ${card.card_id} â€” reason: `} state={railState} setState={setRailState} />
        {posture.stateVerb !== "RECHECK" && <Rail cardId={card.card_id} verb="RECHECK" copy={`RECHECK ${card.card_id} resurface ${card.recheck_date}`} state={railState} setState={setRailState} />}
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
        <details style={{ border: "1px solid #243044", borderRadius: 8, background: "#0b1220", padding: 8, margin: "8px 0", fontSize: 12, color: "#94a3b8" }}>
          <summary style={{ cursor: "pointer", fontWeight: 750 }}>Not checked / optional context</summary>
          <IvHint display={display} />
          <div style={{ fontSize: 13, color: "#cbd5e1", margin: "4px 0" }}>not checked: {(display.not_checked || []).length ? (display.not_checked || []).join(", ") : "none"}</div>
        </details>
      </div>
    </details>
  );
}

function ActionQueueTail({ payload, limit = 10 }) {
  const queue = [...(payload.cards || []), ...(payload.backlog || [])];
  if (queue.length <= (payload.cards || []).length) return null;
  return (
    <details style={{ border: "1px solid #243044", borderRadius: 8, background: "#0b1220", padding: 8, margin: "8px 0", fontSize: 12, color: "#94a3b8" }}>
      <summary style={{ cursor: "pointer", fontWeight: 750 }}>Show top {Math.min(limit, queue.length)} decision-queue items</summary>
      {queue.slice(0, limit).map((card, i) => {
        const display = card.conviction_display || { why: {}, raises: [], not_checked: [] };
        const win = card.window || {};
        const checkFirst = Boolean((card.card_blockers || []).length);
        const direction = cardDirection(card);
        const posture = reviewPosture(card, checkFirst, win.class || "WAIT", direction);
        const face = faceModel(card, display, posture, checkFirst, win.class || "WAIT", direction);
        return (
          <div key={`queue-${card.card_id || i}`} style={{ fontSize: 13, color: "#cbd5e1", margin: "4px 0" }}>
            <strong style={{ color: "#e2e8f0" }}>#{i + 1} {card.ticker || ""}</strong> - {face.status} - {face.title} ({sizeLabel(card)}; {scoreText(display)}; p{card.priority})
          </div>
        );
      })}
    </details>
  );
}

export default function TodayDecide({ payload }) {
  const [railState, setRailState] = useState({});
  if (!payload) return null;
  const ga = payload.goal_anchor || {}, pl = payload.plan_line || {};
  const sections = [
    ["Material decisions", (payload.cards || []).filter((card) => isMaterial(card) && !isFundingLeg(card))],
    ["Other rechecks", (payload.cards || []).filter((card) => !isMaterial(card) && !isFundingLeg(card))],
    ["Funding / paired sells", (payload.cards || []).filter(isFundingLeg)],
  ].filter(([, cards]) => cards.length);
  let rank = 1;
  return (
    <section className="td-react-shell" style={{ fontFamily: "-apple-system,'Segoe UI',Roboto,sans-serif", background: "#0b1220",
                      color: "#e2e8f0", border: "1px solid #1e293b", borderRadius: 12, padding: 18, marginBottom: 18 }}>
      <CompactResponsiveStyles />
      <h2 style={{ margin: 0, fontSize: 20, letterSpacing: ".04em" }}>
        TODAY - DECIDE <span style={{ color: "#94a3b8", fontSize: 12 }}>built {payload.built}</span>
      </h2>
      <div className="td-react-anchor" style={{ fontSize: 17, margin: "8px 0 2px" }}>
        {ga.book_value != null
          ? <>${ga.book_value.toLocaleString()} to ${ga.fi_target.toLocaleString()} - {ga.pct_to_target}% there</>
          : "book value: not readable - honest absence"}
      </div>
      <div className="td-react-pace" style={{ color: "#94a3b8", fontStyle: "italic", fontSize: 12, marginBottom: 10 }}>{ga.pace_line}</div>
      <div className="td-react-plan" style={{ color: "#cbd5e1", fontSize: 13, marginBottom: 10 }}>
        plan: {pl.pool_usd != null ? `funding pool $${pl.pool_usd.toLocaleString()}` : "funding pool n/a"}
        {pl.shortfall_usd != null ? ` - shortfall $${pl.shortfall_usd.toLocaleString()}` : ""} - positions as of {pl.positions_as_of}
      </div>
      <TrustPanel payload={payload} />
      <TopVerdict payload={payload} />
      {sections.map(([label, cards]) => (
        <div key={label}>
          <div style={{ fontSize: 11, color: "#94a3b8", textTransform: "uppercase", fontWeight: 900, letterSpacing: ".08em", margin: "14px 0 5px" }}>{label}</div>
          {cards.map((c) => {
            const thisRank = rank;
            rank += 1;
            return <Card key={c.card_id} card={c} rank={thisRank} checkFirst={Boolean((c.card_blockers || []).length)} railState={railState} setRailState={setRailState} builtDate={payload.built} />;
          })}
        </div>
      ))}
      <ActionQueueTail payload={payload} />
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
