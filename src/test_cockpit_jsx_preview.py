import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cockpit_jsx_preview import html_source, runtime_source


def test_runtime_source_mounts_canonical_cockpit_with_cdn_react():
    src = '''import React, { useEffect, useState, useMemo } from "react";
export default function ConvictionCockpit() {
  return <div>ok</div>;
}
'''

    out = runtime_source(src)

    assert "useEffect" in out
    assert "https://esm.sh/react@18.3.1" in out
    assert "https://esm.sh/react-dom@18.3.1/client" in out
    assert 'createRoot(rootEl).render(<ConvictionCockpit />);' in out


def test_html_source_points_to_jsx_preview_bundle():
    out = html_source("preview.js")

    assert '<div id="root"></div>' in out
    assert 'import("./preview.js?v=" + Date.now());' in out


def test_canonical_jsx_has_current_commands_tab():
    src = (Path(__file__).resolve().parent / "conviction_cockpit_v5.jsx").read_text(encoding="utf-8")

    assert '["commands","Commands"]' in src
    assert "python src/live_dashboard_refresh.py" in src
    assert "python src/alert_policy.py --feed src/latest_cockpit_feed.json --format text" in src
    assert "Social Watch remains queued/dark" in src


def test_canonical_jsx_has_fundstrat_news_tab_and_if_i_were_you():
    src = (Path(__file__).resolve().parent / "conviction_cockpit_v5.jsx").read_text(encoding="utf-8")

    assert '["news","News"]' in src
    assert 'id="fundstrat-news"' in src
    assert "Monthly Bible / Allocation" in src
    assert "Top 5 SMID is not captured" in src
    assert "Bottom 5 SMID" in src
    assert "If I Were You" in src


def test_canonical_jsx_has_source_conflicts_section():
    src = (Path(__file__).resolve().parent / "conviction_cockpit_v5.jsx").read_text(encoding="utf-8")

    assert 'id="source-conflicts"' in src
    assert "Source conflicts" in src
    assert "No current bull/bear source splits" in src


def test_canonical_jsx_book_labels_allocation_guidance():
    src = (Path(__file__).resolve().parent / "conviction_cockpit_v5.jsx").read_text(encoding="utf-8")

    assert "Allocation guide: working model target + Fundstrat cue" in src
    assert "model target" in src
    assert "Fundstrat {String(c.fundstrat_cue" in src


def test_canonical_jsx_hero_uses_packet_attention_state():
    src = (Path(__file__).resolve().parent / "conviction_cockpit_v5.jsx").read_text(encoding="utf-8")

    assert "function heroAttention(h, packet, op)" in src
    assert "blocked by named evidence checks" in src
    assert "available checks already ran for this build" in src
    assert "No decisions need attention" in src


def test_canonical_jsx_promotes_time_sensitive_ideas_into_today_stack():
    src = (Path(__file__).resolve().parent / "conviction_cockpit_v5.jsx").read_text(encoding="utf-8")

    assert '["action","Today"]' in src
    assert '["reallocation","Reallocation"]' in src
    assert "function todayPriorityRows(feed, actions, researchActions)" in src
    assert "function TodayDecisionQueue" in src
    assert "function TodayActionCard" in src
    assert "function DecisionLaneBoard" in src
    assert 'id="today-decisions"' in src
    assert "Decision-first queue; only items that can change a near-term act" in src
    assert "Ready to Decide" in src
    assert "Evidence Missing" in src
    assert "Decision lane board" in src
    assert "Today sub-category" not in src
    assert "The boxes below are sub-categories inside Today Decisions" not in src
    assert "Needed evidence:" in src
    assert "Confidence basis:" in src
    assert "Plain-English read:" in src
    assert "Why conviction:" in src
    assert "hidden decision metadata" in src
    assert "System data gap:" in src
    assert "System proof:" in src
    assert "Full book + per-name detail lives in Book." in src


def test_canonical_jsx_sections_start_as_summary_boxes():
    src = (Path(__file__).resolve().parent / "conviction_cockpit_v5.jsx").read_text(encoding="utf-8")

    assert "const SECTION_DESCRIPTIONS" in src
    assert "Decision-first queue; only items that can change a near-term act" in src
    assert "function Section({ id, title, icon, badge, badgeColor, summary, description, children, openMap, setOpen, defaultOpen=false })" in src
    assert 'Category summary and expandable backup detail.' in src
    assert "expand" in src and "hide" in src
    assert 'convictionCockpit.openSections.v4' in src
    assert 'id="today-decisions"' in src and 'defaultOpen={true}' in src


def test_canonical_jsx_has_ideas_and_ops_tab_homes():
    src = (Path(__file__).resolve().parent / "conviction_cockpit_v5.jsx").read_text(encoding="utf-8")

    assert '["ideas","Ideas"]' in src
    assert '["ops","Ops"]' in src
    assert '{mode==="ideas" && (<>' in src
    assert '{mode==="ops" && (<>' in src
    assert 'id="top-prospects"' in src
    assert 'id="asymmetric-opportunities"' in src
    assert 'id="bullish-flow"' in src
    assert 'id="radar"' in src
    assert 'id="source-audits"' in src
    assert 'id="feedback"' in src
    assert 'id="social-watch"' in src


def test_canonical_jsx_routes_major_sections_to_their_tab_homes():
    src = (Path(__file__).resolve().parent / "conviction_cockpit_v5.jsx").read_text(encoding="utf-8")

    expected = {
        "action": ["source-conflicts"],
        "reallocation": ["reallocation-brief", "target-drift"],
        "ideas": ["top-prospects", "asymmetric-opportunities", "research-actions", "fresh-signals", "bullish-flow", "radar", "research"],
        "news": ["fundstrat-news", "synthesis", "market", "cats"],
        "ops": ["uw-action-runbook", "source-audits", "feedback", "signal-log", "questions", "social-watch"],
    }

    assert re.search(r'\{mode==="action" && .*?<TodayDecisionQueue', src, flags=re.S)
    assert 'id="today-decisions"' in src
    for mode, section_ids in expected.items():
        for section_id in section_ids:
            pattern = rf'\{{mode==="{mode}" && .*?id="{re.escape(section_id)}"'
            assert re.search(pattern, src, flags=re.S), f"{section_id} should be rendered from {mode} tab"
