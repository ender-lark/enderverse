# Fundstrat Web Fast Lane

## Objective

Use the authenticated Fundstrat website as the fastest full-content source for
FlashInsights and other high-decay Fundstrat notes when email delivery lags.
The broader source map lives in `docs/fundstrat_source_catalog.md`.

This lane is an upstream acquisition path only. It feeds the existing compact
Fundstrat daily-call intake and does not create trade actions by itself.

## Feasibility Snapshot

On 2026-06-09, Chrome control could access the logged-in Fundstrat Direct member
FlashInsights page through the user's existing browser session. The main
FlashInsights feed rendered complete FlashInsights card text plus timestamp,
author, ticker tags, and visible source context.

A temporary compact row derived from the visible page was accepted by the
strict web helper:

```bash
python src/fundstrat_web_intake.py --stdin-json --out-dir tmp\fundstrat_web_feasibility --generated-at "2026-06-09T16:20:00-04:00"
```

The temporary proof wrote redacted audit/state files, produced one source-call
candidate, and `python src/fundstrat_email_intake.py --validate
tmp\fundstrat_web_feasibility` returned valid with no problems. Focused compact
intake and daytime alert tests also passed.

## Source Rules

- The user logs into Fundstrat in Chrome. Codex must not receive or store
  Fundstrat credentials, cookies, local storage, browser profile data, or
  passwords.
- Chrome use stays read-only unless the user gives a narrow instruction for a
  specific browser-side action.
- iOS Fundstrat push notifications are discovery triggers only. They can tell
  the operator that a new item exists, but they are snippet-only and must not
  update checked Fundstrat caches.
- A Fundstrat web item becomes checked only after Codex can read the visible
  member page/card/article content in Chrome or the user supplies equivalent
  full-content evidence.
- The main FlashInsights page can be full-content evidence when it renders the
  full FlashInsights cards.
- Most non-FlashInsights articles require opening the article detail page before
  they count as full-body checked. Listing cards, search results, notifications,
  and snippets are discovery only.
- Stock-list and crypto-list tables are slower baseline/diff sources, not
  daily-call rows. Capture them only through a future baseline lane or a
  specific user request.
- Do not store raw Fundstrat article bodies, long excerpts, screenshots, or
  copied page text in tracked repo files.
- Store only compact source-backed rows that preserve date, author/lane,
  ticker, direction/posture, levels, timing/risk summary, and source surface.

## Workflow

1. Open the authenticated Fundstrat member page in Chrome:

   ```text
   https://fundstratdirect.com/members/flashinsights/
   ```

   Use the crypto page separately when crypto FlashInsights matter:

   ```text
   https://fundstratdirect.com/members/crypto-flash-insights/
   ```

2. Confirm the page is logged in and current. Evidence can include the member
   page title, visible account greeting, visible refresh control, latest
   FlashInsights timestamp, and ticker tags.

3. For FlashInsights, read compact source inputs from the visible feed cards
   only when the card itself contains the full note. For standard Fundstrat
   research/articles, open the article detail page first and confirm the
   article text or transcript is visible before marking the item full-body
   checked.

4. Extract only compact row inputs. The helper requires `source_surface` and
   `full_content_basis`; it rejects raw article fields such as `body`,
   `article_text`, `html`, screenshots, listing snippets, push notifications,
   and video-only titles.

   ```json
   {
     "items": [
       {
         "source_surface": "flashinsights_feed",
         "full_content_basis": "complete FlashInsights feed card visible in logged-in Chrome",
         "author": "Mark L. Newton, CMT",
         "ticker": "QQQ",
         "direction": "avoid",
         "quote": "Short source-backed paraphrase, <= 320 chars, with levels/timing/risk.",
         "date": "2026-06-09",
         "subject": "FlashInsights: short title or operator label",
         "source_message_id": "fundstrat-web-flashinsights-YYYY-MM-DD-HHMM-et-ticker",
         "source": "Fundstrat Chrome member FlashInsights page"
       }
     ]
   }
   ```

5. Run the strict web wrapper. It delegates accepted rows to the existing
   compact intake and leaves discovery-only rows out of checked caches:

   ```bash
   python src/fundstrat_web_intake.py --stdin-json --out-dir src --merge-existing
   ```

6. Validate and alert through the existing routine gates:

   ```bash
   python src/fundstrat_email_intake.py --validate src
   python src/fundstrat_daytime_alert.py --send --write-state --format text
   ```

7. Refresh the dashboard only after validation succeeds. If the run is scheduled
   or routine-owned, use the existing receipt and commit helpers rather than
   ad-hoc git staging.

## Source Surfaces

Allowed checked surfaces:

- `flashinsights_feed`: complete FlashInsights card visible in the logged-in
  feed
- `flashinsights_detail`: FlashInsights detail page, if used
- `article_detail`: standard research article detail page with article text
  visible
- `video_transcript` / `video_captions`: video page with transcript or captions
  visible
- `companion_article`: text article attached to or summarizing a video
- `supplied_compact_notes`: user-supplied compact notes from a full-content
  review

Discovery-only surfaces:

- `ios_push` / `push_notification`
- `listing_card` / `article_listing` / `search_result`
- `email_snippet`
- `video_only` / `video_embed` / `thumbnail`

## Video Handling

Tom Lee macro updates and other Fundstrat videos now have two separate paths:
full transcript review and compact cockpit intake. The full transcript review
path writes source material only to the private source vault pointed to by
`INVESTING_OS_SOURCE_VAULT`; the public repo stores only metadata, hashes,
analysis summaries, and compact derived rows.

Videos can be handled safely only when one of these is available:

- a visible article transcript on the member page
- captions/transcript text exposed by the video player
- a Fundstrat email/article companion that summarizes the video
- a user-supplied transcript or compact notes

The first proof, run on 2026-06-15 against Mark Newton's 2026-06-12 Daily
Technical Strategy video, used the user's logged-in Chrome session, the visible
Vimeo transcript panel, and the player-exposed caption track. The accepted row
was compact only and landed through `source_surface=video_transcript`.

For full transcript review, use:

```bash
python src/fundstrat_transcript_vault.py transcript_payload.json --commit-vault --push-vault
python src/fundstrat_transcript_vault.py --validate-public-index
python src/fundstrat_transcript_synthesis.py --since YYYY-MM-DD --out tmp\fundstrat_transcript_notion_notes.json --write-vault-notes --commit-vault --push-vault
python src/fundstrat_transcript_synthesis.py --validate tmp\fundstrat_transcript_notion_notes.json
```

The payload may include `transcript_text`, source metadata, `analysis`,
`extracts`, and optional `compact_rows`. The helper writes full transcript text
only to the private vault and updates `src/fundstrat_transcript_index.json` with
safe metadata only. If no transcript/captions are visible, do not write a
checked transcript entry; leave the video discovery-only / not checked.

The synthesis helper reads the private vault pack and emits compact
Notion-ready action notes without raw transcript text. Write those notes to the
Notion Synthesis Log or the relevant action/research page, then fetch the live
Notion page back and verify the transcript id or title landed before reporting
Notion success. If Notion is unavailable, report the Notion write as
`not_checked` and keep the generated note in the private vault / temporary
handoff file; do not paste the full transcript into chat or public repo files.

For video transcript rows, do not pass raw transcript text. Supply compact proof
fields instead:

- `presenter` or `author`
- `video_title`
- `source_url`
- `directional_bias`
- `key_levels`
- `timing_horizon`
- `names` or `sectors` when relevant
- `change_vs_prior`
- `action_implication`
- short `quote`/summary, no more than the compact intake limit

Broad macro calls must map to a portfolio proxy before they can land: `SPY` for
broad market, `RSP` for breadth/equal-weight, `QQQ` for AI/tech/Nasdaq/growth,
`IWM` for small caps, `TLT` for rates/duration, and a sector ETF only when the
call is clearly sector-specific.

Video-only items still remain discovery/audit-only when no transcript, captions,
companion article, or compact user-supplied notes are visible.

## Compact Row Policy

Use this lane only when the Fundstrat item changes or clarifies one of:

- action posture: act, wait, trim, avoid, hedge, re-check
- timing: intraday, same-session, short-term, target window
- sizing or leverage posture
- risk/invalidation levels
- research priority for a named ticker or portfolio exposure

Suppress or audit-only:

- webinar, replay, promotion, invite, or marketing content
- video-only content without transcript, captions, companion article, or
  compact user-supplied notes
- broad backdrop with no action, timing, sizing, hedge, risk, or research
  implication
- monthly list/table content that belongs in the Bible/prospect lane
- snippet-only notifications or email search results

## Operating Notes

- This lane is faster than Gmail when Fundstrat delays email delivery.
- It is not fully unattended unless Chrome is logged in and available to the
  Codex session. Browser login prompts, CAPTCHA, or permission prompts are user
  handoff states.
- If Chrome access fails, fall back to Gmail full-body intake, Drive/manual
  source drop, or user-supplied website text/screenshots routed through compact
  intake.
- If only a push notification exists and no member-page content is read, report
  Fundstrat as discovered/not checked rather than checked clear.
