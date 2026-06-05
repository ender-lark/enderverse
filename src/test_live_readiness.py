import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import macro_pulse_scan as mp
from live_readiness import readiness_report


def _write(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


def _series(base, n=70):
    return [base + i for i in range(n)]


def _required_files(src):
    _write(src / "positions.json", {
        "snapshot_date": "2026-06-05",
        "sleeve_value": 100000,
        "positions": [
            {"ticker": "NVDA", "shares": 10, "market_value": 12000},
            {"ticker": "SMH", "shares": 5, "market_value": 8000},
        ],
    })
    _write(src / "theses.json", [
        {"ticker": "NVDA", "tier": "T2", "stance": "ACTIVE", "factor_tags": ["ai_complex"]},
        {"ticker": "SMH", "tier": "T2", "stance": "ACTIVE", "factor_tags": ["semiconductors"]},
    ])


def _market_files(src):
    for ticker, base in {
        "SMH": 100,
        "IGV": 200,
        "GRNY": 300,
        "IBIT": 400,
        "URA": 500,
        "REMX": 600,
        "XLF": 700,
        "GDX": 800,
        "VOLT": 900,
        "SPY": 1000,
    }.items():
        closes = json.loads((src / "uw_closes.json").read_text(encoding="utf-8")) if (src / "uw_closes.json").exists() else {}
        closes[ticker] = _series(base)
        _write(src / "uw_closes.json", closes)
    curve = mp.YieldCurveSnapshot(
        date="2026-06-05",
        yields={"2y": 4.00, "10y": 4.50, "30y": 5.00},
    )
    cross = mp.CrossAssetSnapshot(
        tlt_price=83.0,
        ief_price=93.0,
        lqd_price=107.0,
        hyg_price=79.0,
        uup_price=27.0,
        vix_level=18.0,
        gld_price=417.0,
        uso_price=148.0,
        move_index=95.0,
    )
    _write(src / "macro_state.json", mp.build_macro_state(
        curve,
        cross,
        mp.assemble_regime(curve, cross),
        mp.check_alerts(curve, cross),
    ))


def test_readiness_blocks_go_live_when_minimum_market_inputs_missing(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _required_files(src)

    report = readiness_report(
        src,
        run_timestamp="2026-06-05T14:00:00+00:00",
        generated_at="2026-06-05T14:00:00+00:00",
    )

    assert report["rehearsal_ready"] is True
    assert report["go_live_ready"] is False
    assert {row["key"] for row in report["missing_minimum_live_inputs"]} == {"macro", "uw_prices"}
    assert "uw_price" in report["dark_lane_keys"]
    assert "uw_macro" in report["dark_lane_keys"]


def test_readiness_go_live_ready_with_minimum_market_inputs(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _required_files(src)
    _market_files(src)

    report = readiness_report(
        src,
        run_timestamp="2026-06-05T14:00:00+00:00",
        generated_at="2026-06-05T14:00:00+00:00",
    )

    assert report["build_ready"] is True
    assert report["publish_ready"] is True
    assert report["live_data_ready"] is True
    assert report["go_live_ready"] is True
    assert report["missing_minimum_live_inputs"] == []


def test_readiness_cli_strict_returns_nonzero_when_not_ready(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _required_files(src)
    script = os.path.join(os.path.dirname(__file__), "live_readiness.py")

    proc = subprocess.run(
        [
            sys.executable,
            script,
            "--src-dir",
            str(src),
            "--run-timestamp",
            "2026-06-05T14:00:00+00:00",
            "--generated-at",
            "2026-06-05T14:00:00+00:00",
            "--strict",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 2
    assert json.loads(proc.stdout)["go_live_ready"] is False
