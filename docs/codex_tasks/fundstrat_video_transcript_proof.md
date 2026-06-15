# Fundstrat Video Transcript Proof

Date: 2026-06-15

## Scope

One proof only: read one visible Fundstrat video transcript through the user's
logged-in Chrome session, distill it into a compact Fundstrat evidence row, and
prove the row lands where the existing Fundstrat intake reads evidence.

No raw transcript text, screenshots, cookies, credentials, browser storage, or
long copied member content were stored in repo files.

## Source Checked

- Source: Fundstrat Direct Daily Technical Strategy video
- Presenter: Mark L. Newton, CMT
- Video: `06/12/26 Technical Strategy with Mark Newton, CMT`
- Article title: `Increasing Sector participation seen as constructive as Crude, US Dollar & Rates drop`
- Published: 2026-06-12 20:20 ET
- URL: `https://fundstratdirect.com/technical-strategy/2026/06/12/increasing-sector-participation-seen-as-constructive-as-crude-us-dollar-rat/`
- Evidence basis: visible Vimeo transcript panel plus player-exposed caption
  track in the user's Chrome session

## Compact Row Landed

- Surface: `video_transcript`
- Ticker/proxy: `SPY`
- Direction: `watch`
- Window: next week into the late-July/August cycle check
- Portfolio implication: watch SPY/RSP breadth confirmation and re-check
  QQQ/semis before chasing AI/tech beta
- Guardrail: source evidence only; not a trade trigger
- Source message id:
  `fundstrat-video-transcript-2026-06-12-newton-spy-rsp`

The row landed in `src/fundstrat_daily_calls.json` and propagated to
`src/source_calls.json` with `repo_cache_only=true`.

Follow-up adjustment: transcript-derived rows should err on storing more
structured distillation rather than less. Keep the dashboard-facing quote short,
but preserve the richer `evidence_detail` block with title, URL, bias, levels,
timing, names/sectors, change versus prior, portfolio implication, confirmation
needed, blocker before action, and suggested next check. Do not store the raw
transcript.

## Verification

Passed:

```bash
python -m pytest src/test_fundstrat_web_intake.py src/test_fundstrat_daily_compact_intake.py -q
python src/fundstrat_email_intake.py --validate src
```

Temporary proof output also validated in `tmp/fundstrat_video_transcript_proof`
before the `src --merge-existing` landing.

## Operating Notes

- Video transcript rows now require compact proof fields when using
  `video_transcript` or `video_captions`.
- Expanded transcript distillation is stored as structured `evidence_detail`.
- Raw transcript fields such as `transcript_text` are rejected.
- Video-only cards, embeds, thumbnails, and titles remain discovery-only.
- A missing or inaccessible transcript must stay not checked.
