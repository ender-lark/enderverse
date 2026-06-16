import hashlib
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fundstrat_transcript_vault as ftv


def _payload(transcript="FULL PRIVATE TRANSCRIPT TEXT with levels and discussion."):
    return {
        "title": "Daily Technical Strategy with Mark Newton",
        "analyst": "Mark L. Newton, CMT",
        "source_url": "https://fundstratdirect.com/technical-strategy/example/",
        "published_at": "2026-06-12T20:20:00-04:00",
        "captured_at": "2026-06-16T12:00:00-04:00",
        "capture_method": "chrome_visible_transcript",
        "completeness_notes": "Visible transcript panel captured through Chrome.",
        "transcript_text": transcript,
        "short_synthesis": "Newton framed breadth as constructive while requiring confirmation before chasing tech beta.",
        "analysis": {
            "executive_takeaway": "Constructive breadth, but wait for confirmation.",
            "key_claims": ["Breadth improving", "Tech beta should be re-checked"],
            "portfolio_impact": "Use as review input, not a trade trigger.",
        },
        "extracts": [
            {
                "ticker": "SPY",
                "claim": "Breadth supports a constructive broad-market setup.",
                "use_case": "macro_timing_review",
            }
        ],
        "compact_rows": [
            {
                "source_surface": "video_transcript",
                "ticker": "SPY",
                "direction": "watch",
                "quote": "Breadth supports a constructive setup, but tech beta needs confirmation.",
            }
        ],
    }


def test_transcript_id_and_voice_lane_are_stable():
    payload = _payload()

    assert ftv.transcript_id_for(payload) == "fundstrat-2026-06-12-newton-daily-technical-strategy-with-mark-newton"
    assert ftv.voice_lane_for("Mark L. Newton, CMT", payload["title"]) == "mark_newton_technical"
    assert ftv.voice_lane_for("Tom Lee", "Macro Minute") == "tom_lee_macro"


def test_write_transcript_pack_keeps_raw_text_out_of_public_index(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    public_index = tmp_path / "public_index.json"
    payload = _payload()
    raw_text = payload["transcript_text"]

    report = ftv.write_transcript_pack(payload, vault_path=vault, public_index_path=public_index)

    assert report["valid"] is True
    folder = vault / "fundstrat" / "transcripts" / "2026" / "06" / report["transcript_id"]
    transcript_md = (folder / "transcript.md").read_text(encoding="utf-8")
    assert raw_text in transcript_md
    assert (folder / "source.json").is_file()
    assert (folder / "analysis.md").is_file()
    assert (folder / "extracts.json").is_file()
    assert (vault / "fundstrat" / "manifests" / "fundstrat_transcripts.json").is_file()

    public_payload = json.loads(public_index.read_text(encoding="utf-8"))
    assert ftv.validate_public_index_payload(public_payload) == []
    public_text = json.dumps(public_payload)
    assert raw_text not in public_text
    row = public_payload["items"][0]
    assert row["transcript_sha256"] == hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    assert row["transcript_chars"] == len(raw_text)
    assert row["vault_ref"].startswith("vault://fundstrat/transcripts/2026/06/")


def test_duplicate_url_and_hash_replaces_public_index_row(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    public_index = tmp_path / "public_index.json"
    payload = _payload()

    ftv.write_transcript_pack(payload, vault_path=vault, public_index_path=public_index)
    payload["short_synthesis"] = "Updated safe synthesis."
    ftv.write_transcript_pack(payload, vault_path=vault, public_index_path=public_index)

    public_payload = json.loads(public_index.read_text(encoding="utf-8"))
    assert len(public_payload["items"]) == 1
    assert public_payload["items"][0]["short_synthesis"] == "Updated safe synthesis."


def test_public_index_validation_rejects_raw_transcript_keys():
    problems = ftv.validate_public_index_payload({
        "items": [{
            "transcript_id": "x",
            "vault_ref": "vault://x",
            "transcript_text": "must not be public",
        }]
    })

    assert any("raw transcript" in problem or "non-public" in problem for problem in problems)


def test_missing_transcript_is_rejected(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    payload = _payload(transcript="")

    with pytest.raises(ValueError, match="transcript"):
        ftv.write_transcript_pack(payload, vault_path=vault, public_index_path=tmp_path / "idx.json")
