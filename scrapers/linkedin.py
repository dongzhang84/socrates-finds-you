import hashlib
import logging
import os
import random
import time
import urllib.parse

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

logger = logging.getLogger(__name__)

DEFAULT_KEYWORDS = [
    "PhD career transition",
    "leaving academia",
    "learn machine learning",
    "AI mentor",
    "career change data science",
    "PhD to industry",
    "machine learning career",
    "data science transition",
]


def scrape_linkedin(keywords: list[str] = DEFAULT_KEYWORDS, max_posts: int = 20, debug: bool = False) -> list[dict]:
    email = os.getenv("LINKEDIN_EMAIL")
    password = os.getenv("LINKEDIN_PASSWORD")
    if not email or not password:
        logger.error("[linkedin] LINKEDIN_EMAIL or LINKEDIN_PASSWORD not set in .env")
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

            # Login (skip if already on feed, e.g. via persisted Google SSO)
            page.goto("https://www.linkedin.com")
            if "/feed" not in page.url:
                try:
                    # Homepage may show SSO buttons instead of the email form directly.
                    # Click "Sign in with email" to reveal the email/password inputs.
                    email_input = page.query_selector('input[name="session_key"]')
                    if not email_input:
                        try:
                            page.click(
                                'a[data-tracking-control-name="guest_homepage-basic_sign-in-btn"]',
                                timeout=5000,
                            )
                        except Exception:
                            page.click('text=Sign in with email', timeout=5000)
                        page.wait_for_selector('input[name="session_key"]', timeout=10000)

                    page.fill('input[name="session_key"]', email, timeout=10000)
                    page.fill('input[name="session_password"]', password, timeout=10000)
                    page.click('button[type="submit"]')
                    page.wait_for_url(lambda url: "feed" in url, timeout=20000)
                except Exception as exc:
                    logger.error("[linkedin] Login failed: %s", exc)
                    browser.close()
                    return []
            else:
                logger.info("[linkedin] Already logged in, skipping login form")

            for keyword in keywords:
                if len(results) >= max_posts:
                    break
                try:
                    encoded = urllib.parse.quote(keyword)
                    url = (
                        f"https://www.linkedin.com/search/results/content/"
                        f"?keywords={encoded}&sortBy=DATE_POSTED"
                    )
                    page.goto(url)

                    # Wait for SDUI search container (current LinkedIn DOM as of 2026)
                    try:
                        page.wait_for_selector(
                            'div[data-sdui-screen*="SearchResultsContent"]', timeout=10000
                        )
                    except Exception:
                        page.wait_for_load_state("domcontentloaded", timeout=15000)
                        time.sleep(3)

                    logger.info("[linkedin] Page URL: %s", page.url)
                    logger.info("[linkedin] Page title: %s", page.title())

                    if debug:
                        with open("debug_linkedin.html", "w", encoding="utf-8") as fh:
                            fh.write(page.content())
                        logger.info("[linkedin] Debug HTML saved to debug_linkedin.html")
                        browser.close()
                        return []

                    # Extract posts via JS DOM traversal — avoids obfuscated class names
                    extracted = page.evaluate("""() => {
                        const results = [];
                        const seen = new Set();
                        const postLinks = document.querySelectorAll('a[href*="/feed/update/"]');

                        for (const link of postLinks) {
                            const rawUrl = link.href.split('?')[0];
                            if (!rawUrl || seen.has(rawUrl)) continue;

                            // Walk up to find a card root that contains both a profile link
                            // and the post link — stops before the SDUI screen container.
                            let card = link;
                            for (let i = 0; i < 20; i++) {
                                if (!card.parentElement) break;
                                card = card.parentElement;
                                if (card.hasAttribute('data-sdui-screen')) break;
                                if (
                                    card.querySelector('a[href*="/in/"]') &&
                                    card.querySelector('a[href*="/feed/update/"]')
                                ) break;
                            }

                            // Author: first profile link in card
                            const authorEl = card.querySelector('a[href*="/in/"]');
                            const author = authorEl
                                ? (authorEl.innerText || authorEl.getAttribute('aria-label') || '').trim()
                                : '';

                            // Snippet: longest <p> text block in card
                            let snippet = '';
                            for (const p of card.querySelectorAll('p')) {
                                const t = p.innerText.trim();
                                if (t.length > snippet.length) snippet = t;
                            }

                            if (!snippet) continue;
                            seen.add(rawUrl);
                            results.push({ url: rawUrl, author, snippet });
                        }
                        return results;
                    }""")

                    for item in extracted:
                        if len(results) >= max_posts:
                            break
                        post_url = item["url"]
                        if post_url in seen_urls:
                            continue
                        snippet = item["snippet"]
                        seen_urls.add(post_url)
                        results.append(
                            {
                                "platform": "linkedin",
                                "external_id": hashlib.md5(post_url.encode()).hexdigest()[:12],
                                "url": post_url,
                                "title": snippet[:120],
                                "body": snippet[:2000],
                                "author": item["author"],
                                "subreddit": None,
                                "posted_at": None,
                            }
                        )

                    time.sleep(random.uniform(3.0, 6.0))

                except Exception as exc:
                    logger.warning("[linkedin] Failed on keyword %r: %s", keyword, exc)
                    continue

            browser.close()

    except Exception as exc:
        logger.error("[linkedin] Scraper failed: %s", exc)
        return []

    logger.info("[linkedin] %d posts scraped", len(results))
    return results


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    debug_mode = "--debug" in sys.argv
    posts = scrape_linkedin(DEFAULT_KEYWORDS, max_posts=20, debug=debug_mode)
    for p in posts:
        print(p["url"], "|", p["title"])
