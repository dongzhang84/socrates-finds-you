# CLAUDE.md — Project Context for Claude Code

## What this project does

`socrates-finds-you` is a local lead-discovery pipeline for Dong Zhang, Ph.D. — a STEM and AI mentor. It scrapes multiple platforms for posts from people who need coaching or mentorship, uses Claude AI to match each signal against a service menu, generates a suggested Reddit reply, and surfaces everything in a local Flask dashboard.

## Architecture

```
Scrapers → SQLite (data/signals.db) → Claude Matcher → Report + Web Dashboard
```

**Entry points:**
- `main.py` — CLI pipeline runner
- `app.py` — Flask web dashboard at `http://localhost:8080`

**Key modules:**
- `scrapers/` — one file per platform (LinkedIn, Blind, Reddit, HN, RSS, Grad Cafe, 小红书)
- `matcher/claude_match.py` — Claude API batched matching + reply generation
- `storage/db.py` — all SQLite access; `init_db()` handles schema + auto-migrations + purges retired subreddits
- `reporter/daily_report.py` — Markdown report generator

## Database

SQLite at `data/signals.db`. Schema defined in `storage/db.py:init_db()` — always add new columns there AND include an `ALTER TABLE ... ADD COLUMN` migration guard so existing DBs are updated automatically.

Key columns: `id` (platform:external_id), `matched`, `service_match`, `client_tier` (high/medium/low), `confidence`, `reasoning`, `suggested_reply`.

## Scrapers

| Scraper | Method | Notes |
|---------|--------|-------|
| `linkedin.py` | Playwright, `headless=False` | max_posts=100; requires LINKEDIN_EMAIL + PASSWORD |
| `blind.py` | Playwright, `headless=False` | max_posts=100; scrapes `/channels/` pages (not `/topics/`); 7-day cutoff |
| `reddit.py` | Public JSON API | No auth needed |
| `hackernews.py` | Firebase REST API | ThreadPoolExecutor |
| `rss.py` | requests + feedparser | macOS SSL workaround: fetch bytes, pass to feedparser |
| `gradcafe.py` | requests + HTMLParser | Forums 72 + 21 |
| `twitter.py` | tweepy | Disabled — API cost |
| `xiaohongshu.py` | Playwright stub | Not yet active |

**Blind `/channels/` note:** The JS stub-collection selector uses `data-testid="popular-article-preview-title"` with fallbacks for `[data-testid*="title"]` and `h2, h3, [class*="title"]`. If a new channel page returns 0 stubs, run `python scrapers/blind.py --debug` to capture the HTML.

## Matcher

`matcher/claude_match.py` runs two types of Claude calls:
- `match_signals(signals)` — batch-evaluates unmatched signals; returns matched/tier/confidence/reasoning/suggested_reply
- `generate_replies(signals)` — generates `suggested_reply` only for already-matched signals (used by `--fix-replies`)

Model: `claude-sonnet-4-5`. Batch size: 10. Max tokens: 4096.

**Scoring criteria (conversion likelihood, not service category):**
- HIGH (`matched=True`, `client_tier="high"`) — explicit ask with clear action intent (PhD→industry, AI career, tutor request)
- MEDIUM (`matched=True`, `client_tier="medium"`) — interested but hesitant or direction unclear
- NO (`matched=False`) — venting, complaints, unrelated, sharing news with no ask for help

The prompt instructs Claude to be strict: false negatives are preferred over false positives.

## main.py flags

| Flag | What it does |
|------|-------------|
| _(none)_ | Full pipeline — all active scrapers |
| `--reddit-only` | HN + RSS + Reddit + Grad Cafe only |
| `--high-value-only` | LinkedIn + Blind only |
| `--no-browser` | Skip Playwright scrapers |
| `--no-scrape` | Re-run matching on existing unmatched signals |
| `--report-only` | Regenerate Markdown report only |
| `--fix-replies` | Backfill suggested_reply for matched signals missing one |

## Web Dashboard (`app.py`)

- Calls `init_db()` at startup — safe to run without running `main.py` first
- **Date selector** dropdown — populated from `SELECT DISTINCT DATE(scraped_at) … WHERE matched=TRUE`; defaults to today; drives `?date=YYYY-MM-DD` URL param. `_get_leads(date)` filters by calendar date, not a rolling window.
- Main section: matched leads for the selected date, grouped by tier, with suggested reply + Copy button
- **Lead sort order within each tier**: AI Career Path Planning → AI Upskilling for Professionals → Applied AI Project Coaching → PhD to Industry Transition → AI/ML Learning Path → AP/SAT/ACT Math → College-Level STEM → everything else. Defined by `service_priority` dict in `index()`.
- **Mark as Replied** button on each lead card — POSTs to `POST /api/mark-replied` with `{ id, actioned: bool }`; toggles `actioned` in the DB; button turns green ("✅ Replied") when active, reverts on undo
- **Show All / Hide Replied** filter toggle (default: Show All) — hides/shows `actioned` cards client-side without reload
- Bottom section: **LinkedIn — All Signals** — every LinkedIn signal regardless of match status

## Reporter (`reporter/daily_report.py`)

- Generates both `output/report_YYYY-MM-DD.md` (Markdown) and `output/report_YYYY-MM-DD.html` (standalone HTML) on every run
- All dates and timestamps use **Seattle time** (`ZoneInfo("America/Los_Angeles")`)
- HTML report includes the same tier/service sort order as the dashboard, Copy button (JS clipboard), and Mark as Replied button (JS visual toggle, resets on refresh) — no Flask dependency
- `_group_by_tier(signals)` applies the `SERVICE_PRIORITY` sort within each tier (same priorities as `app.py`)

## GitHub Pages (`push_report.sh`)

Publishes the daily HTML report to GitHub Pages:
```bash
./push_report.sh                  # today's report (Seattle time)
./push_report.sh 2026-03-19      # specific date
```
- Always regenerates the report before pushing (never skips)
- Checks out `gh-pages`, copies HTML to `index.html`, commits, pushes, returns to `main`
- Live at: https://dongzhang84.github.io/socrates-finds-you

## Conventions

- All DB access goes through `storage/db.py` — don't call `sqlite3` directly in other modules
- Signals get their `id` assembled in `main.py` as `{platform}:{external_id}`
- Port: 8080
- Python 3.11+
