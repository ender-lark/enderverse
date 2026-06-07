import json
from pathlib import Path

from feed_assembler import assemble_feed
from full_build_runner import build_full_feed_from_files
from validators import validate_cockpit_feed


HERE = Path(__file__).resolve().parent
CLASSIFICATION = HERE.parent / "docs" / "dashboard_feed_block_classification.json"
SUMMARY_RENDERED_BLOCKS = {
    "action_decision_groups",
    "alert_policy",
    "asymmetric_opportunities",
    "fresh_signals",
    "market_open_packet",
    "portfolio_views",
    "reallocation_brief",
    "research_actions",
    "signal_log",
    "social_watch",
    "source_audits",
    "uw_action_runbook",
    "uw_endpoint_proof",
}


def _write(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


def _series(base, n=70):
    return [base + i for i in range(n)]


def _build_src_with_account_positions(src):
    _write(src / "positions.json", {
        "snapshot_date": "2026-06-04",
        "sleeve_value": 100000,
        "positions": [
            {"ticker": "NVDA", "shares": 10, "market_value": 12000, "account": "SKB"},
            {"ticker": "SMH", "shares": 5, "market_value": 8000, "account": "IRA"},
        ],
    })
    _write(src / "account_positions.json", {
        "snapshot_date": "2026-06-04",
        "sleeve_value": 100000,
        "account_positions": [
            {
                "ticker": "NVDA",
                "description": "NVIDIA",
                "shares": 10,
                "market_value": 12000,
                "account": "Taxable",
                "owner": "SKB",
                "broker": "Fidelity",
                "tracked": True,
            },
            {
                "ticker": "SMH",
                "description": "Semis ETF",
                "shares": 5,
                "market_value": 8000,
                "account": "IRA",
                "owner": "Parents",
                "broker": "Schwab",
                "tracked": True,
            },
        ],
    })
    _write(src / "theses.json", [
        {"ticker": "NVDA", "tier": "T2", "stance": "ACTIVE", "factor_tags": ["ai_complex"]},
        {"ticker": "SMH", "tier": "T2", "stance": "ACTIVE", "factor_tags": ["semiconductors"]},
    ])
    _write(src / "uw_closes.json", {"SMH": _series(400), "SPY": _series(600)})


def _current_emitted_feed_keys(tmp_path):
    with (HERE / "golden_snapshot.json").open(encoding="utf-8") as fh:
        golden = json.load(fh)
    assembled = assemble_feed(golden, parabolic={"MU"})
    assert validate_cockpit_feed(assembled) == []

    src = tmp_path / "src"
    src.mkdir()
    _build_src_with_account_positions(src)
    full = build_full_feed_from_files(
        src_dir=src,
        as_of="2026-06-05",
        run_timestamp="2026-06-05T14:00:00+00:00",
    )
    assert validate_cockpit_feed(full) == []

    return set(assembled) | set(full)


def test_every_emitted_dashboard_feed_block_is_classified(tmp_path):
    payload = json.loads(CLASSIFICATION.read_text(encoding="utf-8"))
    blocks = payload["blocks"]
    allowed = set(payload["allowed_primary_statuses"])

    missing = sorted(_current_emitted_feed_keys(tmp_path) - set(blocks))
    assert missing == [], (
        "New dashboard feed block(s) need docs/dashboard_feed_block_classification.json "
        f"classification before UI/export work: {missing}"
    )

    bad_status = {
        key: row.get("primary_status")
        for key, row in blocks.items()
        if row.get("primary_status") not in allowed
    }
    assert bad_status == {}


def test_classification_names_canonical_dashboard_path():
    payload = json.loads(CLASSIFICATION.read_text(encoding="utf-8"))
    canonical = payload["canonical_dashboard"]

    assert canonical["renderer"] == "src/conviction_cockpit_v5.jsx"
    assert canonical["injector"] == "src/render_cockpit.py"
    assert "docs/index.html" in canonical["summary_export"]


def test_summary_rendered_blocks_are_not_documented_as_hidden():
    payload = json.loads(CLASSIFICATION.read_text(encoding="utf-8"))
    blocks = payload["blocks"]

    problems = {
        key: (blocks.get(key) or {}).get("summary_surface", "")
        for key in sorted(SUMMARY_RENDERED_BLOCKS)
        if "not rendered" in (blocks.get(key) or {}).get("summary_surface", "").lower()
    }

    assert problems == {}
