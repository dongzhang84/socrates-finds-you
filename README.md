# socrates-finds-you

> An automated pipeline that finds people who need STEM, AI, and career mentorship — before they find you.

---

## What It Does

High-value coaching and mentoring needs appear every day across LinkedIn, Blind, Reddit, Twitter, and more — but they're scattered, fleeting, and hard to find manually.

**socrates-finds-you** monitors these platforms automatically, scores each signal against a service menu using Claude AI, and delivers a ranked daily report of leads sorted by client value.

**You focus on outreach. The pipeline handles discovery.**

---

## How It Works

```
Platform Scrapers → SQLite → Claude API Matcher → Daily Markdown Report
```

1. **Scrape** — Pulls posts and discussions from 9+ platforms
2. **Match** — Claude API evaluates each signal against the service menu
3. **Report** — Ranked daily markdown report: High / Medium / Low value leads

---

## Platforms Covered

| Priority | Platform | Client Tier | Method |
|----------|----------|-------------|--------|
| ⭐⭐⭐ | LinkedIn | Highest | Playwright |
| ⭐⭐⭐ | Blind | Highest | Playwright |
| ⭐⭐ | Twitter/X | High | tweepy API |
| ⭐⭐ | Hacker News | Mid-High | Firebase API |
| ⭐⭐ | Substack / Medium | Mid-High | RSS |
| ⭐ | 小红书 | Mid | Playwright |
| ⭐ | Reddit (r/PhD, r/datascience, ...) | Mid | PRAW |
| ⭐ | The Grad Cafe | Mid | requests |

---

## Services Matched

The matcher evaluates each signal against this service menu:

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

## Quick Start

```bash
git clone https://github.com/dongzhang84/socrates-finds-you
cd socrates-finds-you
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env   # fill in your credentials
python storage/db.py   # initialize database
```

---

## Usage

```bash
# Full run — all platforms
python main.py

# High-value only — LinkedIn + Blind + Twitter
python main.py --high-value-only

# No browser — Reddit + HN + RSS + Grad Cafe (good for testing)
python main.py --reddit-only

# Skip scraping — re-run matching on existing data
python main.py --no-scrape

# Regenerate report only
python main.py --report-only
```

Reports are saved to `output/report_YYYY-MM-DD.md`.

---

## Project Structure

```
socrates-finds-you/
├── docs/
│   ├── 01-services.md       # Full service menu
│   └── 02-platforms.md      # Platform priority table
├── scrapers/                # One file per platform
├── matcher/
│   └── claude_match.py      # Claude API semantic matching
├── storage/
│   └── db.py                # SQLite read/write layer
├── reporter/
│   └── daily_report.py      # Markdown report generator
├── main.py                  # Entry point
├── requirements.txt
└── .env.example
```

---

## Environment Variables

```bash
ANTHROPIC_API_KEY=        # Claude API
LINKEDIN_EMAIL=           # Personal LinkedIn account
LINKEDIN_PASSWORD=
BLIND_EMAIL=              # Personal Blind account
BLIND_PASSWORD=
TWITTER_BEARER_TOKEN=     # Twitter API v2
REDDIT_CLIENT_ID=         # Reddit app credentials
REDDIT_CLIENT_SECRET=
REDDIT_USER_AGENT=socrates-finds-you/1.0
XIAOHONGSHU_PHONE=        # 小红书 personal account
XIAOHONGSHU_PASSWORD=
```

See `.env.example` for full template.

> ⚠️ All credentials stay local. This tool is never deployed to a server.

---

## Cost

~$1–6/month (Claude API only). All platform scrapers are free.

---

## License

MIT
