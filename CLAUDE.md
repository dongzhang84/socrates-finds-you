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
- Main section: matched leads from last 48 hours, grouped by tier, with suggested reply + Copy button
- **Mark as Replied** button on each lead card — POSTs to `POST /api/mark-replied` with `{ id, actioned: bool }`; toggles `actioned` in the DB; button turns green ("✅ Replied") when active, reverts on undo
- **Show All / Hide Replied** filter toggle (default: Show All) — hides/shows `actioned` cards client-side without reload
- Bottom section: **LinkedIn — All Signals** — every LinkedIn signal regardless of match status

## Conventions

- All DB access goes through `storage/db.py` — don't call `sqlite3` directly in other modules
- Signals get their `id` assembled in `main.py` as `{platform}:{external_id}`
- Port: 8080
- Python 3.11+
