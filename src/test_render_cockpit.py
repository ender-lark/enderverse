"""Seam tests for render_cockpit.py (the Cockpit read-path injector)."""
import json
import os

import pytest

import render_cockpit as rc

TEMPLATE = os.environ.get("COCKPIT_TEMPLATE", "/mnt/project/conviction_cockpit_v5.jsx")

# Skip the pinned-template tests when the renderer file is not provisioned in this
# env (it lives at /mnt/project on the read-path). Set COCKPIT_TEMPLATE to run them.
requires_template = pytest.mark.skipif(
    not os.path.exists(TEMPLATE),
    reason="pinned renderer not present in this env; set COCKPIT_TEMPLATE to run",
)


# ── T1: the brace-matcher must survive { } ; inside string VALUES ──
def test_brace_matcher_ignores_braces_and_semicolons_inside_strings():
    pre = "import x\nconst C = { a: 1 };\n"
    # FEED whose string values contain literal { } ; and an escaped quote
    feed_obj = {"note": 'see {ticker}; \\"q\\" end', "nested": {"c": 1}, "holdings": []}
    feed_src = json.dumps(feed_obj, ensure_ascii=False)
    post = "\n// seam\nexport default function ConvictionCockpit(){return null}\n"
    src = pre + "const FEED = " + feed_src + ";" + post

    start, end = rc.find_feed_literal(src)
    assert src[:start] == pre
    assert src[end:] == post
    extracted = rc.parse_feed(src[start + len("const FEED = "):end].rstrip().rstrip(";"))
    assert extracted == feed_obj


def test_anchor_missing_and_ambiguous_raise():
    with pytest.raises(ValueError):
        rc.find_feed_literal("no anchor here")
    dup = "const FEED = {};\nconst FEED = {};\n"
    with pytest.raises(ValueError):
        rc.find_feed_literal(dup)


# ── T2: the parse gate must fail loud on bad / non-cockpit input ──
def test_parse_feed_rejects_malformed_and_non_object_and_non_feed():
    with pytest.raises(ValueError):
        rc.parse_feed("{not valid json,,,}")
    with pytest.raises(ValueError):
        rc.parse_feed("[]")              # valid JSON, wrong type
    with pytest.raises(ValueError):
        rc.parse_feed("")               # empty
    with pytest.raises(ValueError):
        rc.parse_feed('{"generated_at": "x"}')  # object but no holdings


@requires_template
def test_inject_aborts_on_bad_feed_without_writing():
    tpl = open(TEMPLATE, encoding="utf-8").read()
    with pytest.raises(ValueError):
        rc.inject("{broken", tpl)


# ── T3: golden-master — injecting the template's OWN FEED reproduces a valid file ──
@requires_template
def test_golden_master_roundtrip_against_pinned_template():
    tpl = open(TEMPLATE, encoding="utf-8").read()
    start, end = rc.find_feed_literal(tpl)
    golden = rc.parse_feed(tpl[start + len("const FEED = "):end].rstrip().rstrip(";"))
    new_text, reparsed = rc.inject(json.dumps(golden, ensure_ascii=False), tpl)
    assert reparsed == golden
    rc.validate_output(new_text)                 # raises if structurally broken
    assert rc.REQUIRED_EXPORT in new_text
    # FEED re-extracted from the rebuilt file equals the golden object
    s2, e2 = rc.find_feed_literal(new_text)
    again = rc.parse_feed(new_text[s2 + len("const FEED = "):e2].rstrip().rstrip(";"))
    assert again == golden


@requires_template
def test_selftest_helper_passes_on_pinned_template():
    assert rc.selftest(TEMPLATE) is True


# ── T4: end-to-end with a fake live feed → valid output + a useful caveat line ──
@requires_template
def test_end_to_end_fake_feed_and_caveat():
    tpl = open(TEMPLATE, encoding="utf-8").read()
    fake = {
        "generated_at": "2026-06-01T20:17:26.884999-04:00",
        "actions": [], "fresh_signals": [], "catalysts": [], "questions": [],
        "hero": {"needs_you": {"count": 0, "items": []}},
        "heartbeat": [
            {"layer": "Parabolic Cache", "status": "down"},
            {"layer": "Macro cache", "status": "stale"},
            {"layer": "Daily Synthesis", "status": "ok"},
        ],
        "holdings": [{"cat": "AI", "rot": {"w": "LEADING"},
                      "pos": [{"t": "NVDA", "pct": 6.5}]}],
    }
    new_text, feed = rc.inject(json.dumps(fake, ensure_ascii=False), tpl)
    rc.validate_output(new_text)
    cav = rc.build_caveat(feed)
    assert "2026-06-01 20:17 ET" in cav
    assert "refresh" in cav
    assert "Parabolic Cache" in cav and "Macro cache" in cav
    assert "Daily Synthesis" not in cav        # ok layers are not surfaced
    assert "catalysts" in cav and "questions" in cav   # curated lanes flagged


def test_caveat_is_windows_console_safe():
    feed = {
        "generated_at": "2026-06-01T20:17:26-04:00",
        "actions": [],
        "fresh_signals": [],
        "catalysts": [],
        "questions": [],
        "hero": {"needs_you": {"count": 0, "items": []}},
        "heartbeat": [{"layer": "Optional Source Lanes", "status": "stale"}],
        "holdings": [],
    }
    rc.build_caveat(feed).encode("cp1252")


@requires_template
def test_main_stdin_writes_artifact(tmp_path, monkeypatch, capsys):
    out = tmp_path / "cockpit.jsx"
    fake = {"generated_at": "2026-06-01T20:17:26-04:00",
            "holdings": [{"cat": "X", "rot": {"w": ""}, "pos": [{"t": "AAA", "pct": 1.0}]}],
            "heartbeat": []}
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(json.dumps(fake)))
    code = rc.main(["--template", TEMPLATE, "--out", str(out)])
    assert code == 0
    assert out.exists()
    rc.validate_output(out.read_text(encoding="utf-8"))
    assert "RENDER READY" in capsys.readouterr().out
