import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fundstrat_web_intake import normalize_web_compact_rows, write_web_outputs


def test_accepts_flashinsights_feed_full_card_rows(tmp_path):
    payload = {
        "items": [{
            "source_surface": "flashinsights_feed",
            "full_content_basis": "complete FlashInsights feed card visible in logged-in Chrome",
            "author": "Mark L. Newton, CMT",
            "ticker": "QQQ",
            "direction": "avoid",
            "quote": "Premature to buy Tech dips while QQQ tests 675-679 and rotation out of Tech develops.",
            "date": "2026-06-09",
            "subject": "FlashInsights: QQQ support risk",
            "source_url": "https://fundstratdirect.com/members/flashinsights/",
        }]
    }

    calls, suppressed, problems = normalize_web_compact_rows(payload)
    assert problems == []
    assert suppressed == []
    assert calls[0]["ticker"] == "QQQ"
    assert calls[0]["source"] == "Fundstrat Chrome FlashInsights feed"

    write_web_outputs(calls, tmp_path, generated_at="2026-06-09T20:20:00+00:00")
    summary = json.loads((tmp_path / "fundstrat_intake_summary.json").read_text(encoding="utf-8"))
    assert summary["web_compact_intake"]["source"] == "authenticated_fundstrat_chrome"
    assert summary["web_compact_intake"]["raw_bodies_stored"] is False


def test_article_listing_is_discovery_only():
    calls, suppressed, problems = normalize_web_compact_rows({
        "items": [{
            "source_surface": "article_listing",
            "full_content_basis": "listing card only",
            "ticker": "SPY",
            "quote": "Generic listing teaser with no detail page.",
            "date": "2026-06-09",
        }]
    })

    assert calls == []
    assert problems == []
    assert suppressed[0]["source_surface"] == "article_listing"
    assert "discovery-only" in suppressed[0]["reason"]


def test_article_detail_requires_detail_page_basis():
    calls, suppressed, problems = normalize_web_compact_rows({
        "items": [{
            "source_surface": "article_detail",
            "full_content_basis": "listing card visible in Chrome",
            "ticker": "SPY",
            "quote": "Re-check risk if SPY loses support near 730.",
            "date": "2026-06-09",
        }]
    })

    assert calls == []
    assert suppressed == []
    assert any("detail-page evidence" in problem for problem in problems)


def test_article_detail_accepts_compact_detail_page_rows():
    calls, suppressed, problems = normalize_web_compact_rows({
        "items": [{
            "source_surface": "article_detail",
            "full_content_basis": "article detail page text visible in logged-in Chrome",
            "author": "Tom Lee",
            "ticker": "SPY",
            "direction": "watch",
            "quote": "Risk-on stance stays intact only if SPY holds support and breadth confirms over the next 1-2 weeks.",
            "date": "2026-06-09",
            "subject": "First Word detail-page compact row",
        }]
    })

    assert problems == []
    assert suppressed == []
    assert calls[0]["source"] == "Fundstrat Chrome article detail page"


def test_rejects_raw_article_body_fields():
    calls, suppressed, problems = normalize_web_compact_rows({
        "items": [{
            "source_surface": "article_detail",
            "full_content_basis": "article detail page text visible in logged-in Chrome",
            "ticker": "SPY",
            "quote": "Support check near 730.",
            "date": "2026-06-09",
            "article_text": "raw article body must not be stored",
        }]
    })

    assert calls == []
    assert suppressed == []
    assert any("raw text fields" in problem for problem in problems)


def test_video_only_is_discovery_but_transcript_is_allowed():
    video_only = normalize_web_compact_rows({
        "items": [{
            "source_surface": "video_only",
            "full_content_basis": "video title visible only",
            "ticker": "SPY",
            "quote": "Video title only.",
            "date": "2026-06-09",
        }]
    })
    assert video_only[0] == []
    assert video_only[2] == []
    assert video_only[1][0]["source_surface"] == "video_only"

    calls, suppressed, problems = normalize_web_compact_rows({
        "items": [{
            "source_surface": "video_transcript",
            "full_content_basis": "visible transcript text on logged-in video page",
            "author": "Tom Lee",
            "ticker": "QQQ",
            "direction": "watch",
            "video_title": "Macro Minute: Breadth confirmation",
            "source_url": "https://fundstratdirect.com/members/video/example/",
            "directional_bias": "Constructive if breadth confirms.",
            "key_levels": "QQQ support must hold.",
            "timing_horizon": "This week.",
            "change_vs_prior": "No explicit prior shift stated.",
            "action_implication": "Re-check before adding AI/tech exposure.",
            "quote": "Transcript says to wait for breadth confirmation before adding QQQ exposure this week.",
            "date": "2026-06-09",
        }]
    })
    assert problems == []
    assert suppressed == []
    assert calls[0]["source"] == "Fundstrat Chrome video transcript"


def test_video_transcript_requires_compact_proof_fields_without_raw_transcript():
    calls, suppressed, problems = normalize_web_compact_rows({
        "items": [{
            "source_surface": "video_transcript",
            "full_content_basis": "visible transcript text on logged-in video page",
            "author": "Mark L. Newton, CMT",
            "ticker": "QQQ",
            "direction": "watch",
            "video_title": "Daily Technical Strategy video",
            "source_url": "https://fundstratdirect.com/members/video/example/",
            "directional_bias": "Higher if support holds.",
            "key_levels": "QQQ support 520; upside confirmation above 530.",
            "timing_horizon": "Tactical, next 1-2 weeks.",
            "action_implication": "Re-check AI/tech exposure before adding.",
            "quote": "Transcript-derived compact row with levels and re-check implication.",
            "date": "2026-06-15",
        }]
    })

    assert calls == []
    assert suppressed == []
    assert any("change_vs_prior" in problem for problem in problems)

    calls, suppressed, problems = normalize_web_compact_rows({
        "items": [{
            "source_surface": "video_transcript",
            "full_content_basis": "visible transcript text on logged-in video page",
            "author": "Mark L. Newton, CMT",
            "ticker": "QQQ",
            "direction": "watch",
            "video_title": "Daily Technical Strategy video",
            "source_url": "https://fundstratdirect.com/members/video/example/",
            "directional_bias": "Higher if support holds.",
            "key_levels": "QQQ support 520; upside confirmation above 530.",
            "timing_horizon": "Tactical, next 1-2 weeks.",
            "change_vs_prior": "Shifted from caution to constructive above support.",
            "action_implication": "Re-check AI/tech exposure before adding.",
            "names_sectors": "QQQ, semiconductors, AI beta.",
            "portfolio_implication": "Do not add until support/confirmation holds.",
            "confirmation_needed": "Breadth confirmation and QQQ support hold.",
            "blocker_before_action": "No action while confirmation is missing.",
            "suggested_next_check": "Next regular technical update.",
            "date": "2026-06-15",
        }]
    })

    assert problems == []
    assert suppressed == []
    assert calls[0]["ticker"] == "QQQ"
    assert "Shifted from caution" in calls[0]["quote"]
    assert len(calls[0]["quote"]) <= 320
    assert calls[0]["evidence_detail"]["video_title"] == "Daily Technical Strategy video"
    assert calls[0]["evidence_detail"]["names_sectors"] == "QQQ, semiconductors, AI beta."
    assert calls[0]["evidence_detail"]["confirmation_needed"] == "Breadth confirmation and QQQ support hold."
    assert "transcript_text" not in calls[0]["evidence_detail"]


def test_video_transcript_rejects_raw_transcript_text():
    calls, suppressed, problems = normalize_web_compact_rows({
        "items": [{
            "source_surface": "video_transcript",
            "full_content_basis": "visible transcript text on logged-in video page",
            "author": "Mark L. Newton, CMT",
            "ticker": "QQQ",
            "direction": "watch",
            "video_title": "Daily Technical Strategy video",
            "source_url": "https://fundstratdirect.com/members/video/example/",
            "directional_bias": "Higher if support holds.",
            "key_levels": "QQQ support 520.",
            "timing_horizon": "Tactical.",
            "change_vs_prior": "No explicit prior shift stated.",
            "action_implication": "Re-check before adding.",
            "transcript_text": "Long raw transcript text must not be accepted.",
            "quote": "Compact transcript-derived row.",
            "date": "2026-06-15",
        }]
    })

    assert calls == []
    assert suppressed == []
    assert any("raw text fields" in problem for problem in problems)


def test_web_intake_cli_writes_outputs(tmp_path):
    payload = tmp_path / "web.json"
    payload.write_text(json.dumps({
        "items": [{
            "source_surface": "flashinsights_feed",
            "full_content_basis": "complete FlashInsights feed card visible in logged-in Chrome",
            "author": "Mark L. Newton, CMT",
            "ticker": "QQQ",
            "direction": "avoid",
            "quote": "Premature to buy Tech dips while QQQ tests 675-679 and rotation out of Tech develops.",
            "date": "2026-06-09",
            "subject": "FlashInsights: QQQ support risk",
        }]
    }), encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            os.path.join(os.path.dirname(__file__), "fundstrat_web_intake.py"),
            str(payload),
            "--out-dir",
            str(tmp_path),
            "--generated-at",
            "2026-06-09T20:20:00+00:00",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["written"] is True
    assert (tmp_path / "fundstrat_daily_calls.json").is_file()
