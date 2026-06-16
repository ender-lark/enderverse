# Fundstrat Late Evening Web/Transcript Sweep

## Objective

Capture late Fundstrat web/video updates after the regular after-hours catch-up
without putting raw transcript text in the public repo.

This routine exists for video-first Fundstrat updates where a logged-in page
exposes a visible transcript, captions, companion article text, or a supplied
compact note. Video-only titles, thumbnails, player embeds, and listing cards
remain discovery-only.

This is a Chrome-driven routine. Codex should navigate Fundstrat directly in
the user's logged-in Chrome session, open recent video/article detail pages, and
check transcript/caption/player controls itself. The operator is not expected to
manually drive the page unless Fundstrat blocks the session, asks for login or
CAPTCHA, or hides transcript controls that require human intervention.

## Inputs

- Authenticated Fundstrat member pages through the user's logged-in Chrome
  session.
- User-supplied transcript/caption/companion text payloads.
- Private source vault path from `INVESTING_OS_SOURCE_VAULT`.
- Existing compact Fundstrat caches in `src/`.

## Procedure

1. Write a `started` receipt with `run_source=scheduled` through
   `cloud_routine_runner.py` or `cloud_routine_receipts.py`.
2. Open Fundstrat in Chrome and check recent web/video surfaces:
   - Latest Videos and relevant analyst/category pages for new videos.
   - Video detail pages, not only listing cards.
   - Embedded player transcript/caption controls and any visible transcript
     panes, scrolling the pane when needed.
   - Companion article/detail text when attached to the video.
   Do not treat listing cards, video thumbnails, or the player embed alone as
   checked evidence.
3. For each checked video/article payload with transcript, captions, companion
   article text, or supplied compact notes, run:

   ```powershell
   python src/fundstrat_transcript_vault.py <payload.json> --commit-vault --push-vault
   ```

   Raw transcript/caption text must go only to the private vault. The public
   repo receives only `src/fundstrat_transcript_index.json` metadata, hashes,
   short synthesis, and compact row counts.

4. Build compact Notion-ready notes from the private vault:

   ```powershell
   python src/fundstrat_transcript_synthesis.py --since <YYYY-MM-DD> --out tmp/fundstrat_transcript_notion_notes.json --write-vault-notes --commit-vault --push-vault
   ```

5. Write or update Notion Synthesis Log review notes from
   `tmp/fundstrat_transcript_notion_notes.json`. Fetch each page back and verify
   the compact note landed before claiming success.
6. Merge compact transcript-derived rows through the existing Fundstrat compact
   intake path. The compact rows may update Fundstrat daily calls, source-call
   candidates, source-call calibration, and the dashboard only when they carry
   transcript/caption/companion evidence.
7. Refresh the dashboard if compact rows changed action posture, re-check
   priority, source-call calibration, or research priority.
8. Validate:

   ```powershell
   python src/fundstrat_transcript_vault.py --validate-public-index
   python src/fundstrat_transcript_synthesis.py --validate tmp/fundstrat_transcript_notion_notes.json
   python -m pytest src/test_fundstrat_transcript_vault.py src/test_fundstrat_transcript_synthesis.py src/test_fundstrat_web_intake.py -q
   ```

9. Commit routine-owned public outputs with the safe commit helper. Leave
   unrelated dirty files untouched.
10. Write a `success` or `failed` receipt with `run_source=scheduled`.

## No-Input Behavior

If no checked transcript, caption track, companion article text, or supplied
compact note is available, write a successful not-checked/no-new-input receipt.
Do not update public Fundstrat caches, do not create Notion review notes, and do
not mark video-only discovery as checked clear.

Chrome login/session failures, CAPTCHA, permission prompts, inaccessible tabs,
or missing player transcript/caption tracks are not a reason to invent a short
note. Record the exact blocker in the receipt or handoff and keep the item
discovery-only / `not_checked`.

## Public/Private Boundary

- Public repo allowed: metadata, hashes, short synthesis, compact derived rows,
  counts, `vault://...` references, validation results, and dashboard artifacts.
- Private vault only: raw transcript text, full caption text, source JSON with
  private transcript metadata, extracted private analysis packs, and private
  synthesis note artifacts.
- Never commit credentials, cookies, Chrome profile data, screenshots, raw
  member-page bodies, or raw transcript/caption text to the public repo.
