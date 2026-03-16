# socrates-finds-you

> An automated pipeline that finds people who need STEM, AI, and career mentorship — before they find you.

Scrapes LinkedIn, Blind, Reddit, Hacker News, RSS feeds, and The Grad Cafe for coaching signals, uses **Claude AI** to match each post against a service menu, and delivers a ranked daily Markdown report with a local web dashboard.

**You focus on outreach. The pipeline handles discovery.**

---

## How It Works

```
Scrapers (9 platforms) → SQLite → Claude API Matcher → Daily Report + Web UI
```

**Three phases run end-to-end with a single command:**

1. **Scrape** — Pull posts and discussions from up to 9 platforms using Playwright, public APIs, and RSS
2. **Match** — Claude evaluates each signal against the service menu in batches of 10, returning `service_match`, `client_tier`, `confidence`, and a one-line `reasoning`
3. **Report** — Ranked Markdown report written to `output/report_YYYY-MM-DD.md`, plus a live web dashboard at `localhost:5000`

---

## Screenshot

> _Web dashboard — leads grouped by tier with service match, confidence, and reasoning_

![Dashboard placeholder](docs/screenshot.png)

```
# socrates-finds-you — Daily Report 2026-03-16

**6 leads matched** — 2 high / 4 medium / 0 low value

## 🔴 High Value (PhD / Professionals)

### 1. How do academics actually find jobs abroad?
- Platform: reddit · r/AskAcademia
- Service: PhD to Industry Transition Coaching
- Confidence: medium
- Why: Partner of academic seeking RAP positions abroad suggests potential career transition guidance need.
- Link: https://reddit.com/r/AskAcademia/comments/...
```

---

## Platforms Covered

| Priority | Platform | Client Tier | Method | Status |
|----------|----------|-------------|--------|--------|
| ⭐⭐⭐ | LinkedIn | Highest — PhD / professionals | Playwright | ✅ Active |
| ⭐⭐⭐ | Blind | Highest — big tech workers | Playwright | ✅ Active |
| ⭐⭐ | Hacker News | Mid-high — technical professionals | Firebase REST API | ✅ Active |
| ⭐⭐ | Substack / Medium | Mid-high — career changers | RSS (feedparser) | ✅ Active |
| ⭐⭐ | Reddit (11 subreddits) | Mixed — PhD to high school | Public JSON API | ✅ Active |
| ⭐ | The Grad Cafe | Mid — PhD students in limbo | requests + HTMLParser | ✅ Active |
| ⭐ | 小红书 | Mid — Chinese-speaking diaspora | Playwright | 🔧 Stub |
| — | Twitter/X | High | tweepy | ⛔ Disabled (API cost) |

**Reddit subreddits monitored:** r/PhD, r/AskAcademia, r/datascience, r/MachineLearning, r/cscareerquestions, r/learnmachinelearning, r/GradSchool, r/SAT, r/ApplyingToCollege, r/learnpython

---

## Tech Stack

| Layer | Choice |
|-------|--------|
| Language | Python 3.11+ |
| Browser automation | Playwright (sync API, `headless=False`) |
| HTTP scraping | requests + feedparser |
| Database | SQLite — `data/signals.db` |
| AI matching | Anthropic SDK — `claude-sonnet-4-5` |
| Web UI | Flask |
| Output | Markdown reports in `output/` |

---

## Quick Start

```bash
git clone https://github.com/dongzhang84/socrates-finds-you
cd socrates-finds-you

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium

cp .env.example .env     # fill in your credentials
python storage/db.py     # initialize database

# Verify the full pipeline with free scrapers only
python main.py --reddit-only
```

Open the web dashboard:

```bash
python app.py            # → http://localhost:5000
```

---

## Usage

```bash
# Full run — all active platforms (LinkedIn, Blind, HN, RSS, Reddit, Grad Cafe)
python main.py

# High-value only — LinkedIn + Blind (browser required)
python main.py --high-value-only

# No browser — HN + RSS + Reddit + Grad Cafe (best for cron / headless servers)
python main.py --no-browser

# Free scrapers only — HN + RSS + Reddit + Grad Cafe (fastest, no credentials needed)
python main.py --reddit-only

# Skip scraping — re-run Claude matching on existing unmatched signals
python main.py --no-scrape

# Skip scraping and matching — regenerate today's report from already-matched data
python main.py --report-only
```

Reports are saved to `output/report_YYYY-MM-DD.md`. Each run appends new signals; duplicates are silently skipped.

---

## Web Dashboard

```bash
python app.py
```

Opens at **http://localhost:5000**. Shows:

- Total signals in the database
- Matched leads from the last 48 hours grouped by tier (High / Medium / Low)
- Per-lead: title (linked), platform + subreddit, service match, confidence badge, reasoning
- **Run Pipeline** button — triggers `python main.py --reddit-only` in the background with a live log stream, then auto-reloads when done

---

## Project Structure

```
socrates-finds-you/
├── scrapers/
│   ├── linkedin.py          # Playwright — login + keyword search + JS DOM traversal
│   ├── blind.py             # Playwright — Career/Job topics, 7-day window
│   ├── hackernews.py        # Firebase REST API, concurrent fetch (ThreadPoolExecutor)
│   ├── rss.py               # feedparser via requests (macOS SSL workaround)
│   ├── reddit.py            # Public reddit.com/r/{sub}/new.json — no auth needed
│   ├── gradcafe.py          # HTMLParser state machines, Forums 72 + 21
│   ├── twitter.py           # tweepy (disabled — API credits)
│   └── xiaohongshu.py       # Playwright stub
├── matcher/
│   └── claude_match.py      # Claude API semantic matching, batches of 10
├── storage/
│   └── db.py                # SQLite — init, save, get_unmatched, update, report
├── reporter/
│   └── daily_report.py      # Markdown report generator, tier-sorted
├── docs/
│   ├── 01-services.md       # Full service menu
│   ├── 02-platforms.md      # Platform priority rationale
│   └── implementation-guide.md  # Build notes, lessons learned, actual selectors
├── output/                  # Daily reports — gitignored
├── data/                    # SQLite database — gitignored
├── app.py                   # Flask web dashboard
├── main.py                  # Pipeline entry point
├── requirements.txt
└── .env.example
```

---

## Environment Variables

Copy `.env.example` to `.env` and fill in the values you need. Only `ANTHROPIC_API_KEY` is required for the free-scraper mode (`--reddit-only`).

```bash
# Required
ANTHROPIC_API_KEY=sk-ant-...          # Claude API key

# LinkedIn scraper (headless=False, personal account)
LINKEDIN_EMAIL=you@example.com
LINKEDIN_PASSWORD=...

# Blind scraper (headless=False, personal account)
BLIND_EMAIL=you@example.com
BLIND_PASSWORD=...

# Twitter/X — disabled by default (API credits)
TWITTER_BEARER_TOKEN=...

# Reddit — reserved (not used; scraper uses public .json API)
REDDIT_CLIENT_ID=...
REDDIT_CLIENT_SECRET=...
REDDIT_USER_AGENT=socrates-finds-you/1.0

# 小红书 — stub, not yet active
XIAOHONGSHU_PHONE=+1...
XIAOHONGSHU_PASSWORD=...
```

> All credentials stay on your local machine. This tool is never deployed to a server.

---

## Database Schema

```sql
CREATE TABLE signals (
    id               TEXT PRIMARY KEY,   -- "{platform}:{external_id}"
    platform         TEXT NOT NULL,
    external_id      TEXT NOT NULL,
    url              TEXT NOT NULL,
    title            TEXT NOT NULL,
    body             TEXT,
    author           TEXT,
    subreddit        TEXT,               -- Reddit only
    posted_at        DATETIME,
    scraped_at       DATETIME DEFAULT CURRENT_TIMESTAMP,

    -- Matching results (set by Claude)
    matched          BOOLEAN DEFAULT FALSE,
    service_match    TEXT,               -- e.g. "PhD to Industry Transition Coaching"
    client_tier      TEXT,               -- "high" | "medium" | "low"
    confidence       TEXT,               -- "high" | "medium" | "low"
    reasoning        TEXT,               -- one-sentence explanation

    -- Tracking
    included_in_report  BOOLEAN DEFAULT FALSE,
    actioned            BOOLEAN DEFAULT FALSE,

    UNIQUE(platform, external_id)
);
```

---

## Services Matched

Claude evaluates each signal against this menu:

**High Value** — PhD students, professionals
- PhD to Industry Transition Coaching
- AI Career Path Planning
- Applied AI Project Coaching for Career Switchers
- AI Upskilling for Professionals

**Medium Value** — College students, early-career
- AI / ML Learning Path Coaching
- College-Level STEM Tutoring
- Research / Independent Project Coaching

**Lower Value** — High school students, parents
- AI Project Mentorship for High School Students
- AP / SAT / ACT Math Tutoring
- AI Literacy for Students

---

## Cost Estimate

| Component | Cost |
|-----------|------|
| Claude API (~150 signals × ~500 tokens/run) | ~$0.05–$0.20/run |
| Reddit, HN, RSS, Grad Cafe | Free |
| LinkedIn, Blind, 小红书 (personal account) | Free |
| Twitter/X API | Disabled — too expensive |
| **Monthly estimate (daily runs)** | **~$1–6/month** |

---

## Caveats

- **LinkedIn and Blind** require `headless=False` and a real account. Both have anti-bot detection. Run at most once per day.
- **LinkedIn DOM** changes frequently — if it breaks, run `python scrapers/linkedin.py --debug` to capture the current HTML and update selectors.
- **Twitter/X** is fully implemented (`scrapers/twitter.py`) but commented out in `main.py`. Re-enable by uncommenting `TWITTER_QUERIES` and the scraper call in `run_scraping()`.
- This is a personal local tool, not a SaaS product. No auth, no deployment, no database server.

---

## License

MIT
