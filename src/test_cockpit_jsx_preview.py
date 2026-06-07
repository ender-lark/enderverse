import os
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
