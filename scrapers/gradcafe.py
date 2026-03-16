import logging
import random
import re
import time
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://forum.thegradcafe.com"
HEADERS = {"User-Agent": "Mozilla/5.0"}
CUTOFF_DAYS = 7

# Forum 18 (career-advice) no longer exists — using the current relevant forums:
#   72 = Jobs, 21 = Officially Grads
FORUM_URLS = [
    f"{BASE_URL}/forum/72-jobs/",
    f"{BASE_URL}/forum/21-officially-grads/",
]


class _HTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def get_text(self) -> str:
        return " ".join(self._parts).strip()


def _strip_html(html: str) -> str:
    p = _HTMLStripper()
    p.feed(html)
    return p.get_text()


class _ThreadListParser(HTMLParser):
    """Extracts thread stubs from a GradCafe forum index page.

    Each thread is an <a href="/topic/..."> inside an h4.ipsDataItem_title,
    with a <time datetime="ISO"> and an author <a href="/profile/..."> nearby.
    """

    def __init__(self):
        super().__init__()
        self.threads: list[dict] = []
        self._in_title = False
        self._in_meta = False
        self._current: dict | None = None
        self._tag_stack: list[str] = []

    def handle_starttag(self, tag, attrs):
        attrs_d = dict(attrs)
        self._tag_stack.append(tag)

        if tag == "h4" and "ipsDataItem_title" in attrs_d.get("class", ""):
            self._in_title = True
            self._current = {"url": None, "title": "", "datetime": None, "author": ""}

        if self._in_title and tag == "a":
            href = attrs_d.get("href", "")
            if "/topic/" in href and self._current and not self._current["url"]:
                self._current["url"] = href.split("?")[0]

        if tag == "div" and "ipsDataItem_meta" in attrs_d.get("class", ""):
            self._in_meta = True

        if self._in_meta and tag == "time":
            dt_str = attrs_d.get("datetime", "")
            if dt_str and self._current:
                self._current["datetime"] = dt_str

        if self._in_meta and tag == "a":
            href = attrs_d.get("href", "")
            if "/profile/" in href and self._current and not self._current["author"]:
                self._current["_capture_author"] = True

    def handle_data(self, data):
        if self._current:
            if self._in_title and self._current.get("url") and not self._current["title"]:
                text = data.strip()
                if text:
                    self._current["title"] = text
            if self._current.get("_capture_author"):
                text = data.strip()
                if text:
                    self._current["author"] = text
                    del self._current["_capture_author"]

    def handle_endtag(self, tag):
        if self._tag_stack:
            self._tag_stack.pop()

        if tag == "h4" and self._in_title:
            self._in_title = False
            if self._current and self._current.get("url") and self._current.get("title"):
                self.threads.append(self._current)
            self._current = None

        if tag == "div" and self._in_meta:
            self._in_meta = False


class _PostBodyParser(HTMLParser):
    """Extracts the first post body from a GradCafe thread page.

    The OP content is in: <div data-role="commentContent" ...>
    """

    def __init__(self):
        super().__init__()
        self._in_body = False
        self._depth = 0
        self._parts: list[str] = []
        self.body = ""
        self.done = False

    def handle_starttag(self, tag, attrs):
        if self.done:
            return
        attrs_d = dict(attrs)
        if not self._in_body and attrs_d.get("data-role") == "commentContent":
            self._in_body = True
            self._depth = 1
            return
        if self._in_body:
            self._depth += 1

    def handle_endtag(self, tag):
        if self.done or not self._in_body:
            return
        self._depth -= 1
        if self._depth <= 0:
            self.body = " ".join(self._parts).strip()
            self._in_body = False
            self.done = True

    def handle_data(self, data):
        if self._in_body:
            text = data.strip()
            if text:
                self._parts.append(text)


def _parse_iso(dt_str: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _slug_from_url(url: str) -> str:
    parts = url.rstrip("/").split("/")
    return parts[-1] if parts else url


def _fetch(url: str) -> str | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        return resp.text
    except Exception as exc:
        logger.warning("[gradcafe] GET %s failed: %s", url, exc)
        return None


def scrape_gradcafe(max_posts: int = 30) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=CUTOFF_DAYS)
    results: list[dict] = []
    seen_urls: set[str] = set()

    try:
        # Collect thread stubs from all forum pages
        all_stubs: list[dict] = []
        for forum_url in FORUM_URLS:
            html = _fetch(forum_url)
            if not html:
                continue
            parser = _ThreadListParser()
            parser.feed(html)
            all_stubs.extend(parser.threads)
            logger.debug("[gradcafe] %s: %d threads found", forum_url, len(parser.threads))

        # Filter by age and dedup
        fresh_stubs: list[dict] = []
        for stub in all_stubs:
            url = stub.get("url", "")
            if not url or url in seen_urls:
                continue
            dt = _parse_iso(stub.get("datetime") or "")
            if dt and dt < cutoff:
                continue
            seen_urls.add(url)
            fresh_stubs.append(stub)

        # Fetch full body for each thread, up to max_posts
        for stub in fresh_stubs[:max_posts]:
            url = stub["url"]
            html = _fetch(url)
            if not html:
                continue

            body_parser = _PostBodyParser()
            body_parser.feed(html)
            body = body_parser.body

            dt = _parse_iso(stub.get("datetime") or "")
            results.append({
                "platform": "gradcafe",
                "external_id": _slug_from_url(url),
                "url": url,
                "title": stub["title"][:120],
                "body": body[:2000],
                "author": stub.get("author", ""),
                "subreddit": None,
                "posted_at": dt.isoformat() if dt else None,
            })

            time.sleep(random.uniform(1.0, 2.5))

    except Exception as exc:
        logger.error("[gradcafe] Scraper failed: %s", exc)
        return results

    logger.info("[gradcafe] %d threads scraped", len(results))
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    posts = scrape_gradcafe(max_posts=30)
    for p in posts:
        print(p["url"], "|", p["author"], "|", p["title"])
