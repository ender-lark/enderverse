# Investing 2026 — Code

Version-controlled home for the operational scripts behind the Investing 2026
framework. This repo holds **code only**. It is deliberately scoped so it can
be **public** without exposing anything sensitive.

---

## Why this exists (what it changes for you)

Before: every time a script changed, you downloaded it from chat and re-uploaded
it into the Claude project so Claude could see the current version.

Now: the script's canonical home is this repo. In a build session, Claude clones
this repo directly in its sandbox, so it always reads the **current** code with
no re-upload. Tests run automatically on every push. You get diff history for
free.

**The one manual step that remains:** writing *new* work product back into the
repo. GitHub does not allow anonymous writes, so Claude can't silently push from
chat (that would require pasting a credential into the transcript). The low-
friction path is the GitHub web UI — **Add file → Upload files → drag → Commit**
— which works from any browser, no terminal, no Claude Code required.

---

## What's in here vs. what's not

**In the repo (safe to publish):**
- `src/*.py` — all 47 operational + test scripts, unmodified.
- `.github/workflows/tests.yml` — runs the suite on every push.
- Dashboard code and docs. The canonical operator dashboard path is the
  Contract-C FEED rendered by `src/conviction_cockpit_v5.jsx` with live-feed
  injection through `src/render_cockpit.py`. `docs/index.html` is only a
  generated summary/export page unless it is explicitly brought to parity.

**Deliberately NOT in the repo** (kept in Notion + the Claude project — see
`.gitignore`):
- **State / holdings** — every `*.json` (positions, theses, source calls, etc.).
  Your portfolio never goes to a public repo.
- **Framework / CI docs** — the Custom Instructions, governance, principles, and
  reference `*.md` files. They embed Notion IDs and account structure, so they
  stay private. (Trade-off: doc changes are still handled manually. Docs change
  far less often than code, so this is the right boundary.)
- **Licensed research** — the Fundstrat / Meridian PDFs and docx.

**On secrets:** there are none in the code. Every credential is read from an
environment variable (`NOTION_API_TOKEN`, `UW_API_KEY`). The Notion IDs that do
appear are opaque identifiers — useless to anyone without your workspace token.

---

## One-time setup

1. Create a **new public repo** on GitHub named e.g. `investing-2026`.
   Do **not** initialize it with a README (this zip already has one).
2. On the empty repo's page: **Add file → Upload files**.
3. Drag in the **contents** of this folder (`src/`, `.github/`, `.gitignore`,
   `README.md`). Commit.
4. Go to the **Actions** tab — the `tests` workflow runs automatically and
   should go green (119 tests in the current snapshot).

That's it. No terminal, no local git install required.

---

## The ongoing loop (the discipline that keeps it frictionless)

- **Operate mode (daily):** you do nothing here. Work happens in chat against
  Notion as canonical state. This repo is invisible.
- **Build mode (when code changes):**
  1. Claude produces the updated script(s) in chat.
  2. You upload them to the repo via the web UI (one commit, multiple files OK).
  3. Next session, Claude clones the repo and is automatically current — **no
     re-upload to the Claude project needed.**
- **Tests** run on every commit. If a change breaks something, Actions tells you
  before it ever reaches a live session.

> Rule of thumb: **the repo is canonical for code; Notion is canonical for
> state; the Claude project is now optional for code** (you can stop maintaining
> the script copies there once the repo is live).

---

## Running Verification Locally

```powershell
pip install pytest requests
python src/verify_standard.py
```

For dashboard JSX edits, also run:

```powershell
python src/verify_standard.py --include-js
```

The standard command intentionally excludes the retired
`src/test_reallocate.py` tests and runs `src/test_reallocate_rebuild.py` instead.
See `docs/verification.md` for the exact check list and known expected failure.
