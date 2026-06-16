import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fundstrat_transcript_synthesis as fts
import fundstrat_transcript_vault as ftv


def _payload(raw_text: str) -> dict:
    return {
        "title": "Interim Deal Underpins Constructive Framework",
        "analyst": "Mark L. Newton, CMT",
        "source_url": "https://fundstratdirect.com/technical-strategy/example/",
        "source_date": "2026-06-15",
        "published_at": "2026-06-15T18:41:00-04:00",
        "captured_at": "2026-06-16T04:51:00Z",
        "capture_method": "chrome_visible_vimeo_transcript_panel_plus_player_caption_track",
        "completeness_notes": "Visible transcript panel plus player caption track.",
        "transcript_text": raw_text,
        "short_synthesis": "Newton stayed constructive while requiring support checks.",
        "analysis": {
            "executive_takeaway": "Use FOMC weakness as a re-check/add setup, not an automatic chase.",
            "key_claims": [
                "Breadth improved as risk assets reacted to lower crude and yields.",
                "Semis are strong but overbought.",
            ],
            "levels": [
                "SMH support at 553; 521.99 matters on a weekly close.",
            ],
            "portfolio_impact": "Keep equity stance constructive, but confirm support before sizing up.",
            "questions": ["Does the gap fill hold?", "Do Semis hold support?"],
        },
        "extracts": [
            {
                "ticker": "SMH",
                "claim": "Semis remain constructive while support holds.",
                "implication": "Stay with trend but do not overchase.",
            }
        ],
        "compact_rows": [
            {
                "source_surface": "video_captions",
                "full_content_basis": "complete caption track",
                "author": "Mark L. Newton, CMT",
                "ticker": "SMH",
                "direction": "hold",
                "date": "2026-06-15",
                "subject": "Daily Technical Strategy: Semis",
                "video_title": "Interim Deal Underpins Constructive Framework",
                "source_url": "https://fundstratdirect.com/technical-strategy/example/",
                "directional_bias": "strong but overbought",
                "key_levels": "553 support; 521.99 weekly support",
                "timing_horizon": "short-term trend check",
                "change_vs_prior": "strength reasserted",
                "action_implication": "stay with trend while support holds",
                "quote": "Semis are strong but overbought; stay with trend while support holds.",
            }
        ],
    }


def test_synthesis_builds_notion_note_without_raw_transcript(tmp_path):
    raw = "RAW PRIVATE TRANSCRIPT OPENING LINE. This text must never leave the vault output."
    vault = tmp_path / "vault"
    vault.mkdir()
    public_index = tmp_path / "public_index.json"
    report = ftv.write_transcript_pack(_payload(raw), vault_path=vault, public_index_path=public_index)
    out = tmp_path / "notes.json"

    synthesis_report = fts.build_notes(
        vault_path=vault,
        transcript_ids=[report["transcript_id"]],
        out_path=out,
        write_vault_notes=True,
    )

    assert synthesis_report["valid"] is True
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert fts.validate_notes_payload(payload) == []
    dumped = json.dumps(payload)
    assert raw not in dumped
    note = payload["items"][0]
    assert note["transcript_id"] == report["transcript_id"]
    assert note["priority"] == "medium"
    assert note["transcript_hash_ok"] is True
    assert "Raw transcript text is intentionally not included" in note["notion"]["content"]
    folder = vault / "fundstrat" / "transcripts" / "2026" / "06" / report["transcript_id"]
    assert (folder / fts.NOTE_MD).is_file()
    assert (folder / fts.SYNTHESIS_JSON).is_file()
    assert raw not in (folder / fts.NOTE_MD).read_text(encoding="utf-8")


def test_validate_notes_rejects_raw_transcript_shape():
    problems = fts.validate_notes_payload({
        "items": [{
            "transcript_id": "fundstrat-test",
            "raw_transcript": "private",
            "notion": {"content": "## Transcript\nprivate"},
        }]
    })

    assert problems
    assert any("raw transcript" in problem for problem in problems)
