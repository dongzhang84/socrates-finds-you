import logging
import os
import time
from datetime import datetime, timedelta, timezone

import tweepy
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

DEFAULT_QUERIES = [
    "PhD leaving academia",
    "PhD to industry",
    "academic to industry transition",
    "learning machine learning career",
    "AI career change",
    "SAT tutor math",
    "AP calculus help",
    "STEM mentor high school",
]

CUTOFF_HOURS = 48


def scrape_twitter(queries: list[str] = DEFAULT_QUERIES, max_per_query: int = 50) -> list[dict]:
    bearer_token = os.getenv("TWITTER_BEARER_TOKEN")
    if not bearer_token:
        logger.error("[twitter] TWITTER_BEARER_TOKEN not set in .env")
        return []

    client = tweepy.Client(bearer_token=bearer_token, wait_on_rate_limit=True)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=CUTOFF_HOURS)

    results: list[dict] = []
    seen_ids: set[str] = set()

    for query in queries:
        try:
            response = client.search_recent_tweets(
                query=f"{query} -is:retweet lang:en",
                max_results=min(max_per_query, 100),
                tweet_fields=["created_at", "author_id", "text", "public_metrics"],
                expansions=["author_id"],
                user_fields=["username"],
            )

            if not response.data:
                logger.info("[twitter] %r: 0 tweets", query)
                time.sleep(2)
                continue

            # Build author_id → username lookup from expansions
            users: dict[int, str] = {}
            if response.includes and response.includes.get("users"):
                for user in response.includes["users"]:
                    users[user.id] = user.username

            added = 0
            for tweet in response.data:
                tweet_id = str(tweet.id)
                if tweet_id in seen_ids:
                    continue

                # Age filter
                if tweet.created_at and tweet.created_at < cutoff:
                    continue

                seen_ids.add(tweet_id)
                results.append({
                    "platform": "twitter",
                    "external_id": tweet_id,
                    "url": f"https://twitter.com/i/web/status/{tweet_id}",
                    "title": tweet.text[:120],
                    "body": tweet.text[:2000],
                    "author": users.get(tweet.author_id, ""),
                    "subreddit": None,
                    "posted_at": tweet.created_at.isoformat() if tweet.created_at else None,
                })
                added += 1

            logger.info("[twitter] %r: %d tweets", query, added)
            time.sleep(2)

        except tweepy.TweepyException as exc:
            logger.warning("[twitter] Query %r failed: %s", query, exc)
            continue

    logger.info("[twitter] %d tweets fetched", len(results))
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    posts = scrape_twitter(DEFAULT_QUERIES, max_per_query=10)
    for p in posts:
        print(p["url"], "|", p["author"], "|", p["title"][:80])
