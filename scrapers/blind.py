import logging
import os
import random
import re
import time
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

logger = logging.getLogger(__name__)

TOPICS = [
    "/topics/Career",
    "/topics/Job-Search",
    "/topics/Career-Advice",
    "/topics/AI-Machine-Learning",
    "/topics/Tech",
    "/topics/Software-Engineer",
    "/topics/Data-Science",
    "/topics/Artificial-Intelligence",
]

BASE_URL = "https://www.teamblind.com"
CUTOFF_HOURS = 168  # 7 days — Blind channel pages show popular posts, not real-time feed


def _parse_posted_at(text: str) -> str | None:
    """Best-effort parse of Blind timestamps.

    Handles:
      - Relative: "5d", "2h", "30m", "1w"
      - Absolute month-day: "Mar 7", "Feb 28"
    """
    if not text:
        return None
    now = datetime.now(timezone.utc)
    stripped = text.strip()

    # Relative: "5d", "2h ago", "30m", "1w"
    m = re.search(r"(\d+)\s*(s|m|h|d|w)", stripped, re.IGNORECASE)
    if m:
        n, unit = int(m.group(1)), m.group(2).lower()
        delta = {
            "s": timedelta(seconds=n),
            "m": timedelta(minutes=n),
            "h": timedelta(hours=n),
            "d": timedelta(days=n),
            "w": timedelta(weeks=n),
        }.get(unit)
        if delta:
            return (now - delta).isoformat()

    # Absolute month-day: "Mar 7", "Feb 28"
    m = re.match(r"([A-Za-z]{3})\s+(\d{1,2})$", stripped)
    if m:
        try:
            dt = datetime.strptime(f"{m.group(1)} {m.group(2)} {now.year}", "%b %d %Y")
            dt = dt.replace(tzinfo=timezone.utc)
            # If the parsed date is in the future, it must be last year
            if dt > now:
                dt = dt.replace(year=now.year - 1)
            return dt.isoformat()
        except ValueError:
            pass

    return None


def _is_too_old(posted_at: str | None) -> bool:
    if not posted_at:
        return False  # unknown age — keep
    try:
        dt = datetime.fromisoformat(posted_at)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - dt > timedelta(hours=CUTOFF_HOURS)
    except Exception:
        return False


def _slug_from_url(url: str) -> str:
    # e.g. https://www.teamblind.com/post/Title-slug-ABC123 → ABC123 or full path slug
    parts = url.rstrip("/").split("/")
    return parts[-1] if parts else url


def scrape_blind(max_posts: int = 100, debug: bool = False) -> list[dict]:
    email = os.getenv("BLIND_EMAIL")
    password = os.getenv("BLIND_PASSWORD")
    if not email or not password:
        logger.error("[blind] BLIND_EMAIL or BLIND_PASSWORD not set in .env")
        return []

    results: list[dict] = []
    seen_urls: set[str] = set()

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=False,
                args=["--disable-blink-features=AutomationControlled", "--start-maximized"],
            )
            context = browser.new_context(no_viewport=True)
            page = context.new_page()

            # --- Login ---
            # Use domcontentloaded — Blind keeps background XHRs open and never fires 'load'
            page.goto(BASE_URL, wait_until="domcontentloaded")
            time.sleep(2)

            if "/login" in page.url or page.query_selector('input[type="email"], input[name="email"]'):
                # Need to log in
                try:
                    if "/login" not in page.url:
                        page.goto(f"{BASE_URL}/login", wait_until="domcontentloaded")
                        time.sleep(1)
                    page.wait_for_selector('input[type="email"], input[name="email"]', timeout=10000)
                    page.fill('input[type="email"], input[name="email"]', email)
                    page.fill('input[type="password"], input[name="password"]', password)
                    page.click('button[type="submit"]')
                    page.wait_for_load_state("domcontentloaded", timeout=15000)
                    time.sleep(2)
                    # If CAPTCHA present, user must solve it manually — scraper waits up to 60s
                    if "captcha" in page.content().lower() or "verify" in page.url.lower():
                        logger.warning("[blind] CAPTCHA detected — solve manually in the browser window (60s timeout)")
                        page.wait_for_url(lambda u: "login" not in u, timeout=60000)
                except Exception as exc:
                    logger.error("[blind] Login failed: %s", exc)
                    browser.close()
                    return []
            else:
                logger.info("[blind] Already logged in, skipping login form")

            # --- Collect post stubs from topic pages ---
            post_stubs: list[dict] = []  # {url, title, posted_at_raw}

            for topic in TOPICS:
                if len(post_stubs) >= max_posts * 3:  # collect extra, filter later
                    break
                try:
                    page.goto(f"{BASE_URL}{topic}", wait_until="domcontentloaded")
                    time.sleep(2)
                    page.evaluate("window.scrollBy(0, 1500)")
                    time.sleep(1)

                    logger.info("[blind] Page URL: %s", page.url)
                    logger.info("[blind] Page title: %s", page.title())

                    if debug:
                        with open("debug_blind.html", "w", encoding="utf-8") as fh:
                            fh.write(page.content())
                        logger.info("[blind] Debug HTML saved to debug_blind.html")
                        browser.close()
                        return []

                    stubs = page.evaluate("""() => {
                        const results = [];
                        const seen = new Set();
                        // Each post card is an <a href="/post/..."> that wraps the whole card
                        const cards = document.querySelectorAll('a[href*="/post/"]');
                        for (const card of cards) {
                            const url = card.href.split('?')[0];
                            if (!url || seen.has(url)) continue;

                            // Title: data-testid attribute (reliable as of 2026-03)
                            const titleEl = card.querySelector('[data-testid="popular-article-preview-title"]');
                            const title = (titleEl ? titleEl.innerText : card.innerText).trim().split('\\n')[0];
                            if (!title || title.length < 5) continue;

                            // Timestamp: <p class="text-xs text-gray-600"> e.g. "6d", "Mar 7"
                            const tsEl = card.querySelector('p.text-gray-600');
                            const postedAt = tsEl ? tsEl.innerText.trim() : '';

                            seen.add(url);
                            results.push({ url, title, postedAt });
                        }
                        return results;
                    }""")

                    post_stubs.extend(stubs)
                    logger.info("[blind] %s: %d stubs collected", topic, len(stubs))
                    time.sleep(random.uniform(1.5, 3.0))

                except Exception as exc:
                    logger.warning("[blind] Failed on topic %s: %s", topic, exc)
                    continue

            # --- Deduplicate stubs and filter by age ---
            unique_stubs: list[dict] = []
            seen_stub_urls: set[str] = set()
            for stub in post_stubs:
                url = stub["url"]
                if url in seen_stub_urls:
                    continue
                posted_at = _parse_posted_at(stub.get("postedAt", ""))
                if _is_too_old(posted_at):
                    continue
                seen_stub_urls.add(url)
                unique_stubs.append({**stub, "posted_at": posted_at})

            # --- Fetch full body for each post ---
            for stub in unique_stubs:
                if len(results) >= max_posts:
                    break
                url = stub["url"]
                if url in seen_urls:
                    continue
                try:
                    page.goto(url, wait_until="domcontentloaded")
                    time.sleep(1)

                    data = page.evaluate("""() => {
                        // Body: largest text block in the post content area
                        // Blind wraps the OP body in an article or a section with role=main
                        const candidates = [
                            document.querySelector('article'),
                            document.querySelector('[role="main"]'),
                            document.querySelector('main'),
                        ];
                        let body = '';
                        for (const container of candidates) {
                            if (!container) continue;
                            const text = container.innerText.trim();
                            if (text.length > body.length) body = text;
                        }
                        // Author: profile link or username element
                        const authorEl = document.querySelector(
                            'a[href*="/profile/"], [data-testid="author"], [class*="author"], [class*="username"]'
                        );
                        const author = authorEl ? authorEl.innerText.trim() : '';
                        return { body, author };
                    }""")

                    body = (data.get("body") or "").strip()
                    author = (data.get("author") or "").strip()
                    slug = _slug_from_url(url)
                    title = stub.get("title") or slug

                    seen_urls.add(url)
                    results.append({
                        "platform": "blind",
                        "external_id": slug,
                        "url": url,
                        "title": title[:120],
                        "body": body[:2000],
                        "author": author,
                        "subreddit": None,
                        "posted_at": stub.get("posted_at"),
                    })

                    time.sleep(random.uniform(1.5, 3.5))

                except Exception as exc:
                    logger.warning("[blind] Failed fetching post %s: %s", url, exc)
                    continue

            browser.close()

    except Exception as exc:
        logger.error("[blind] Scraper failed: %s", exc)
        return results  # return whatever was collected before failure

    logger.info("[blind] %d posts scraped", len(results))
    return results


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    debug_mode = "--debug" in sys.argv
    posts = scrape_blind(max_posts=100, debug=debug_mode)
    for p in posts:
        print(p["url"], "|", p["title"])
