import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from daily_synthesis_from_feed import build_synthesis_from_feed


def test_fundstrat_daily_line_prefers_latest_radar_rows():
    feed = {
        "generated_at": "2026-06-07T15:00:00+00:00",
        "lane_status": {"counts": {"has_data": 1, "not_checked": 0}, "rows": []},
        "actions": [],
        "radar": [
            {"ticker": "XOP", "direction": "avoid", "date": "2026-06-03", "source": "Fundstrat"},
            {"ticker": "RYF", "direction": "avoid", "date": "2026-06-03", "source": "Fundstrat"},
            {"ticker": "QQQ", "author": "Newton", "direction": "watch", "date": "2026-06-05"},
            {"ticker": "SOX", "author": "Newton", "direction": "watch", "date": "2026-06-05"},
            {"ticker": "RSP", "author": "Newton", "direction": "watch", "date": "2026-06-05"},
        ],
    }

    synthesis = build_synthesis_from_feed(feed, as_of="2026-06-07")

    assert "Latest Fundstrat Daily compact calls in radar: QQQ watch, SOX watch, RSP watch." in synthesis["delta"]
    assert "XOP avoid" not in synthesis["delta"]
