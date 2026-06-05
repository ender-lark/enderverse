from pathlib import Path


ROOT = Path(__file__).resolve().parent
CANONICAL = ROOT / "conviction_cockpit_v5.jsx"
RENDERED = ROOT / "rendered" / "conviction_cockpit_v5.jsx"


def test_canonical_cockpit_surfaces_operator_status():
    text = CANONICAL.read_text(encoding="utf-8")

    assert "function operatorStatus(feed)" in text
    assert "Operator status" in text
    assert "Today actions" in text
    assert "Open reviews" in text
    assert "Source lanes" in text
    assert "python src/go_live_checklist.py --format text" in text


def test_rendered_cockpit_keeps_operator_status_card():
    text = RENDERED.read_text(encoding="utf-8")

    assert "Operator status" in text
    assert "Open reviews" in text
    assert "Source lanes" in text
    assert "python src/go_live_checklist.py --format text" in text
