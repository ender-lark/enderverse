"""Tests for the options-chain acquisition module (pure assembly + cache write)."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import options_chain_refresh as ocr  # noqa: E402


def test_self_test_passes():
    assert ocr._self_test() == 0


def test_select_universe_excludes_no_add_dedups_and_caps():
    theses = [
        {"ticker": "nvda", "stance": "ACTIVE"},
        {"ticker": "MU", "stance": "MONITOR"},      # no-add -> excluded by default
        {"ticker": "AVGO", "stance": "ACTIVE"},
        {"ticker": "NVDA", "stance": "ACTIVE"},     # dup
        {"stance": "ACTIVE"},                        # no ticker -> skipped
    ]
    uni = ocr.select_universe(theses, extra=["leu", "AVGO", ""], cap=10)
    assert uni == ["NVDA", "AVGO", "LEU"]            # uppercased, deduped, no-add dropped, extra appended
    # cap respected, theses win the cap over extra
    assert ocr.select_universe(theses, extra=["LEU"], cap=1) == ["NVDA"]
    # opt-in to include a no-add sleeve for awareness pulls
    assert "MU" in ocr.select_universe(theses, include_no_add=True)


def test_target_expiry_snaps_to_monthly_opex():
    # get_options_chain returns empty for a non-expiration date, so target_expiry must land on a
    # real standard monthly expiration (3rd Friday) of the month ~dte days out.
    assert ocr.target_expiry("2026-06-18", dte=45) == "2026-08-21"   # Aug 3rd Friday
    assert ocr.target_expiry("2026-06-18", dte=30) == "2026-07-17"   # Jul 3rd Friday
    # all results are Fridays
    import datetime as _dt
    for dte in (20, 45, 75, 120):
        d = _dt.datetime.strptime(ocr.target_expiry("2026-06-18", dte=dte), "%Y-%m-%d")
        assert d.weekday() == 4 and 15 <= d.day <= 21


def test_assemble_bundle_keeps_usable_drops_empty_and_never_raises():
    responses = {
        "NVDA": {"screener": {"result": [{"close": "10"}]}, "chain": {"states": [{"strike": "10"}]}},
        "zzz": {"screener": 5, "chain": None},          # no usable payload -> dropped
        "AAA": {"chain": {"states": []}},               # chain present (empty list is still a list)
        "_meta": {"x": 1},                              # bookkeeping key -> dropped
        "bad": [1, 2, 3],                               # non-dict entry -> dropped
    }
    b = ocr.assemble_bundle(responses)
    assert set(b) == {"NVDA", "AAA"}
    assert b["NVDA"]["screener"] and b["NVDA"]["chain"]
    assert "screener" not in b["AAA"] and "chain" in b["AAA"]
    # wrapper unwrapping + junk inputs degrade to empty, never raise
    assert ocr.assemble_bundle({"responses": {"MU": {"chain": {"states": [{"strike": 1}]}}}}) == {"MU": {"chain": {"states": [{"strike": 1}]}}}
    assert ocr.assemble_bundle([1, 2, 3]) == {} and ocr.assemble_bundle(None) == {}


def test_build_cache_wraps_meta_and_strips_cleanly():
    bundle = {"NVDA": {"screener": {"result": [{}]}}}
    cache = ocr.build_cache(bundle, as_of="2026-06-18", generated_at="x", expiry_target="2026-08-02")
    assert cache["_meta"]["count"] == 1
    assert cache["_meta"]["tickers"] == ["NVDA"]
    assert cache["_meta"]["expiry_target"] == "2026-08-02"
    assert "NVDA" in cache
    # the build path's coercion drops _meta back out to a clean bundle
    from full_build_runner import options_bundle_from_cache
    assert options_bundle_from_cache(cache) == bundle


def test_refresh_from_responses_writes_atomic_cache_with_summary(tmp_path):
    raw = {
        "NVDA": {"screener": {"result": [{"close": "10"}]}, "chain": {"states": [{"strike": "10"}]}},
        "ZZZ": {"screener": 5},                          # dropped
    }
    out = tmp_path / "options_chain_cache.json"
    summary = ocr.refresh_from_responses(raw, out=out, as_of="2026-06-18", generated_at="x")
    assert summary["count"] == 1 and summary["tickers"] == ["NVDA"]
    written = json.loads(out.read_text(encoding="utf-8"))
    assert "NVDA" in written and written["_meta"]["count"] == 1
    assert not (tmp_path / "options_chain_cache.json.tmp").exists()   # atomic: tmp cleaned up


def test_cli_from_responses_roundtrip(tmp_path):
    raw = tmp_path / "raw.json"
    raw.write_text(json.dumps({"NVDA": {"chain": {"states": [{"strike": 1}]}}}), encoding="utf-8")
    out = tmp_path / "cache.json"
    rc = ocr.main(["--from-responses", str(raw), "--out", str(out), "--as-of", "2026-06-18",
                   "--generated-at", "x", "--expiry", "2026-08-02"])
    assert rc == 0
    cache = json.loads(out.read_text(encoding="utf-8"))
    assert "NVDA" in cache and cache["_meta"]["expiry_target"] == "2026-08-02"
