# socrates-finds-you — Implementation Guide

**Status**: 🔧 In Progress  
**Repo**: https://github.com/dongzhang84/socrates-finds-you  
**Last Updated**: March 2026

---

## 📊 Project Overview

socrates-finds-you is a personal automated pipeline that monitors multiple platforms for people who need STEM tutoring, AI mentorship, or PhD/career coaching — and matches those signals to the right service tier. It outputs a daily markdown report of leads, ranked by client value.

**This is a personal tool. No auth, no payments, no SaaS.**

**Stack**: Python + Playwright + PRAW (Reddit API) + Claude API + SQLite + Markdown reports

---

## 🏗️ Architecture

```
Platform Scrapers (Playwright / API)
        ↓
Raw data → SQLite database
        ↓
Claude API semantic matching layer
        ↓
Daily markdown report (output/)
```

**Scrapers**: Playwright (Blind, LinkedIn), PRAW (Reddit), HN Firebase API (Hacker News), RSS (Substack/Medium)  
**Matching**: Claude API (claude-sonnet) — semantic scoring against service menu  
**Storage**: SQLite (local, lightweight, no server needed)  
**Output**: Markdown report, generated locally  
**Runtime**: Local machine, run manually or via cron  

---

## 📁 Project Structure

```
socrates-finds-you/
├── docs/
│   ├── 01-services.md              # Service menu (Dong Zhang)
│   └── 02-platforms.md             # Platform priority table
├── ideas/
│   └── proposal.md                 # Project proposal
├── scrapers/
│   ├── blind.py                    # Blind scraper (Playwright)
│   ├── linkedin.py                 # LinkedIn scraper (Playwright)
│   ├── reddit.py                   # Reddit scraper (PRAW)
│   ├── hackernews.py               # HN scraper (Firebase API)
│   ├── rss.py                      # Substack / Medium RSS
│   └── utils.py                    # Shared utilities
├── matcher/
│   └── claude_match.py             # Claude API semantic matcher
├── storage/
│   └── db.py                       # SQLite read/write
├── reporter/
│   └── daily_report.py             # Markdown report generator
├── output/                         # Daily reports (gitignored)
├── data/
│   └── signals.db                  # SQLite database (gitignored)
├── main.py                         # Entry point — run everything
├── requirements.txt
├── .env.example
└── README.md
```

---

## 🗄️ Database Schema (SQLite)

```sql
CREATE TABLE IF NOT EXISTS signals (
    id              TEXT PRIMARY KEY,       -- platform:externalId
    platform        TEXT NOT NULL,          -- "blind" | "linkedin" | "reddit" | "hn" | "rss"
    external_id     TEXT NOT NULL,
    url             TEXT NOT NULL,
    title           TEXT NOT NULL,
    body            TEXT,
    author          TEXT,
    subreddit       TEXT,                   -- reddit only
    posted_at       DATETIME,
    scraped_at      DATETIME DEFAULT CURRENT_TIMESTAMP,

    -- Matching results
    matched         BOOLEAN DEFAULT FALSE,
    service_match   TEXT,                   -- matched service name
    client_tier     TEXT,                   -- "high" | "medium" | "low"
    confidence      TEXT,                   -- "high" | "medium" | "low"
    reasoning       TEXT,

    -- Tracking
    included_in_report  BOOLEAN DEFAULT FALSE,
    actioned            BOOLEAN DEFAULT FALSE,  -- manually marked after review

    UNIQUE(platform, external_id)
);
```

---

## 🔑 Environment Variables

```bash
# .env (copy from .env.example)

# Claude API
ANTHROPIC_API_KEY=sk-ant-...

# Reddit (PRAW) — get from reddit.com/prefs/apps
REDDIT_CLIENT_ID=...
REDDIT_CLIENT_SECRET=...
REDDIT_USER_AGENT=socrates-finds-you/1.0

# Blind — your personal login
BLIND_EMAIL=...
BLIND_PASSWORD=...

# LinkedIn — your personal login
LINKEDIN_EMAIL=...
LINKEDIN_PASSWORD=...
```

> **Note**: LinkedIn and Blind credentials are yours personally. This tool runs locally only — credentials never leave your machine.

---

## 📋 Build Phases

---

### Phase 1: Project Setup + SQLite Storage ✅

**Goal**: Repo structure, dependencies, database initialized and ready.

**Steps**:
1. Clone repo, create virtual environment
2. Install dependencies (see requirements.txt)
3. Create `.env` from `.env.example`
4. Run `python storage/db.py` to initialize SQLite database

**requirements.txt**:
```
anthropic
playwright
praw
feedparser
requests
python-dotenv
```

**CC Prompt 1 — SQLite storage layer:**

```
Create storage/db.py for socrates-finds-you.

This is a local SQLite database for storing scraped signals and their matching results.

Create a function: init_db() — creates the signals table if it doesn't exist.
Schema:
  id TEXT PRIMARY KEY (format: "{platform}:{external_id}")
  platform TEXT NOT NULL
  external_id TEXT NOT NULL
  url TEXT NOT NULL
  title TEXT NOT NULL
  body TEXT
  author TEXT
  subreddit TEXT
  posted_at DATETIME
  scraped_at DATETIME DEFAULT CURRENT_TIMESTAMP
  matched BOOLEAN DEFAULT FALSE
  service_match TEXT
  client_tier TEXT
  confidence TEXT
  reasoning TEXT
  included_in_report BOOLEAN DEFAULT FALSE
  actioned BOOLEAN DEFAULT FALSE
  UNIQUE(platform, external_id)

Also create:
  save_signals(signals: list[dict]) — insert or ignore (skip duplicates)
  get_unmatched(limit=200) → list[dict]
  update_match_result(id: str, service_match: str, client_tier: str, confidence: str, reasoning: str)
  get_report_candidates(client_tier_filter=None) → list[dict]
    - Returns signals where matched=True and included_in_report=False
    - Optional filter by client_tier ("high", "medium", "low")
    - ORDER BY: high first, then medium, then low
  mark_included_in_report(ids: list[str])

Use sqlite3 from Python standard library. Database path: data/signals.db
```

**Test**: Run `python storage/db.py` → should create `data/signals.db` with no errors.

---

### Phase 2: Reddit Scraper ✅

**Goal**: Scrape Reddit using PRAW (official API). Most reliable scraper, start here.

**Target subreddits by client tier**:

| Tier | Subreddits |
|------|-----------|
| High | r/PhD, r/AskAcademia, r/datascience, r/MachineLearning |
| Medium | r/cscareerquestions, r/learnmachinelearning, r/GradSchool |
| Low | r/SAT, r/ApplyingToCollege, r/learnpython |

---

**CC Prompt 2 — Reddit scraper:**

```
Create scrapers/reddit.py for socrates-finds-you.

Install: praw python-dotenv

Use PRAW (Python Reddit API Wrapper) with credentials from .env:
  REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT

Export: scrape_reddit(subreddits: list[str], limit_per_sub: int = 50) → list[dict]

Logic:
- For each subreddit, fetch `new` posts (limit=limit_per_sub)
- Filter out: posts older than 48 hours, stickied posts, [removed] and [deleted] body
- Return list of dicts with fields:
  platform, external_id, url, title, body, author, subreddit, posted_at

Target subreddits to pass in from main.py:
  High tier: ["PhD", "AskAcademia", "datascience", "MachineLearning"]
  Medium tier: ["cscareerquestions", "learnmachinelearning", "GradSchool"]
  Low tier: ["SAT", "ApplyingToCollege", "learnpython"]

Add try/except around each subreddit so one failure doesn't stop others.
Log: [reddit] r/{subreddit}: {N} posts fetched
```

**Test**:
```bash
python -c "from scrapers.reddit import scrape_reddit; posts = scrape_reddit(['PhD']); print(len(posts), 'posts')"
```

---

### Phase 3: Hacker News Scraper

**Goal**: HN Firebase API — completely open, no auth needed.

---

**CC Prompt 3 — HN scraper:**

```
Create scrapers/hackernews.py for socrates-finds-you.

Use HN's public Firebase API. No auth required.

Export: scrape_hn(limit: int = 100) → list[dict]

Logic:
- GET https://hacker-news.firebaseio.com/v0/newstories.json → list of IDs
- Take first {limit} IDs
- Fetch each: https://hacker-news.firebaseio.com/v0/item/{id}.json
- Batch 10 at a time using concurrent.futures.ThreadPoolExecutor
- Filter out: null/deleted items, type != "story", score < 2, older than 48 hours, no title
- Strip HTML from text field if present (use html.parser)
- Return list of dicts with fields:
  platform="hn", external_id (str of HN id), url, title, body, author, subreddit=None, posted_at

Log: [hn] {N} stories fetched
```

**Test**:
```bash
python -c "from scrapers.hackernews import scrape_hn; posts = scrape_hn(50); print(len(posts), 'stories')"
```

---

### Phase 4: Blind Scraper (Playwright)

**Goal**: Scrape Blind using browser automation. Requires personal login.

> ⚠️ **Note**: Run slowly. Add random delays between actions. Don't scrape more than once per day. Blind has anti-bot detection.

---

**CC Prompt 4 — Blind scraper:**

```
Create scrapers/blind.py for socrates-finds-you.

Use Playwright (sync API) to scrape Blind.

Install: playwright → then run: playwright install chromium

Export: scrape_blind(max_posts: int = 30) → list[dict]

Logic:
1. Launch Chromium (headless=False for debugging, set headless=True once working)
2. Navigate to https://www.teamblind.com
3. Login with BLIND_EMAIL and BLIND_PASSWORD from .env
4. Wait for login to complete (wait for feed element)
5. Navigate to these sections one by one:
   - /topics/Career
   - /topics/Job-Search
   - /topics/Career-Advice
6. For each section: scroll once, collect post cards
7. For each post card: extract title, snippet, URL, author, timestamp
8. Click into each post to get full body text (limit to max_posts total)
9. Add random delay between actions: time.sleep(random.uniform(1.5, 3.5))
10. Return list of dicts with fields:
    platform="blind", external_id (from URL slug), url, title, body, author, subreddit=None, posted_at

Filter out posts older than 48 hours.
Wrap everything in try/except. Log progress.
Log: [blind] {N} posts scraped
```

**Test**:
```bash
python -c "from scrapers.blind import scrape_blind; posts = scrape_blind(5); print(len(posts), 'posts')"
```

---

### Phase 5: LinkedIn Scraper (Playwright)

**Goal**: Scrape public LinkedIn posts. Higher risk — run conservatively.

> ⚠️ **Note**: LinkedIn has stronger anti-bot detection than Blind. Use headless=False. Add longer delays. Limit to 20 posts per run. Do not run more than once per day.

---

**CC Prompt 5 — LinkedIn scraper:**

```
Create scrapers/linkedin.py for socrates-finds-you.

Use Playwright (sync API) to search LinkedIn for relevant public posts.

Export: scrape_linkedin(keywords: list[str], max_posts: int = 20) → list[dict]

Logic:
1. Launch Chromium (headless=False — required for LinkedIn)
2. Navigate to https://www.linkedin.com
3. Login with LINKEDIN_EMAIL and LINKEDIN_PASSWORD from .env
4. For each keyword in keywords list:
   - Use LinkedIn search: https://www.linkedin.com/search/results/content/?keywords={keyword}
   - Collect visible post cards (title/snippet + author + URL)
   - Add delay: time.sleep(random.uniform(3.0, 6.0)) between searches
5. Deduplicate posts by URL
6. Return list of dicts with fields:
   platform="linkedin", external_id (from URL), url, title, body (snippet), author, subreddit=None, posted_at=None

Target keywords to pass from main.py:
  ["PhD career transition", "leaving academia", "learn machine learning", 
   "AI mentor", "career change data science", "PhD to industry"]

Limit total posts to max_posts. Log: [linkedin] {N} posts scraped
Wrap all in try/except — LinkedIn is fragile.
```

---

### Phase 6: Claude API Matching Layer

**Goal**: Send scraped signals to Claude API, match against service menu, score client tier.

---

**CC Prompt 6 — Claude semantic matcher:**

```
Create matcher/claude_match.py for socrates-finds-you.

Use the Anthropic Python SDK with ANTHROPIC_API_KEY from .env.

Export: match_signals(signals: list[dict]) → list[dict]
  Each input dict has: id, title, body, platform, subreddit
  Each output dict adds: matched (bool), service_match, client_tier, confidence, reasoning

Process in batches of 10.
Model: claude-sonnet-4-5 (or latest available)

Use this system prompt:
"You are a matching assistant for Dong Zhang, Ph.D. — a STEM and AI mentor who offers the following services:

HIGH VALUE SERVICES (target: PhD students, professionals, high-income parents):
- PhD to Industry Transition Coaching
- AI Career Path Planning
- Applied AI Project Coaching for Career Switchers
- AI Upskilling for Professionals

MEDIUM VALUE SERVICES (target: college students, early-career professionals):
- AI / ML Learning Path Coaching
- College-Level STEM Tutoring
- Research / Independent Project Coaching

LOWER VALUE SERVICES (target: high school students, parents):
- AI Project Mentorship for High School Students
- AP / SAT / ACT Math Tutoring
- AI Literacy for Students

Your job: evaluate each post and determine if it signals a real need that Dong Zhang can help with."

User prompt per batch:
"Evaluate these posts. For each, return:
- matched: true/false (is there a real learning/coaching/transition need?)
- service_match: which specific service from the list above (or null)
- client_tier: 'high', 'medium', or 'low' (based on likely ability to pay)
- confidence: 'high', 'medium', or 'low'
- reasoning: one sentence

Posts:
{json.dumps([{id, title, body[:600], platform, subreddit} for each post])}

Return only a JSON array. No other text."

Parse response as JSON. Handle parse errors gracefully (skip batch, log error).
Log: [matcher] Processed {N} signals, {M} matched
```

**Test**:
```bash
python -c "
from matcher.claude_match import match_signals
test = [{'id': 'test:1', 'title': 'Just finished PhD in physics, no idea how to get a job in ML', 'body': 'I have been in academia for 6 years and feel completely lost', 'platform': 'reddit', 'subreddit': 'PhD'}]
results = match_signals(test)
print(results)
"
```

---

### Phase 7: Daily Report Generator

**Goal**: Pull matched signals from DB, generate a ranked markdown report.

---

**CC Prompt 7 — Daily report generator:**

```
Create reporter/daily_report.py for socrates-finds-you.

Export: generate_report() → str (markdown string), also saves to output/report_YYYY-MM-DD.md

Logic:
1. Query DB for unreported matched signals (matched=True, included_in_report=False)
   using storage.db.get_report_candidates()
2. Split into three sections: high / medium / low client_tier
3. Generate markdown report

Report format:

# socrates-finds-you — Daily Report {YYYY-MM-DD}

**{total} signals matched** — {high} high / {medium} medium / {low} low value

---

## 🔴 High Value (PhD / Professionals)

### 1. {title}
- **Platform**: {platform} {subreddit if reddit}
- **Service match**: {service_match}
- **Confidence**: {confidence}
- **Why**: {reasoning}
- **Link**: {url}
- **Posted**: {posted_at}

---

## 🟡 Medium Value (College / Early Career)

[same format]

---

## 🟢 Lower Value (High School / Students)

[same format]

---
*Generated at {timestamp}. Mark leads as actioned in signals.db after review.*

4. Save file to output/report_{date}.md
5. Call storage.db.mark_included_in_report(ids) for all included signals
6. Return the markdown string

Log: [reporter] Report saved: output/report_{date}.md ({N} leads)
```

---

### Phase 8: Main Entry Point

**Goal**: Wire everything together into a single command.

---

**CC Prompt 8 — main.py:**

```
Create main.py for socrates-finds-you.

This is the single entry point. Running `python main.py` does everything.

Steps:
1. Load .env (python-dotenv)
2. Init DB (storage.db.init_db())
3. Run scrapers:
   a. Reddit: scrape_reddit(subreddits=[...all tiers...])
   b. HN: scrape_hn(100)
   c. Blind: scrape_blind(30) — wrap in try/except, log if fails
   d. LinkedIn: scrape_linkedin(keywords=[...]) — wrap in try/except, log if fails
4. Combine all results, save to DB: storage.db.save_signals(all_signals)
5. Get unmatched signals: storage.db.get_unmatched(limit=150)
6. Run matcher: matcher.claude_match.match_signals(unmatched)
7. Save match results to DB
8. Generate report: reporter.daily_report.generate_report()
9. Print: "Done. Report saved to output/report_{date}.md"

Add a --reddit-only flag (argparse) to skip Playwright scrapers during testing.
Add a --no-scrape flag to skip scraping and only re-run matching + report on existing data.

Log total runtime at the end.
```

**Run**:
```bash
# Full run
python main.py

# Reddit + HN only (no browser automation)
python main.py --reddit-only

# Re-run matching and report on already-scraped data
python main.py --no-scrape
```

---

### Phase 9: RSS Scraper (Substack + Medium)

**Goal**: Low-effort additional signal source via RSS feeds.

---

**CC Prompt 9 — RSS scraper:**

```
Create scrapers/rss.py for socrates-finds-you.

Install: feedparser

Export: scrape_rss(feeds: list[str], max_age_hours: int = 48) → list[dict]

Logic:
- For each RSS feed URL in feeds list, use feedparser to fetch and parse
- Filter entries older than max_age_hours
- Return list of dicts with fields:
  platform="rss", external_id (from entry.id or entry.link), url, title,
  body (entry.summary, strip HTML), author, subreddit=None, posted_at

Target feeds to pass from main.py:
  Substack newsletters covering AI, career, academia:
  - https://every.to/feed  
  - https://www.lennysnewsletter.com/feed
  - Any relevant academic/career Substacks

Log: [rss] {feed_url}: {N} entries fetched
Handle fetch errors gracefully per feed.
```

---

## ⚙️ Running the Pipeline

**First time setup**:
```bash
git clone https://github.com/dongzhang84/socrates-finds-you
cd socrates-finds-you
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
# Fill in .env with your credentials
python main.py --reddit-only  # test without browser scrapers first
```

**Daily run** (add to crontab):
```bash
# Run every morning at 7am
0 7 * * * cd /path/to/socrates-finds-you && source venv/bin/activate && python main.py
```

**Manual run options**:
```bash
python main.py                  # full run, all scrapers
python main.py --reddit-only    # Reddit + HN only (no Playwright)
python main.py --no-scrape      # re-match and regenerate report only
```

---

## 💰 Cost Estimate

| Service | Cost |
|---------|------|
| Claude API (claude-sonnet) | ~$0.05–0.20 per daily run (150 signals × ~500 tokens) |
| Reddit API (PRAW) | Free |
| HN API | Free |
| Blind / LinkedIn | Free (personal account) |
| Storage (SQLite local) | Free |
| **Total** | **~$1–5/month** |

---

## 🐛 Known Gotchas

**Playwright on LinkedIn**: LinkedIn detects headless browsers. Always use `headless=False`. Add `--disable-blink-features=AutomationControlled` launch arg. If blocked, wait 24h before retrying.

**Blind login flow**: Blind sometimes shows a CAPTCHA on first login from a new browser profile. Run headless=False and solve manually once — then Playwright can reuse the session by saving browser state to a file.

**Claude API JSON parsing**: Claude sometimes adds a markdown code fence around JSON. Strip ` ```json ` and ` ``` ` before `json.loads()`.

**SQLite concurrency**: This is a single-user local tool — no concurrency issues. If you ever add parallel scrapers, use `check_same_thread=False`.

**Reddit rate limits**: PRAW handles rate limiting automatically. Don't worry about it.

**LinkedIn post timestamps**: LinkedIn doesn't always expose exact timestamps on search results. `posted_at` may be None for LinkedIn signals — that's fine, sort by scraped_at instead.

**Signal volume**: Expect 50–150 raw signals per run, 10–30 matched, 3–10 high-value. If volume is too low, add more subreddits. If too noisy, tighten the Claude prompt.

---

## 🔄 Change Log

| Date | Version | Changes |
|------|---------|---------|
| 2026-03 | 0.1 | Initial guide — project setup, all phases drafted |
