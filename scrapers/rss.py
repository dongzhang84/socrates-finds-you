import hashlib
import logging
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser

import feedparser
import requests

logger = logging.getLogger(__name__)

DEFAULT_FEEDS = [
    "https://every.to/feed",
    "https://www.lennysnewsletter.com/feed",
    "https://www.oneusefulthing.org/feed",
]


class _HTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def get_text(self) -> str:
        return " ".join(self._parts)


def _strip_html(html: str) -> str:
    if not html:
        return ""
    parser = _HTMLStripper()
    parser.feed(html)
    return parser.get_text().strip()


def _parse_published(entry) -> datetime | None:
    """Return a timezone-aware datetime from a feedparser entry, or None."""
    # feedparser populates published_parsed as a time.struct_time in UTC
    if entry.get("published_parsed"):
        import calendar
        ts = calendar.timegm(entry.published_parsed)
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    return None


def scrape_rss(feeds: list[str] = DEFAULT_FEEDS, max_age_hours: int = 48) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    results: list[dict] = []

    for feed_url in feeds:
        try:
            # Fetch via requests so SSL/redirects are handled correctly,
            # then pass raw content to feedparser rather than the URL.
            resp = requests.get(feed_url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            parsed = feedparser.parse(resp.content)

            if parsed.get("bozo") and not parsed.entries:
                logger.warning("[rss] %s: parse error — %s", feed_url, parsed.get("bozo_exception", ""))
                continue

            added = 0
            for entry in parsed.entries:
                pub_dt = _parse_published(entry)
                if pub_dt and pub_dt < cutoff:
                    continue

                raw_id = entry.get("id") or entry.get("link", "")
                external_id = raw_id if raw_id else hashlib.md5(feed_url.encode()).hexdigest()[:12]
                # If id looks like a full URL or is very long, hash it for compactness
                if len(external_id) > 64:
                    external_id = hashlib.md5(external_id.encode()).hexdigest()[:12]

                summary = entry.get("summary") or entry.get("content", [{}])[0].get("value", "")
                body = _strip_html(summary)

                results.append({
                    "platform": "rss",
                    "external_id": external_id,
                    "url": entry.get("link", ""),
                    "title": entry.get("title", ""),
                    "body": body[:2000],
                    "author": entry.get("author", ""),
                    "subreddit": None,
                    "posted_at": entry.get("published", None),
                })
                added += 1

            logger.info("[rss] %s: %d entries fetched", feed_url, added)

        except Exception as exc:
            logger.warning("[rss] %s: failed — %s", feed_url, exc)
            continue

    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    posts = scrape_rss(DEFAULT_FEEDS, max_age_hours=48)
    print(f"{len(posts)} total entries")
    for p in posts:
        print(p["url"], "|", p["title"][:80])
