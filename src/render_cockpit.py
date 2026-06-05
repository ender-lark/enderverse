#!/usr/bin/env python3
"""
render_cockpit.py  —  the in-session Cockpit read-path injector.

Takes the FEED JSON that the cloud routine already wrote to the
"🛰️ Cockpit Feed — Latest" Notion page, and slots it into the pinned
renderer (conviction_cockpit_v5.jsx) by a string-aware brace-matched
replace of the `const FEED = {...};` literal. Nothing else in the jsx
moves (the render never changes — only the data).

It is a PURE LOCAL TRANSFORM: no network, no credentials. The operator
copies the FEED block off the Notion page into this tool (file arg or
stdin); the tool validates, injects, validates again, writes the
artifact, and prints the freshness / dark-lane caveat line so the
session never hand-authors it.

Usage (the 3-call render):
    1) notion-fetch the Cockpit Feed — Latest page; copy the FEED JSON
    2) python3 render_cockpit.py feed.json        # or:  ... < feed.json
    3) present the written artifact

Self-test (P-SIMPLICITY runner-coverage):
    python3 render_cockpit.py --selftest

Exit codes:  0 ok · 2 feed parse failed · 3 renderer not found ·
             4 FEED anchor not found · 5 post-injection validation failed
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_TEMPLATE = str(HERE / "conviction_cockpit_v5.jsx")
DEFAULT_OUT = str(HERE / "rendered" / "conviction_cockpit_v5.jsx")

ANCHOR = "const FEED = {"
REQUIRED_EXPORT = "export default function ConvictionCockpit"


# ── seam 1: locate the FEED literal by true, string-aware brace matching ──
def find_feed_literal(src: str) -> tuple[int, int]:
    """Return (stmt_start, literal_end) bounding `const FEED = {...};`.

    literal_end is exclusive and includes the closing ';'. Brace chars and
    semicolons inside double/single-quoted strings are ignored, so a note
    value like "see {ticker}; etc" cannot fool the matcher.

    Raises ValueError if the anchor is missing, appears more than once, or
    the braces never balance.
    """
    n = src.count(ANCHOR)
    if n == 0:
        raise ValueError(
            f"FEED anchor not found: expected exactly one `{ANCHOR}` in the "
            f"renderer. The template's shape changed — re-check the pin."
        )
    if n > 1:
        raise ValueError(
            f"FEED anchor ambiguous: found `{ANCHOR}` {n} times; expected 1."
        )

    stmt_start = src.index(ANCHOR)
    i = src.index("{", stmt_start)  # the FEED object's opening brace
    depth = 0
    in_str = False
    str_ch = ""
    escaped = False
    end_brace = -1
    while i < len(src):
        c = src[i]
        if in_str:
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == str_ch:
                in_str = False
        else:
            if c == '"' or c == "'":
                in_str = True
                str_ch = c
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    end_brace = i
                    break
        i += 1
    if end_brace == -1:
        raise ValueError("FEED literal: braces never balanced (truncated template?).")

    # consume optional whitespace + the terminating ';'
    j = end_brace + 1
    while j < len(src) and src[j] in " \t\r\n":
        j += 1
    if j < len(src) and src[j] == ";":
        j += 1
    return stmt_start, j


# ── seam 2: parse / validate the incoming feed ──
def parse_feed(feed_text: str) -> dict:
    text = feed_text.strip()
    if not text:
        raise ValueError("empty feed: nothing on stdin / in the file.")
    try:
        feed = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"feed is not valid JSON (line {e.lineno}, col {e.colno}): {e.msg}. "
            f"Copy the FULL contents of the ```json block, braces included."
        ) from e
    if not isinstance(feed, dict):
        raise ValueError("feed parsed but is not a JSON object.")
    if "holdings" not in feed:
        raise ValueError("feed is missing 'holdings' — this isn't a cockpit FEED.")
    return feed


# ── the injection ──
def inject(feed_text: str, template_text: str) -> tuple[str, dict]:
    feed = parse_feed(feed_text)
    start, end = find_feed_literal(template_text)
    literal = "const FEED = " + json.dumps(feed, ensure_ascii=False) + ";"
    new_text = template_text[:start] + literal + template_text[end:]
    validate_output(new_text)
    return new_text, feed


# ── seam 3: post-injection structural validation (fail loud, never write garbage) ──
def validate_output(new_text: str) -> None:
    # (a) the injected literal must itself be a balanced `const FEED = {...};`
    find_feed_literal(new_text)  # raises if not
    # (b) whole-file brace regression check (only a balanced JSON obj was swapped)
    o, c = new_text.count("{"), new_text.count("}")
    if o != c:
        raise ValueError(f"post-injection brace imbalance: {{={o}, }}={c}.")
    # (c) the component must survive
    if REQUIRED_EXPORT not in new_text:
        raise ValueError("post-injection: component export missing.")
    # (d) the feed actually landed
    if '"generated_at"' not in new_text:
        raise ValueError("post-injection: injected feed has no generated_at.")


# ── the auto-caveat (so the session stops hand-writing freshness lines) ──
def _fmt_stamp(generated_at: str) -> str:
    if not generated_at:
        return "build stamp unknown"
    try:
        dt = datetime.fromisoformat(generated_at)
        off = dt.utcoffset()
        zone = "ET" if off is not None and off.total_seconds() in (-4 * 3600, -5 * 3600) else ""
        return f"{dt.strftime('%Y-%m-%d %H:%M')}{(' ' + zone) if zone else (' ' + generated_at[19:25] if len(generated_at) > 19 else '')}".rstrip()
    except (ValueError, TypeError):
        return generated_at


def build_caveat(feed: dict) -> str:
    parts = [f"built {_fmt_stamp(feed.get('generated_at', ''))}"]

    # curated / unwired lanes = empty in the feed → the jsx shows a curated stub
    curated = [k for k in ("catalysts", "questions") if not feed.get(k)]
    if curated:
        parts.append("curated/unwired lanes: " + ", ".join(curated))

    # engine lanes that are genuinely empty (engine ran, found nothing live)
    empty_engine = [k for k in ("actions", "fresh_signals") if not feed.get(k)]
    needs = (feed.get("hero", {}) or {}).get("needs_you", {}) or {}
    if not needs.get("count"):
        empty_engine.append("needs_you")
    if empty_engine:
        parts.append("empty engine lanes: " + ", ".join(empty_engine) + " (≠ all clear — see synthesis hanging)")

    # heartbeat: surface the dead-spots honestly
    hb = feed.get("heartbeat", []) or []
    down = [h.get("layer", "?") for h in hb if h.get("status") == "down"]
    stale = [h.get("layer", "?") for h in hb if h.get("status") == "stale"]
    if down:
        parts.append("heartbeat DOWN: " + ", ".join(down))
    if stale:
        parts.append("heartbeat STALE: " + ", ".join(stale))

    parts.append("prices as-of build, not live (say `refresh`)")
    return " · ".join(parts)


# ── self-test: round-trip the template's OWN golden FEED through the injector ──
def selftest(template_path: str) -> bool:
    try:
        with open(template_path, encoding="utf-8") as f:
            tpl = f.read()
    except OSError as e:
        print(f"SELFTEST FAIL — cannot read template {template_path}: {e}")
        return False
    try:
        start, end = find_feed_literal(tpl)
        golden_src = tpl[start + len("const FEED = "):end].rstrip().rstrip(";")
        golden = parse_feed(golden_src)
        new_text, reparsed = inject(json.dumps(golden, ensure_ascii=False), tpl)
        assert reparsed == golden, "golden FEED did not round-trip"
        # re-extract from the rebuilt file and confirm equality again
        s2, e2 = find_feed_literal(new_text)
        again = parse_feed(new_text[s2 + len("const FEED = "):e2].rstrip().rstrip(";"))
        assert again == golden, "re-extracted FEED differs from golden"
        validate_output(new_text)
        _ = build_caveat(golden)
    except (ValueError, AssertionError) as e:
        print(f"SELFTEST FAIL — {e}")
        return False
    print(f"SELFTEST PASS — golden FEED round-trips; output validates "
          f"({len(golden.get('holdings', []))} groups).")
    return True


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Inject a cockpit FEED into the pinned renderer.")
    p.add_argument("feed", nargs="?", help="path to the FEED JSON (omit to read stdin)")
    p.add_argument("--template", default=DEFAULT_TEMPLATE, help="pinned renderer .jsx")
    p.add_argument("--out", default=DEFAULT_OUT, help="artifact output path")
    p.add_argument("--selftest", action="store_true", help="round-trip the template's golden FEED and exit")
    args = p.parse_args(argv)

    if args.selftest:
        return 0 if selftest(args.template) else 1

    # read the template (missing → setup-gap flag, never a clone)
    try:
        with open(args.template, encoding="utf-8") as f:
            tpl = f.read()
    except OSError:
        print(f"RENDERER NOT FOUND at {args.template} — re-pin conviction_cockpit_v5.jsx "
              f"in project files (do NOT clone the repo for a render).")
        return 3

    feed_text = open(args.feed, encoding="utf-8").read() if args.feed else sys.stdin.read()

    try:
        new_text, feed = inject(feed_text, tpl)
    except ValueError as e:
        msg = str(e)
        code = 2 if ("JSON" in msg or "feed" in msg.lower()) and "anchor" not in msg else (
            4 if "anchor" in msg or "FEED literal" in msg else 5)
        print(f"RENDER ABORTED ({msg}) — no artifact written.")
        return code

    import os
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(new_text)

    print(f"RENDER READY · {args.out}")
    print(build_caveat(feed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
