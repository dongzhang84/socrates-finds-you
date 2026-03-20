# Changelog

All notable changes to this project are documented here.

---

## [Unreleased]

---

## [2.0.2] — 2026-03-20

### Added
- `main.py` — pipeline summary table printed at the end of every run, showing per-platform **Scraped / Matched / Filtered** counts plus a TOTAL row.
- `storage/db.py` — `get_platform_summary(date)` helper used by the summary.

### Fixed
- `main.py` — removed `cscareerquestions` from `REDDIT_SUBREDDITS`. It was still being scraped despite `init_db()` deleting all cscareerquestions signals on every startup, wasting one API round-trip per run.

---

## [2.0.1] — 2026-03-20

### Fixed
- `push_report.sh` — removed early-exit that skipped report regeneration when the HTML file already existed. The stale file caused GitHub Pages to show fewer leads than the Flask dashboard when new signals were matched after the first run of the day.
- `reporter/daily_report.py` / `storage/db.py` — `get_report_candidates()` was filtering by `included_in_report = FALSE`, so any re-run of the reporter produced an empty report (all signals already marked). Now filters by `DATE(scraped_at) = <today>`, matching the same logic as `_get_leads()` in the Flask dashboard. The `mark_included_in_report` call is removed since it served no further purpose.

---

## [2.0.0] — 2026-03-20

### Added
- `push_report.sh` — one-command script to publish the daily HTML report to GitHub Pages (`gh-pages` branch → `index.html`). Accepts an optional date argument (`./push_report.sh 2026-03-19`). Live at: https://dongzhang84.github.io/socrates-finds-you
- `reporter/daily_report.py` — now generates a standalone **HTML report** (`output/report_YYYY-MM-DD.html`) alongside the existing Markdown. Includes all leads grouped by tier, with title, platform, service match, confidence, reasoning, suggested reply, clickable URL, **Copy** button (pure JS clipboard), and **Mark as Replied** button (pure JS, visual toggle, resets on refresh). No Flask dependency.
- HTML report: **Copy button** on each lead card — copies suggested reply to clipboard; flashes "Copied!" for 2 s then resets.
- HTML report: **Mark as Replied button** on each lead card — turns green ("✅ Replied") on click; visual only, no persistence.

### Changed
- **Claude matching prompt** (`matcher/claude_match.py`) completely rewritten to score leads by **conversion likelihood**, not service category. New criteria: HIGH (explicit ask, clear action intent), MEDIUM (interested but hesitant), NO (venting/complaints/unrelated — `matched=false`). System prompt now says "be strict — false negative is better than false positive."
- **Lead sort order within each tier** (`app.py` and `reporter/daily_report.py`) — leads now sorted by `service_match` priority: AI Career Path Planning → AI Upskilling for Professionals → Applied AI Project Coaching for Career Switchers → PhD to Industry Transition Coaching → AI / ML Learning Path Coaching → AP / SAT / ACT Math Tutoring → College-Level STEM Tutoring → everything else.
- All dates and timestamps in `reporter/daily_report.py` now use **Seattle time** (`ZoneInfo("America/Los_Angeles")`) instead of UTC. Report filenames, footer timestamps, and `push_report.sh` all consistent on Seattle time.

---

## [1.7.0] — 2026-03-19

### Added
- Dashboard: **date selector dropdown** in the filter bar — lists all dates that have matched signals (`SELECT DISTINCT DATE(scraped_at) … WHERE matched=TRUE`), formatted as "Today (YYYY-MM-DD)", "Yesterday (YYYY-MM-DD)", or bare date. Selecting a date reloads the page with `?date=YYYY-MM-DD`.
- Default date is today if signals exist for today, otherwise the most recent available date.
- `_get_matched_dates()` DB helper in `app.py`.

### Changed
- `_get_leads()` now filters by a specific calendar date (`DATE(scraped_at) = ?`) instead of a rolling 48-hour window.

---

## [1.6.0] — 2026-03-19

### Added
- Dashboard: **"Mark as Replied" / "✅ Replied" toggle button** on each lead card — click to mark a lead as replied (stored as `actioned=TRUE` in the DB); click again to undo. Button turns green when active, reverts to gray/white on undo. State persists across page reloads.
- Dashboard: **"Show All / Hide Replied" filter toggle** at the top of the leads section — defaults to Show All. When Hide Replied is active, cards with `actioned=TRUE` are hidden. Switching back to Show All reveals them without a page reload.
- `POST /api/mark-replied` endpoint — accepts `{ id, actioned: true|false }` JSON; sets or clears `actioned` on the signal record.
- `storage/db.py` — `mark_actioned(id)` helper.

### Changed
- Removed `r/cscareerquestions` from the Reddit subreddits list (`scrapers/reddit.py` `TIER_MEDIUM`).
- `storage/db.py` — `init_db()` now calls `delete_signals_by_subreddit("cscareerquestions")` on every startup to purge any existing signals from that subreddit.
- `storage/db.py` — added `delete_signals_by_subreddit(subreddit)` helper.

---

## [1.5.0] — 2026-03-17

### Added
- Dashboard: **LinkedIn — All Signals** section below the main leads report — shows every LinkedIn signal in the DB (matched or not) with title, URL, author, body snippet (200 chars), and a matched/unmatched badge

### Changed
- `scrapers/linkedin.py` — `max_posts` default raised from 20 → 100
- `scrapers/blind.py` — `max_posts` default raised from 30 → 100; replaced all `/topics/` pages with more relevant `/channels/` pages: Career, Job-Search, Career-Advice, working-parents, AI-Machine-Learning, Data-Science, Software-Engineering; JS stub-collection selectors hardened with fallback chain to handle both `/topics/` and `/channels/` DOM layouts

---

## [1.4.0] — 2026-03-17

### Added
- `suggested_reply` field — Claude now generates a ready-to-send Reddit reply (2–4 sentences, natural tone, soft CTA) for every matched signal alongside the existing `service_match`, `client_tier`, `confidence`, and `reasoning`
- `--fix-replies` flag in `main.py` — backfills `suggested_reply` for matched signals that predate the field; safe to re-run (skips signals that already have a reply)
- `storage/db.py` — `get_matched_without_reply()` and `update_suggested_reply()` helpers; auto-migration adds `suggested_reply TEXT` column to existing databases on first run
- Dashboard: each lead card now shows the suggested reply in a styled block with a one-click **Copy** button

### Changed
- **Run Pipeline** button now runs the full pipeline (`python3 main.py`) instead of `--reddit-only`, covering LinkedIn, Blind, HN, RSS, Reddit, and Grad Cafe
- Default port changed from 5000 → 8080
- `app.py` calls `init_db()` at startup so schema migrations apply automatically without running `main.py` first

---

## [1.3.0] — 2026-03-16

### Added
- `app.py` — local Flask web dashboard at `http://localhost:8080`
  - Leads grouped by tier (High / Medium / Low) with service match, confidence, and reasoning
  - **Run Pipeline** button triggers the full pipeline in the background with a live log stream
  - Auto-reloads page when pipeline finishes
  - Stats bar: total signals in DB, per-tier lead counts, last report timestamp

### Changed
- `README.md` fully rewritten — clearer Quick Start (4 steps), new Daily Use section, new "Adapting for Your Own Use Case" guide pointing to exactly two files to edit

---

## [1.2.0] — 2026-03-16

### Added
- `scrapers/reddit.py` — Reddit scraper using public `reddit.com/r/{sub}/new.json` API (no auth, no PRAW)
- `scrapers/gradcafe.py` — Grad Cafe scraper (Forums 72 Jobs + 21 Officially Grads) using stdlib `html.parser` state machines
- `matcher/claude_match.py` — Claude API semantic matching (`claude-sonnet-4-5`), batch size 10, result merging by `id` key, JSON fence stripping
- `reporter/daily_report.py` — Markdown report generator, tier-sorted High → Medium → Low, zero-signal safe
- `main.py` — unified pipeline entry point with five mutually exclusive flags

### Changed
- `main.py` — Twitter scraper disabled (API credits too expensive); `id` field assembled in `main()` as `{platform}:{external_id}`; added per-scraper progress logging so the ~2 min Claude matching phase is visible

---

## [1.1.0] — 2026-03-15

### Added
- `scrapers/hackernews.py` — HN Firebase REST API, concurrent fetch with `ThreadPoolExecutor(max_workers=10)`
- `scrapers/rss.py` — RSS scraper via `requests` + `feedparser.parse(bytes)` (macOS SSL workaround)
- `scrapers/twitter.py` — Twitter/X scraper using tweepy v4 (implemented, disabled by default)

### Fixed
- RSS: `feedparser.parse(url)` caused `CERTIFICATE_VERIFY_FAILED` on macOS — fixed by fetching with `requests` first and passing `resp.content` to feedparser

---

## [1.0.0] — 2026-03-14

### Added
- `storage/db.py` — SQLite storage layer (`data/signals.db`), `INSERT OR IGNORE` deduplication, `get_unmatched`, `update_match_result`, `get_report_candidates`, `mark_included_in_report`
- `scrapers/linkedin.py` — Playwright scraper with Google SSO login detection, `domcontentloaded` wait strategy, JS DOM traversal using stable `href` attributes (works despite SDUI obfuscated class names), `--debug` mode
- `scrapers/blind.py` — Playwright scraper, `CUTOFF_HOURS=168` (Blind shows popular posts 5–7 days old), two-phase stub→body fetch, relative + absolute timestamp parsing, `--debug` mode
- `docs/implementation-guide.md` — full build notes, actual selectors, lessons learned, deviations from spec
- Sprint tracking via GitHub Actions (`.github/workflows/sprint-report.yml`)

### Fixed
- LinkedIn: `networkidle` wait timed out (persistent background XHR) — replaced with `domcontentloaded` + `time.sleep(3)`
- LinkedIn: homepage now shows Google SSO button instead of email form — added click on `Sign in with email` before filling credentials
- LinkedIn: `.search-results-container` no longer exists (SDUI migration) — replaced all CSS selectors with `page.evaluate()` JS traversal
- Blind: `page.goto()` timed out for the same XHR reason as LinkedIn — same fix applied
- Blind: 48 h cutoff returned 0 results (popular posts are 5–7 days old) — raised to 168 h
