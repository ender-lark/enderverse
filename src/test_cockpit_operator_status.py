from pathlib import Path


ROOT = Path(__file__).resolve().parent
CANONICAL = ROOT / "conviction_cockpit_v5.jsx"
RENDERED = ROOT / "rendered" / "conviction_cockpit_v5.jsx"


def test_canonical_cockpit_surfaces_operator_status():
    text = CANONICAL.read_text(encoding="utf-8")

    assert "function operatorStatus(feed)" in text
    assert "Operator status" not in text
    assert "function SystemCriticalBanner" in text
    assert "System data gap:" in text
    assert "open System" in text
    assert "Today Decisions" in text
    assert "openReviewPressure" in text
    assert "openReviewValue" in text
    assert "Cloud routine failed:" in text
    assert "Source Proof And Writebacks" in text
    assert "Active event watch" not in text
    assert "Today focus" not in text
    assert "Evidence Missing" in text
    assert "needs evidence" not in text
    assert "System proof:" in text
    assert "python src/go_live_checklist.py --format text" in text
    assert "python src/sudden_event_refresh.py --title" in text
    assert "DEFERRED_OPTIONAL_SOURCE_KEYS" in text
    assert "deferredDarkRows" in text
    assert "sourceLaneWarning" in text
    assert '`${deferredDark} deferred`' in text


def test_rendered_cockpit_keeps_operator_status_card():
    text = RENDERED.read_text(encoding="utf-8")

    assert "Operator status" not in text
    assert "System data gap:" in text
    assert "Today Decisions" in text
    assert "Cloud routine failed:" in text
    assert "Source Proof And Writebacks" in text
    assert "Active event watch" not in text
    assert "Today focus" not in text
    assert "Evidence Missing" in text
    assert "needs evidence" not in text
    assert "System proof:" in text
    assert "python src/go_live_checklist.py --format text" in text
    assert "python src/sudden_event_refresh.py --title" in text
