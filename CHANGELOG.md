# Changelog

All notable changes to this project are documented here.

---

## [Unreleased]

---

## [1.3.0] — 2026-03-16

### Added
- `app.py` — local Flask web dashboard at `http://localhost:5000`
  - Leads grouped by tier (High / Medium / Low) with service match, confidence, and reasoning
  - **Run Pipeline** button triggers `python3 main.py --reddit-only` in the background with a live log stream
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
