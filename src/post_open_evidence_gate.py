"""Post-Open Evidence Gate routine (Task 8 / C-final).

The 9:40 AM ET cloud routine ("investing-os-post-open-evidence-gate" in
:mod:`cloud_ops_status`). For each gate in ``timing_gates.json``, ask
:func:`timing_engine.evaluate_gate` what the live price implies about the
gate's state, then write a propose-and-stamp row that the L5 wrapper can
persist back into ``timing_gates.json`` (the QQQ confirm / re-red flow that
this engine was born from).

The routine is **pure**: it takes loaded gates + a price-lookup callable +
the current ET timestamp, returns a JSON-serialisable result. Persisting the
proposed state — writing the updated gates file, appending a routine
receipt — is the responsibility of the L5 wrapper (so this module stays
fully testable without I/O).

Result shape::

    {
      "as_of": "<iso>",
      "evaluations": [
        {
          "gate_id": "...",
          "symbol": "QQQ",
          "current_state": "red_but_tested",
          "suggested_state": "green",
          "changed": true,
          "live_price": 707.4,
          "why": "price 707.4 above band 695-705 — confirm rule satisfied this session",
          "stamped_at": "<iso>",   # only when changed AND a writer is supplied
          "stamp_error": "...",    # only when the writer raised
        },
        ...
      ],
      "honesty": {
        "gates_loaded": int,
        "prices_missing": ["GATE-ID", ...],   # gates with no price → 'no evaluable price'
      },
    }

When ``writer`` is provided AND a state change is proposed, the routine calls
``writer(gates_after, evaluations)`` — the caller is responsible for the
actual file write + receipt append. The default writer is a no-op so unit
tests never touch disk.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import timing_engine as te

SRC = Path(__file__).resolve().parent
GATES_PATH = SRC / "timing_gates.json"


PriceFn = Callable[[str], "float | None"]
WriterFn = Callable[[list[dict[str, Any]], list[dict[str, Any]]], None]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _no_op_writer(gates_after: list[dict[str, Any]],
                  evaluations: list[dict[str, Any]]) -> None:
    del gates_after, evaluations  # tests never touch disk


def evaluate_all_gates(
    *,
    price_fn: PriceFn,
    gates: list[dict[str, Any]] | None = None,
    gates_path: Path | str = GATES_PATH,
    writer: WriterFn | None = None,
    as_of: str | None = None,
) -> dict[str, Any]:
    """Run :func:`timing_engine.evaluate_gate` on every gate.

    * ``gates`` — pre-loaded list; if None, the module reads
      ``timing_gates.json`` (honest absence: missing file raises
      :class:`timing_engine.GatesMissingError`).
    * ``price_fn(symbol)`` — caller-supplied. Returns the latest price for
      the symbol or ``None`` if no quote is available; the routine never
      fabricates a price.
    * ``writer`` — optional ``(gates_after, evaluations) -> None`` callback
      invoked ONLY when at least one gate's state changed. The default is a
      no-op writer; the L5 wrapper supplies one that updates
      ``timing_gates.json`` and appends a routine receipt.
    """
    as_of = as_of or _now_iso()
    if gates is None:
        gates = te.load_gates(gates_path)
    writer = writer or _no_op_writer

    evaluations: list[dict[str, Any]] = []
    prices_missing: list[str] = []
    gates_after: list[dict[str, Any]] = []
    any_change = False

    for gate in gates:
        gate_id = str(gate.get("gate_id") or gate.get("id") or "")
        symbol = str(gate.get("symbol") or "")
        current_state = gate.get("state")
        price = None
        if symbol:
            try:
                price = price_fn(symbol)
            except Exception:
                price = None
        if price is None and symbol:
            prices_missing.append(gate_id or symbol)

        result = te.evaluate_gate(gate, price)
        row = {
            "gate_id": gate_id,
            "symbol": symbol,
            "current_state": current_state,
            "suggested_state": result.get("suggested_state"),
            "changed": bool(result.get("changed")),
            "live_price": price,
            "why": result.get("why"),
        }

        next_gate = dict(gate)
        if row["changed"]:
            next_gate["state"] = row["suggested_state"]
            next_gate["last_evaluated_at"] = as_of
            row["stamped_at"] = as_of
            any_change = True
        gates_after.append(next_gate)
        evaluations.append(row)

    if any_change:
        try:
            writer(gates_after, evaluations)
        except Exception as exc:  # routine should not crash on a writer fault
            for row in evaluations:
                if row["changed"] and "stamp_error" not in row:
                    row["stamp_error"] = f"{type(exc).__name__}: {exc}"

    return {
        "as_of": as_of,
        "evaluations": evaluations,
        "gates_after": gates_after,
        "any_change": any_change,
        "honesty": {
            "gates_loaded": len(gates),
            "prices_missing": prices_missing,
        },
    }


def file_writer(gates_path: Path | str = GATES_PATH) -> WriterFn:
    """Convenience: a writer that rewrites ``timing_gates.json`` with the new
    gate states (preserving any other top-level keys in the file).

    Use from the L5 wrapper only — tests must stick to the default no-op
    writer to keep the suite hermetic.
    """
    path = Path(gates_path)

    def _writer(gates_after: list[dict[str, Any]], evaluations: list[dict[str, Any]]) -> None:
        del evaluations
        payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        payload["gates"] = gates_after
        payload["last_evaluated_at"] = _now_iso()
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    return _writer
