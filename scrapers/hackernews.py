import logging
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser

logger = logging.getLogger(__name__)

HN_API = "https://hacker-news.firebaseio.com/v0"
CUTOFF_HOURS = 48


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


def _fetch_item(item_id: int) -> dict | None:
    try:
        resp = requests.get(f"{HN_API}/item/{item_id}.json", timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


def scrape_hn(limit: int = 100) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=CUTOFF_HOURS)

    try:
        resp = requests.get(f"{HN_API}/newstories.json", timeout=10)
        resp.raise_for_status()
        ids: list[int] = resp.json()[:limit]
    except Exception as exc:
        logger.error("[hn] Failed to fetch story list: %s", exc)
        return []

    items: list[dict] = []
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(_fetch_item, id_): id_ for id_ in ids}
        for future in as_completed(futures):
            item = future.result()
            if item is None:
                continue

            # Filter: deleted/dead, wrong type, no title, low score, too old
            if item.get("deleted") or item.get("dead"):
                continue
            if item.get("type") != "story":
                continue
            if not item.get("title"):
                continue
            if item.get("score", 0) < 2:
                continue
            posted = datetime.fromtimestamp(item["time"], tz=timezone.utc)
            if posted < cutoff:
                continue

            items.append(item)

    results = [
        {
            "platform": "hn",
            "external_id": str(item["id"]),
            "url": f"https://news.ycombinator.com/item?id={item['id']}",
            "title": item["title"],
            "body": _strip_html(item.get("text", "") or "")[:2000],
            "author": item.get("by", ""),
            "subreddit": None,
            "posted_at": datetime.utcfromtimestamp(item["time"]).isoformat(),
        }
        for item in items
    ]

    logger.info("[hn] %d stories fetched", len(results))
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    posts = scrape_hn(100)
    for p in posts:
        print(p["url"], "|", p["author"], "|", p["title"])
