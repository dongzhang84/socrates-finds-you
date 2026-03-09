# socrates-finds-you — Implementation Guide

**Status**: 🔧 In Progress  
**Repo**: https://github.com/dongzhang84/socrates-finds-you  
**Last Updated**: March 2026

> 这是一个纯本地运行的个人工具，无需 Auth、无需 Stripe、无需部署。
> Phase 顺序严格按照 `docs/02-platforms.md` 的客群价值排序，从高净值到低付费意愿。
> 所有标准模块参照 `indie-product-playbook/stack/STANDARD.md`。

---

## 1. Tech Stack

| Layer | Choice | Notes |
|-------|--------|-------|
| Language | Python 3.11+ | venv 隔离 |
| Browser Automation | Playwright (sync) | LinkedIn, Blind, 小红书 |
| Reddit API | PRAW | 官方 API，稳定 |
| HN API | Firebase REST API | 公开，无需 auth |
| Twitter/X API | tweepy | 需要 API key，有成本 |
| RSS | feedparser | Substack / Medium |
| AI Matching | Claude API (claude-sonnet) | 语义匹配服务需求 |
| Storage | SQLite (local) | 无需服务器，轻量 |
| Output | Markdown report | 每日生成到 output/ |
| Runtime | 本地手动或 cron | 不部署，不上云 |

---

## 2. 项目目录结构

```
socrates-finds-you/
├── .github/
│   └── workflows/
│       ├── sprint-report.yml       ← 标准配置，从 playbook 复制
│       └── notify-playbook.yml     ← 推送 sprint summary 到 playbook
├── docs/
│   ├── 01-services.md              ← Dong Zhang 服务清单
│   └── 02-platforms.md             ← 平台优先级表（Phase 顺序依据）
├── ideas/
│   └── proposal.md                 ← 项目 proposal
├── scrapers/
│   ├── linkedin.py                 ← Phase 2: LinkedIn (Playwright)
│   ├── blind.py                    ← Phase 3: Blind (Playwright)
│   ├── twitter.py                  ← Phase 4: Twitter/X (tweepy)
│   ├── hackernews.py               ← Phase 5: HN (Firebase API)
│   ├── rss.py                      ← Phase 6: Substack / Medium (RSS)
│   ├── xiaohongshu.py              ← Phase 7: 小红书 (Playwright)
│   ├── reddit.py                   ← Phase 8: Reddit (PRAW)
│   ├── gradcafe.py                 ← Phase 9: The Grad Cafe (scraper)
│   └── utils.py                    ← 共用工具函数
├── matcher/
│   └── claude_match.py             ← Claude API 语义匹配
├── storage/
│   └── db.py                       ← SQLite 读写层
├── reporter/
│   └── daily_report.py             ← Markdown 报告生成
├── scripts/
│   └── extract-sprint-summary.py   ← GitHub Actions 用
├── output/                         ← 每日报告（gitignored）
├── data/
│   └── signals.db                  ← SQLite 数据库（gitignored）
├── main.py                         ← 唯一入口
├── requirements.txt
├── .env
├── .env.example
├── .gitignore
├── SPRINT.md
└── README.md
```

---

## 3. 环境变量

```bash
# .env（从 .env.example 复制，填入真实值，永远不提交到 repo）

# Claude API
ANTHROPIC_API_KEY=sk-ant-...

# LinkedIn — 个人账号
LINKEDIN_EMAIL=...
LINKEDIN_PASSWORD=...

# Blind — 个人账号
BLIND_EMAIL=...
BLIND_PASSWORD=...

# Twitter/X API — 从 developer.twitter.com 申请
TWITTER_BEARER_TOKEN=...

# Reddit（PRAW）— 从 reddit.com/prefs/apps 申请
REDDIT_CLIENT_ID=...
REDDIT_CLIENT_SECRET=...
REDDIT_USER_AGENT=socrates-finds-you/1.0

# 小红书 — 个人账号（Playwright 登录用）
XIAOHONGSHU_PHONE=...
XIAOHONGSHU_PASSWORD=...
```

> ⚠️ `.env` 永远不进 repo。所有凭证只在本地机器上。

**.gitignore 必须包含**：
```
.env
data/
output/
__pycache__/
*.pyc
.venv/
```

---

## 4. 数据库 Schema（SQLite）

```sql
CREATE TABLE IF NOT EXISTS signals (
    id              TEXT PRIMARY KEY,       -- "{platform}:{external_id}"
    platform        TEXT NOT NULL,          -- "linkedin"|"blind"|"twitter"|"hn"|"rss"|"xiaohongshu"|"reddit"|"gradcafe"
    external_id     TEXT NOT NULL,
    url             TEXT NOT NULL,
    title           TEXT NOT NULL,
    body            TEXT,
    author          TEXT,
    subreddit       TEXT,                   -- reddit only
    posted_at       DATETIME,
    scraped_at      DATETIME DEFAULT CURRENT_TIMESTAMP,

    -- 匹配结果
    matched         BOOLEAN DEFAULT FALSE,
    service_match   TEXT,
    client_tier     TEXT,                   -- "high" | "medium" | "low"
    confidence      TEXT,                   -- "high" | "medium" | "low"
    reasoning       TEXT,

    -- 追踪
    included_in_report  BOOLEAN DEFAULT FALSE,
    actioned            BOOLEAN DEFAULT FALSE,

    UNIQUE(platform, external_id)
);
```

---

## 5. 平台优先级（Phase 顺序依据）

**Phase 顺序严格按此表，从高净值到低付费意愿。**

| 排名 | 平台 | 客群质量 | 典型需求 | 自动化可行性 |
|------|------|----------|----------|-------------|
| 1 | LinkedIn | 最高 | PhD转行、职场AI upskilling、高收入家长 | 半手动，有风险 |
| 2 | Blind | 最高 | 大厂职场人、高薪专业人士转型焦虑 | 半手动，有反爬 |
| 3 | Twitter/X | 高 | AcademicTwitter PhD转行、职场AI焦虑 | 自动化，有成本 |
| 4 | Hacker News | 中高 | 技术型职场人、AI upskilling | 完全自动化 |
| 5 | Substack / Medium | 中高 | 职场转型、AI学习 | RSS自动化 |
| 6 | 小红书 | 中 | 海外华人PhD、留学生家长 | 半手动 |
| 7 | Reddit r/PhD, r/AskAcademia | 中 | PhD转行 | 完全自动化 |
| 8 | The Grad Cafe | 中 | PhD迷茫期、转型讨论 | 可scrape |
| 9 | Reddit r/datascience, r/ML | 中 | 职场转AI | 完全自动化 |
| 10 | Reddit r/cscareerquestions | 中低 | 大学生、早期职场 | 完全自动化 |
| 11 | Quora | 中低 | 混合，质量参差 | 半自动化 |
| 12 | Medium评论区 | 中低 | AI学习者 | RSS自动化 |
| 13 | Reddit r/learnmachinelearning | 低中 | 大学生，入门 | 完全自动化 |
| 14 | Discord | 低中 | 大学生，学习社群 | 违反ToS，跳过 |
| 15 | Reddit r/SAT, r/ApplyingToCollege | 低 | 高中生，不是付费方 | 完全自动化 |
| 16 | Facebook Groups | 低中 | 家长群，质量不稳定 | 高风险，暂跳过 |
| 17 | Nextdoor | 低 | 本地家长 | 不可行，跳过 |
| 18 | Stack Overflow | 低 | 技术答疑，非付费需求 | 信号少，跳过 |

---

## 6. Claude API 匹配层 — 服务菜单

**HIGH VALUE** — PhD / 职场专业人士（最高付费意愿）
- PhD to Industry Transition Coaching
- AI Career Path Planning
- Applied AI Project Coaching for Career Switchers
- AI Upskilling for Professionals

**MEDIUM VALUE** — 大学生 / 早期职场
- AI / ML Learning Path Coaching
- College-Level STEM Tutoring
- Research / Independent Project Coaching

**LOWER VALUE** — 高中生 / 家长
- AI Project Mentorship for High School Students
- AP / SAT / ACT Math Tutoring
- AI Literacy for Students

---

## 📋 Build Phases

---

### Phase 1: Project Setup + SQLite Storage

**Goal**: 项目结构、依赖、数据库初始化完毕。

**Setup**:
```bash
git clone https://github.com/dongzhang84/socrates-finds-you
cd socrates-finds-you
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
# 填入 .env
python storage/db.py   # 初始化数据库
```

**requirements.txt**:
```
anthropic
playwright
praw
tweepy
feedparser
requests
python-dotenv
```

---

**CC Prompt 1 — SQLite 存储层:**

```
Create storage/db.py for socrates-finds-you.

Local SQLite database. Database path: data/signals.db
Create the data/ directory if it doesn't exist.

Export these functions:

init_db()
  Creates signals table if not exists. Schema:
    id TEXT PRIMARY KEY ("{platform}:{external_id}")
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

save_signals(signals: list[dict]) → int
  INSERT OR IGNORE. Returns count of newly inserted rows.
  Log: [db] Saved {N} new signals (skipped {M} duplicates)

get_unmatched(limit: int = 200) → list[dict]
  WHERE matched=FALSE ORDER BY scraped_at DESC LIMIT limit

update_match_result(id, matched, service_match, client_tier, confidence, reasoning)
  UPDATE signals SET matched=?, service_match=?, ... WHERE id=?

get_report_candidates() → list[dict]
  WHERE matched=TRUE AND included_in_report=FALSE
  Sort in Python after fetch: high → medium → low

mark_included_in_report(ids: list[str])
  UPDATE signals SET included_in_report=TRUE WHERE id IN (...)

Use sqlite3 stdlib only. Call init_db() under if __name__ == '__main__'.
```

**Test**: `python storage/db.py` → creates `data/signals.db` with no errors.

---

### Phase 2: LinkedIn Scraper (Playwright) ⭐ 最高价值

**Goal**: 抓取 LinkedIn 公开帖子。客群质量最高。

> ⚠️ LinkedIn 反爬最强。必须 headless=False。每次最多 20 条。每天最多一次。

---

**CC Prompt 2 — LinkedIn scraper:**

```
Create scrapers/linkedin.py for socrates-finds-you.

Use Playwright sync API. headless=False required — LinkedIn blocks headless browsers.

Export: scrape_linkedin(keywords: list[str], max_posts: int = 20) → list[dict]

Logic:
1. Load LINKEDIN_EMAIL and LINKEDIN_PASSWORD from .env
2. Launch Chromium headless=False
   args: ["--disable-blink-features=AutomationControlled", "--start-maximized"]
3. Navigate to https://www.linkedin.com, fill login form, submit
4. Wait for login (wait_for_url containing "feed", timeout=20000)
5. For each keyword:
   - Navigate to: https://www.linkedin.com/search/results/content/?keywords={urllib.parse.quote(keyword)}&sortBy=DATE_POSTED
   - wait_for_selector(".search-results-container", timeout=10000)
   - Collect visible post cards: text snippet + author + post URL
   - Delay: time.sleep(random.uniform(3.0, 6.0))
6. Deduplicate by URL, limit to max_posts
7. Return list of dicts:
  {
    "platform": "linkedin",
    "external_id": hashlib.md5(url.encode()).hexdigest()[:12],
    "url": post URL,
    "title": first 120 chars of snippet,
    "body": full snippet[:2000],
    "author": author name,
    "subreddit": None,
    "posted_at": None   # LinkedIn doesn't expose exact timestamps in search
  }

Default keywords (from main.py):
  ["PhD career transition", "leaving academia", "learn machine learning",
   "AI mentor", "career change data science", "PhD to industry",
   "machine learning career", "data science transition"]

Wrap all in try/except — return empty list on total failure, log error.
Log: [linkedin] {N} posts scraped
```

**Test**:
```bash
python -c "from scrapers.linkedin import scrape_linkedin; posts = scrape_linkedin(['PhD career transition'], 5); print(len(posts), 'posts')"
```

---

### Phase 3: Blind Scraper (Playwright) ⭐ 最高价值

**Goal**: 抓取 Blind Career / Job Search 版块。大厂职场人聚集地。

> ⚠️ 每天最多运行一次。加随机延迟。首次登录可能有 CAPTCHA，手动解一次后可复用 session。

---

**CC Prompt 3 — Blind scraper:**

```
Create scrapers/blind.py for socrates-finds-you.

Use Playwright sync API.

Export: scrape_blind(max_posts: int = 30) → list[dict]

Logic:
1. Load BLIND_EMAIL and BLIND_PASSWORD from .env
2. Launch Chromium headless=False
   args: ["--disable-blink-features=AutomationControlled"]
3. Navigate to https://www.teamblind.com
4. Fill login form and submit
5. Wait for feed: wait_for_selector("[data-testid='feed']" or similar, timeout=15000)
6. Navigate to these sections one by one:
   - /topics/Career
   - /topics/Job-Search
   - /topics/Career-Advice
   - /topics/AI-Machine-Learning
7. For each section: scroll once (page.evaluate("window.scrollBy(0, 1500)")),
   collect post cards (title + URL + timestamp)
8. Deduplicate by URL, limit to max_posts total
9. For each post: navigate to URL, extract full body text, go back
   Delay: time.sleep(random.uniform(1.5, 3.5)) between posts
10. Return list of dicts:
  {
    "platform": "blind",
    "external_id": slug extracted from URL,
    "url": full post URL,
    "title": title text,
    "body": body text[:2000],
    "author": author if visible else "",
    "subreddit": None,
    "posted_at": parsed timestamp or None
  }

Filter: skip posts older than 48 hours.
Wrap all in try/except — return partial results on failure.
Log: [blind] {N} posts scraped
```

**Test**:
```bash
python -c "from scrapers.blind import scrape_blind; posts = scrape_blind(3); print(len(posts), 'posts')"
```

---

### Phase 4: Twitter/X Scraper (tweepy) ⭐ 高价值

**Goal**: 抓取 AcademicTwitter 圈子里的转行、AI 学习讨论。

> ⚠️ Twitter API v2 免费 tier 有限制（每月 500k reads）。需要申请 developer account。

---

**CC Prompt 4 — Twitter/X scraper:**

```
Create scrapers/twitter.py for socrates-finds-you.

Use tweepy with Twitter API v2 Bearer Token.
Install: pip install tweepy
Load TWITTER_BEARER_TOKEN from .env.

Export: scrape_twitter(queries: list[str], max_per_query: int = 50) → list[dict]

Logic:
1. Initialize tweepy.Client(bearer_token=TWITTER_BEARER_TOKEN)
2. For each query string:
   - Use client.search_recent_tweets(
       query=f"{query} -is:retweet lang:en",
       max_results=min(max_per_query, 100),
       tweet_fields=["created_at", "author_id", "text", "public_metrics"],
       expansions=["author_id"],
       user_fields=["username"]
     )
   - Filter: skip tweets older than 48 hours
   - Delay: time.sleep(2) between queries (rate limit respect)
3. Deduplicate by tweet id
4. Return list of dicts:
  {
    "platform": "twitter",
    "external_id": str(tweet.id),
    "url": f"https://twitter.com/i/web/status/{tweet.id}",
    "title": tweet.text[:120],
    "body": tweet.text[:2000],
    "author": username from expansions,
    "subreddit": None,
    "posted_at": tweet.created_at.isoformat()
  }

Default queries (from main.py):
  ["PhD leaving academia", "PhD to industry", "academic to industry transition",
   "learning machine learning career", "AI career change",
   "SAT tutor math", "AP calculus help", "STEM mentor high school"]

Wrap each query in try/except. Log: [twitter] {N} tweets fetched
```

**Test**:
```bash
python -c "from scrapers.twitter import scrape_twitter; posts = scrape_twitter(['PhD leaving academia'], 10); print(len(posts), 'tweets')"
```

---

### Phase 5: Hacker News Scraper (Firebase API) ⭐ 中高价值

**Goal**: HN 技术圈，完全免费，无需 auth。

---

**CC Prompt 5 — HN scraper:**

```
Create scrapers/hackernews.py for socrates-finds-you.

Use HN public Firebase REST API. No auth needed.

Export: scrape_hn(limit: int = 100) → list[dict]

Logic:
- GET https://hacker-news.firebaseio.com/v0/newstories.json → list of IDs
- Take first {limit} IDs
- Fetch each: https://hacker-news.firebaseio.com/v0/item/{id}.json
- Use concurrent.futures.ThreadPoolExecutor(max_workers=10)
- Filter: None/deleted, type != "story", score < 2, older than 48h, no title
- Strip HTML from text field using html.parser (stdlib)
- Return list of dicts:
  {
    "platform": "hn",
    "external_id": str(item["id"]),
    "url": f"https://news.ycombinator.com/item?id={item['id']}",
    "title": item["title"],
    "body": cleaned_text[:2000],
    "author": item.get("by", ""),
    "subreddit": None,
    "posted_at": datetime.utcfromtimestamp(item["time"]).isoformat()
  }

Log: [hn] {N} stories fetched
```

**Test**:
```bash
python -c "from scrapers.hackernews import scrape_hn; posts = scrape_hn(20); print(len(posts), 'stories')"
```

---

### Phase 6: RSS Scraper (Substack / Medium) ⭐ 中高价值

**Goal**: 订阅职场转型、AI 学习类 newsletter 的评论和文章。

---

**CC Prompt 6 — RSS scraper:**

```
Create scrapers/rss.py for socrates-finds-you.

Install: pip install feedparser

Export: scrape_rss(feeds: list[str], max_age_hours: int = 48) → list[dict]

Logic:
- For each feed URL: feedparser.parse(url)
- Filter entries older than max_age_hours
- Strip HTML from entry.summary using html.parser
- Return list of dicts:
  {
    "platform": "rss",
    "external_id": entry.get("id") or hashlib.md5(entry.get("link","").encode()).hexdigest()[:12],
    "url": entry.get("link", ""),
    "title": entry.get("title", ""),
    "body": cleaned_summary[:2000],
    "author": entry.get("author", ""),
    "subreddit": None,
    "posted_at": entry.get("published", None)
  }

Handle per-feed errors with try/except.
Log: [rss] {feed_url}: {N} entries fetched

Default feeds (from main.py):
  ["https://every.to/feed",
   "https://www.lennysnewsletter.com/feed",
   "https://www.oneusefulthing.org/feed"]
```

---

### Phase 7: 小红书 Scraper (Playwright) ⭐ 中价值

**Goal**: 海外华人 PhD、留学生家长圈子。

> ⚠️ 小红书反爬中等。需要手机号登录。建议 headless=False。

---

**CC Prompt 7 — 小红书 scraper:**

```
Create scrapers/xiaohongshu.py for socrates-finds-you.

Use Playwright sync API.

Export: scrape_xiaohongshu(keywords: list[str], max_posts: int = 20) → list[dict]

Logic:
1. Load XIAOHONGSHU_PHONE and XIAOHONGSHU_PASSWORD from .env
2. Launch Chromium headless=False
3. Navigate to https://www.xiaohongshu.com
4. Handle login flow (phone + password or QR code)
5. For each keyword:
   - Use search: https://www.xiaohongshu.com/search_result?keyword={urllib.parse.quote(keyword)}
   - Collect post cards: title + URL
   - time.sleep(random.uniform(2.0, 4.0))
6. Click into each post to get body text, limit to max_posts total
7. Return list of dicts:
  {
    "platform": "xiaohongshu",
    "external_id": slug from URL,
    "url": full post URL,
    "title": title[:120],
    "body": body[:2000],
    "author": author name,
    "subreddit": None,
    "posted_at": timestamp if available else None
  }

Default keywords (from main.py):
  ["PhD转行", "留学生找工作", "AI学习", "数学辅导", "SAT备考", "美国读博"]

Wrap all in try/except. Log: [xiaohongshu] {N} posts scraped
```

---

### Phase 8: Reddit Scraper (PRAW)

**Goal**: PRAW 官方 API，覆盖 PhD 转行、职场 AI、高中生等多个 subreddit。

---

**CC Prompt 8 — Reddit scraper:**

```
Create scrapers/reddit.py for socrates-finds-you.

Use PRAW with REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT from .env.

Export: scrape_reddit(subreddits: list[str], limit_per_sub: int = 50) → list[dict]

Logic:
- reddit = praw.Reddit(..., read_only=True)
- For each subreddit: subreddit.new(limit=limit_per_sub)
- Filter: older than 48h, stickied, body is "[removed]" or "[deleted]"
- Return list of dicts:
  {
    "platform": "reddit",
    "external_id": f"t3_{submission.id}",
    "url": f"https://reddit.com{submission.permalink}",
    "title": submission.title,
    "body": submission.selftext[:2000],
    "author": str(submission.author),
    "subreddit": submission.subreddit.display_name,
    "posted_at": datetime.utcfromtimestamp(submission.created_utc).isoformat()
  }

Wrap each subreddit in try/except.
Log: [reddit] r/{subreddit}: {N} posts | Total: {N} posts

Subreddits by tier (pass from main.py, in priority order):
  TIER_HIGH:   ["PhD", "AskAcademia", "datascience", "MachineLearning"]
  TIER_MEDIUM: ["cscareerquestions", "learnmachinelearning", "GradSchool"]
  TIER_LOW:    ["SAT", "ApplyingToCollege", "learnpython"]
```

**Test**:
```bash
python -c "from scrapers.reddit import scrape_reddit; posts = scrape_reddit(['PhD'], 10); print(len(posts), 'posts')"
```

---

### Phase 9: The Grad Cafe Scraper

**Goal**: PhD 群体转型讨论密集，和 Reddit r/PhD 并列。

---

**CC Prompt 9 — The Grad Cafe scraper:**

```
Create scrapers/gradcafe.py for socrates-finds-you.

Use requests + html.parser (stdlib). No auth needed.

Export: scrape_gradcafe(max_posts: int = 30) → list[dict]

Logic:
1. GET https://forum.thegradcafe.com/forum/18-career-advice/ (Career Advice section)
   Headers: {"User-Agent": "Mozilla/5.0"}
2. Parse thread list with html.parser — extract thread titles + URLs
3. Filter threads older than 7 days (Grad Cafe moves slower than Reddit)
4. For each thread URL: GET page, extract first post body
   time.sleep(random.uniform(1.0, 2.5)) between requests
5. Limit to max_posts
6. Return list of dicts:
  {
    "platform": "gradcafe",
    "external_id": slug from URL,
    "url": full thread URL,
    "title": thread title,
    "body": first post body[:2000],
    "author": OP username,
    "subreddit": None,
    "posted_at": parsed date or None
  }

Wrap all in try/except. Log: [gradcafe] {N} threads scraped
```

---

### Phase 10: Claude API Matching Layer

**Goal**: 语义匹配，判断每条信号对应哪个服务、客群价值高低。

---

**CC Prompt 10 — Claude matcher:**

```
Create matcher/claude_match.py for socrates-finds-you.

Use Anthropic Python SDK. Load ANTHROPIC_API_KEY from .env.

Export: match_signals(signals: list[dict]) → list[dict]
  Input: list of signal dicts (id, title, body, platform, subreddit)
  Output: same list + matched, service_match, client_tier, confidence, reasoning

Process in batches of 10. Model: claude-sonnet-4-5

System prompt:
"You are a matching assistant for Dong Zhang, Ph.D. — a STEM and AI mentor.

He offers these services:

HIGH VALUE (PhD students, professionals):
- PhD to Industry Transition Coaching
- AI Career Path Planning
- Applied AI Project Coaching for Career Switchers
- AI Upskilling for Professionals

MEDIUM VALUE (college students, early-career):
- AI / ML Learning Path Coaching
- College-Level STEM Tutoring
- Research / Independent Project Coaching

LOWER VALUE (high school students, parents):
- AI Project Mentorship for High School Students
- AP / SAT / ACT Math Tutoring
- AI Literacy for Students"

User prompt per batch:
"Evaluate these posts. For each return:
- matched: true if there is a real learning/coaching/transition need
- service_match: specific service name from the list (or null)
- client_tier: 'high', 'medium', or 'low'
- confidence: 'high', 'medium', or 'low'
- reasoning: one sentence max

Posts:
{json.dumps([{"id": s["id"], "title": s["title"], "body": (s.get("body") or "")[:600], "platform": s["platform"], "subreddit": s.get("subreddit")} for s in batch])}

Return a JSON array only. No other text."

Strip ```json fences before json.loads().
Handle parse errors: log and skip batch.
Log: [matcher] Batch {N}: {M}/{K} matched
Log: [matcher] Total: {matched}/{total} matched
```

**Test**:
```bash
python -c "
from matcher.claude_match import match_signals
test = [{'id': 'test:1', 'title': 'Just finished Physics PhD, completely lost on how to break into ML', 'body': 'Been in academia 6 years, no idea how to position myself for industry roles', 'platform': 'reddit', 'subreddit': 'PhD'}]
print(match_signals(test))
"
```

---

### Phase 11: Daily Report Generator

**Goal**: 生成可操作的每日 Markdown 报告，按客群价值排序。

---

**CC Prompt 11 — Report generator:**

```
Create reporter/daily_report.py for socrates-finds-you.

Export: generate_report() → str
  Saves to output/report_YYYY-MM-DD.md (create output/ if not exists)

Logic:
1. storage.db.get_report_candidates()
2. Split by client_tier, sort: high → medium → low (in Python, not SQL)
3. Generate markdown:

# socrates-finds-you — Daily Report {YYYY-MM-DD}

**{total} leads matched** — {H} high / {M} medium / {L} low value

---

## 🔴 High Value (PhD / Professionals)

### 1. {title}
- **Platform**: {platform}{" · r/" + subreddit if subreddit else ""}
- **Service**: {service_match}
- **Confidence**: {confidence}
- **Why**: {reasoning}
- **Link**: {url}
- **Posted**: {posted_at or "unknown"}

---

## 🟡 Medium Value (College / Early Career)
[same format]

---

## 🟢 Lower Value (High School / Students)
[same format]

---
*Generated {UTC timestamp}. Mark leads as actioned in signals.db after review.*

4. Save to output/report_{date}.md
5. mark_included_in_report(all included ids)
6. If zero signals: generate "no leads today" report, still save
Log: [reporter] Saved: output/report_{date}.md ({N} leads)
```

---

### Phase 12: Main Entry Point

**Goal**: 单一命令跑完全流程，scrapers 按平台价值顺序执行。

---

**CC Prompt 12 — main.py:**

```
Create main.py for socrates-finds-you.

`python main.py` runs everything end-to-end.

Scraper execution order follows platform priority (high value first):
1. storage.db.init_db()
2. Scrapers (in this order):
   a. linkedin.scrape_linkedin(keywords=[...])    — 最高价值
   b. blind.scrape_blind(30)                      — 最高价值
   c. twitter.scrape_twitter(queries=[...])        — 高价值
   d. hackernews.scrape_hn(100)                   — 中高价值
   e. rss.scrape_rss(feeds=[...])                 — 中高价值
   f. xiaohongshu.scrape_xiaohongshu(keywords=[...]) — 中价值
   g. reddit.scrape_reddit(subreddits=[...])       — 中价值
   h. gradcafe.scrape_gradcafe(30)                — 中价值

   Wrap b, c, f in try/except — these are most likely to fail.
   Wrap a in try/except with clear message if LinkedIn blocks.

3. storage.db.save_signals(all_signals)
4. unmatched = storage.db.get_unmatched(limit=150)
5. If unmatched: run match_signals(), update_match_result() for each
6. generate_report()
7. Print total runtime

argparse flags:
  --high-value-only   Run LinkedIn + Blind + Twitter only (skip lower-tier scrapers)
  --no-browser        Skip all Playwright scrapers (LinkedIn, Blind, 小红书)
  --reddit-only       Run Reddit + HN + RSS + Grad Cafe only (no Playwright, no Twitter API)
  --no-scrape         Skip scraping, re-run matching + report on existing data
  --report-only       Skip scraping and matching, just regenerate report

Log: [main] Done in {elapsed:.1f}s — {N} new signals, {M} matched, report saved
```

**Run options**:
```bash
python main.py                  # 全量，所有平台
python main.py --high-value-only  # 只跑 LinkedIn + Blind + Twitter
python main.py --no-browser       # 跳过 Playwright，适合 cron / 无 GUI 环境
python main.py --reddit-only      # 只跑免费无风险的平台，适合测试
python main.py --no-scrape        # 重新匹配已抓取的数据
python main.py --report-only      # 只重新生成报告
```

---

## 7. Sprint Tracking

**已完成配置（socrates-finds-you）**：
- `.github/workflows/sprint-report.yml` ✅
- `.github/workflows/notify-playbook.yml` ✅
- `SPRINT.md` ✅
- `scripts/extract-sprint-summary.py` ✅
- `PLAYBOOK_TOKEN` secret 已设置 ✅

每次 push 到 main → 自动更新 `indie-product-playbook` 的 sprint 记录。

---

## 8. 运行成本估算

| 组件 | 费用 |
|------|------|
| Claude API (~150 signals × ~500 tokens/run) | ~$0.05–0.20/run |
| Twitter API v2 (免费 tier 500k reads/月) | 免费（量少时） |
| Reddit API (PRAW) | 免费 |
| HN Firebase API | 免费 |
| RSS | 免费 |
| LinkedIn / Blind / 小红书（个人账号） | 免费 |
| SQLite 本地存储 | 免费 |
| **月度估算（每天运行）** | **~$1–6/月** |

---

## 9. 常见坑

| 坑 | 原因 | 解法 |
|----|------|------|
| LinkedIn 检测 headless | 自动化检测 | headless=False + `--disable-blink-features=AutomationControlled` |
| Blind 首次登录 CAPTCHA | 新 browser profile | headless=False 手动解一次，之后保存 browser state |
| Twitter API 429 | 超过 rate limit | 每个 query 之间 time.sleep(2)，减少 max_per_query |
| Claude 返回带 ```json 的响应 | Claude 有时加围栏 | strip 后再 json.loads() |
| SQLite 排序错乱 | SQL 按字母排 high/low/medium | fetch 后在 Python sort |
| LinkedIn posted_at 为 None | 搜索结果不暴露时间戳 | 用 scraped_at 替代排序 |
| 小红书需要手机验证码 | 新设备登录 | 第一次手动登录后保存 browser state |
| Playwright 在 cron 无 GUI | headless=False 在无 display 环境报错 | cron 里用 --no-browser flag |
| 信号量太多导致 Claude 超时 | 一次送太多 | limit=150，batch size=10 |
| Grad Cafe 结构变化 | HTML 结构随时可能改 | 用 try/except，定期检查 scraper 是否还能跑 |

---

## 10. 新项目 Checklist

```
□ git clone + cd socrates-finds-you
□ python -m venv .venv && source .venv/bin/activate
□ pip install -r requirements.txt
□ playwright install chromium
□ cp .env.example .env → 填入所有凭证
□ python storage/db.py → 确认 data/signals.db 创建成功
□ python main.py --reddit-only → 先跑最稳定的平台验证全流程
□ 检查 output/ 有报告生成，格式正确
□ python main.py --high-value-only → 验证 LinkedIn + Blind + Twitter
□ python main.py → 全量跑一次
□ 确认 .gitignore 包含 .env / data/ / output/
□ SPRINT.md 存在，GitHub Actions 已配置
□ indie-product-playbook/ideas/README.md 表格里有 socrates-finds-you 行 ✅
□ PLAYBOOK_TOKEN secret 已配置 ✅
```

---

## 🔄 Change Log

| Date | Version | Changes |
|------|---------|---------|
| 2026-03 | 1.0 | 初版 |
| 2026-03 | 2.0 | 按 STANDARD.md 重构，统一格式 |
| 2026-03 | 3.0 | Phase 顺序改为按客群价值排序（对照 02-platforms.md）；新增 Twitter/X、小红书、The Grad Cafe scraper；main.py 新增 --high-value-only 和 --no-browser flag |
