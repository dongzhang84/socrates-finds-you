import logging
import time
from datetime import datetime, timedelta, timezone

import requests

logger = logging.getLogger(__name__)

HEADERS = {"User-Agent": "socrates-finds-you/1.0"}
CUTOFF_HOURS = 48

TIER_HIGH = ["PhD", "AskAcademia", "datascience", "MachineLearning"]
TIER_MEDIUM = ["learnmachinelearning", "GradSchool"]
TIER_LOW = ["SAT", "ApplyingToCollege", "learnpython"]
DEFAULT_SUBREDDITS = TIER_HIGH + TIER_MEDIUM + TIER_LOW


def scrape_reddit(subreddits: list[str] = DEFAULT_SUBREDDITS, limit_per_sub: int = 50) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=CUTOFF_HOURS)
    results: list[dict] = []

    for subreddit in subreddits:
        try:
            url = f"https://www.reddit.com/r/{subreddit}/new.json?limit={limit_per_sub}"
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            posts = data.get("data", {}).get("children", [])
            added = 0

            for child in posts:
                post = child.get("data", {})

                # Filter: stickied
                if post.get("stickied"):
                    continue

                # Filter: removed or deleted body
                body = post.get("selftext", "") or ""
                if body in ("[removed]", "[deleted]"):
                    body = ""

                # Filter: older than 48h
                created_utc = post.get("created_utc", 0)
                posted_dt = datetime.fromtimestamp(created_utc, tz=timezone.utc)
                if posted_dt < cutoff:
                    continue

                author = post.get("author", "")
                if author in ("[deleted]", "AutoModerator"):
                    continue

                results.append({
                    "platform": "reddit",
                    "external_id": f"t3_{post['id']}",
                    "url": f"https://reddit.com{post['permalink']}",
                    "title": post.get("title", ""),
                    "body": body[:2000],
                    "author": author,
                    "subreddit": post.get("subreddit", subreddit),
                    "posted_at": datetime.utcfromtimestamp(created_utc).isoformat(),
                })
                added += 1

            logger.info("[reddit] r/%s: %d posts", subreddit, added)

            # Polite delay between subreddits
            time.sleep(1)

        except Exception as exc:
            logger.warning("[reddit] r/%s: failed — %s", subreddit, exc)
            continue

    logger.info("[reddit] Total: %d posts", len(results))
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    posts = scrape_reddit(DEFAULT_SUBREDDITS, limit_per_sub=25)
    for p in posts:
        print(f"r/{p['subreddit']} | {p['url']} | {p['title'][:70]}")
