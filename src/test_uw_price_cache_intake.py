import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uw_price_cache_intake as intake
from full_build_runner import build_full_feed_from_files


def _fake_response(closes):
    data = [
        {"date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", "c": close}
        for i, close in enumerate(closes)
    ]
    return {"data": list(reversed(data))}


def _payload(tickers=None, n=70):
    tickers = tickers or intake.UW_ROTATION_TICKERS
    return {
        ticker: _fake_response([100 + idx + i * 0.1 for i in range(n)])
        for idx, ticker in enumerate(tickers)
    }


def _required_full_build_files(src):
    (src / "positions.json").write_text(json.dumps({
        "snapshot_date": "2026-06-04",
        "sleeve_value": 100000,
        "positions": [{"ticker": "SMH", "shares": 5, "market_value": 8000}],
    }), encoding="utf-8")
    (src / "theses.json").write_text(json.dumps([
        {"ticker": "SMH", "tier": "T2", "stance": "ACTIVE", "factor_tags": ["semiconductors"]},
    ]), encoding="utf-8")


def test_normalize_price_cache_accepts_wrapped_uw_responses_and_sorts():
    cache = intake.normalize_price_cache([{"responses_by_ticker": {"SMH": _fake_response([1, 2, 3])}}])

    assert cache["SMH"] == [1.0, 2.0, 3.0]


def test_validate_price_cache_requires_default_rotation_tickers_and_depth():
    cache = intake.normalize_price_cache([_payload(tickers=["SMH"], n=10)])

    summary = intake.validate_price_cache(cache)

    assert summary["valid"] is False
    assert "SPY" in summary["missing_tickers"]
    assert summary["too_short"]["SMH"] == 10


def test_cli_writes_valid_cache_and_summary(tmp_path):
    input_path = tmp_path / "responses.json"
    out = tmp_path / "uw_closes.json"
    summary = tmp_path / "summary.json"
    input_path.write_text(json.dumps({"responses": _payload()}), encoding="utf-8")
    script = os.path.join(os.path.dirname(__file__), "uw_price_cache_intake.py")

    proc = subprocess.run(
        [sys.executable, script, str(input_path), "--out", str(out), "--summary", str(summary)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["valid"] is True
    assert payload["written"] is True
    assert out.is_file()
    assert summary.is_file()
    written = json.loads(out.read_text(encoding="utf-8"))
    assert set(intake.UW_ROTATION_TICKERS) <= set(written)


def test_cli_rejects_incomplete_cache_without_overwriting_out(tmp_path):
    input_path = tmp_path / "responses.json"
    out = tmp_path / "uw_closes.json"
    summary = tmp_path / "summary.json"
    input_path.write_text(json.dumps({"responses": _payload(tickers=["SMH"], n=70)}), encoding="utf-8")
    script = os.path.join(os.path.dirname(__file__), "uw_price_cache_intake.py")

    proc = subprocess.run(
        [sys.executable, script, str(input_path), "--out", str(out), "--summary", str(summary)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 2
    assert not out.exists()
    payload = json.loads(summary.read_text(encoding="utf-8"))
    assert payload["written"] is False
    assert "SPY" in payload["missing_tickers"]


def test_validate_missing_cache_returns_json_failure(tmp_path):
    missing = tmp_path / "missing.json"
    script = os.path.join(os.path.dirname(__file__), "uw_price_cache_intake.py")

    proc = subprocess.run(
        [sys.executable, script, "--validate", str(missing)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 2
    payload = json.loads(proc.stdout)
    assert payload["valid"] is False
    assert payload["problems"] == ["cache file not found"]


def test_valid_cache_feeds_full_build_price_lane(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _required_full_build_files(src)
    (src / "uw_closes.json").write_text(json.dumps(
        intake.normalize_price_cache([_payload()])
    ), encoding="utf-8")

    feed = build_full_feed_from_files(
        src_dir=src,
        as_of="2026-06-05",
        run_timestamp="2026-06-05T14:00:00+00:00",
    )

    rows = {row["key"]: row for row in feed["lane_status"]["rows"]}
    assert rows["uw_price"]["status"] == "has_data"
    assert feed["rotation"]
