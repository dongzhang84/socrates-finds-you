import argparse
import logging
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")

# ---------------------------------------------------------------------------
# Keywords / feeds / subreddits — centralised here so scrapers stay generic
# ---------------------------------------------------------------------------

LINKEDIN_KEYWORDS = [
    "PhD career transition",
    "leaving academia",
    "learn machine learning",
    "AI mentor",
    "career change data science",
    "PhD to industry",
    "machine learning career",
    "data science transition",
]

# Twitter disabled — API credits too expensive, re-enable when needed.
# TWITTER_QUERIES = [
#     "PhD leaving academia",
#     "PhD to industry",
#     "academic to industry transition",
#     "learning machine learning career",
#     "AI career change",
#     "SAT tutor math",
#     "AP calculus help",
#     "STEM mentor high school",
# ]

RSS_FEEDS = [
    "https://every.to/feed",
    "https://www.lennysnewsletter.com/feed",
    "https://www.oneusefulthing.org/feed",
]

REDDIT_SUBREDDITS = [
    # TIER_HIGH
    "PhD", "AskAcademia", "datascience", "MachineLearning",
    # TIER_MEDIUM
    "cscareerquestions", "learnmachinelearning", "GradSchool",
    # TIER_LOW
    "SAT", "ApplyingToCollege", "learnpython",
]

XIAOHONGSHU_KEYWORDS = [
    "PhD转行", "留学生找工作", "AI学习", "数学辅导", "SAT备考", "美国读博",
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="socrates-finds-you — lead signal pipeline")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--high-value-only", action="store_true",
                      help="Run LinkedIn + Blind only (skip lower-tier scrapers)")
    mode.add_argument("--no-browser", action="store_true",
                      help="Skip all Playwright scrapers (LinkedIn, Blind, 小红书)")
    mode.add_argument("--reddit-only", action="store_true",
                      help="Run Reddit + HN + RSS + Grad Cafe only")
    mode.add_argument("--no-scrape", action="store_true",
                      help="Skip scraping, re-run matching + report on existing data")
    mode.add_argument("--report-only", action="store_true",
                      help="Skip scraping and matching, just regenerate report")
    return p.parse_args()


def run_scraping(args: argparse.Namespace) -> list[dict]:
    all_signals: list[dict] = []

    # ------------------------------------------------------------------
    # Playwright scrapers (browser required)
    # ------------------------------------------------------------------
    if not args.no_browser and not args.reddit_only:
        # a) LinkedIn — highest value
        logger.info("[main] Starting LinkedIn scraper...")
        try:
            from scrapers.linkedin import scrape_linkedin
            signals = scrape_linkedin(keywords=LINKEDIN_KEYWORDS)
            all_signals.extend(signals)
            logger.info("[main] LinkedIn: %d signals", len(signals))
        except Exception as exc:
            logger.error("[main] LinkedIn scraper failed (possibly blocked): %s", exc)

        # b) Blind — highest value
        logger.info("[main] Starting Blind scraper...")
        try:
            from scrapers.blind import scrape_blind
            signals = scrape_blind(max_posts=30)
            all_signals.extend(signals)
            logger.info("[main] Blind: %d signals", len(signals))
        except Exception as exc:
            logger.warning("[main] Blind scraper failed: %s", exc)

        # f) 小红书 — medium value (skip when --high-value-only)
        if not args.high_value_only:
            logger.info("[main] Starting 小红书 scraper...")
            try:
                from scrapers.xiaohongshu import scrape_xiaohongshu
                signals = scrape_xiaohongshu(keywords=XIAOHONGSHU_KEYWORDS)
                all_signals.extend(signals)
                logger.info("[main] 小红书: %d signals", len(signals))
            except Exception as exc:
                logger.warning("[main] 小红书 scraper failed: %s", exc)

    # ------------------------------------------------------------------
    # c) Twitter — disabled
    # Twitter disabled — API credits too expensive, re-enable when needed.
    # try:
    #     from scrapers.twitter import scrape_twitter
    #     signals = scrape_twitter(queries=TWITTER_QUERIES)
    #     all_signals.extend(signals)
    # except Exception as exc:
    #     logger.warning("[main] Twitter scraper failed: %s", exc)
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # API / HTTP scrapers (no browser needed)
    # Skipped when --high-value-only. All run for --reddit-only, --no-browser,
    # and the default full run.
    # ------------------------------------------------------------------
    if not args.high_value_only:
        # d) Hacker News
        logger.info("[main] Starting Hacker News scraper...")
        from scrapers.hackernews import scrape_hn
        signals = scrape_hn(100)
        all_signals.extend(signals)
        logger.info("[main] HN: %d signals", len(signals))

        # e) RSS
        logger.info("[main] Starting RSS scraper...")
        from scrapers.rss import scrape_rss
        signals = scrape_rss(feeds=RSS_FEEDS)
        all_signals.extend(signals)
        logger.info("[main] RSS: %d signals", len(signals))

        # g) Reddit
        logger.info("[main] Starting Reddit scraper...")
        from scrapers.reddit import scrape_reddit
        signals = scrape_reddit(subreddits=REDDIT_SUBREDDITS)
        all_signals.extend(signals)
        logger.info("[main] Reddit: %d signals", len(signals))

        # h) Grad Cafe
        logger.info("[main] Starting Grad Cafe scraper...")
        from scrapers.gradcafe import scrape_gradcafe
        signals = scrape_gradcafe(max_posts=30)
        all_signals.extend(signals)
        logger.info("[main] Grad Cafe: %d signals", len(signals))

    logger.info("[main] Scraping complete — %d total signals collected", len(all_signals))
    return all_signals


def run_matching(unmatched: list[dict]) -> int:
    from matcher.claude_match import match_signals
    from storage.db import update_match_result

    matched_signals = match_signals(unmatched)
    count = 0
    for s in matched_signals:
        if "matched" not in s:
            continue
        update_match_result(
            id=s["id"],
            matched=s["matched"],
            service_match=s.get("service_match"),
            client_tier=s.get("client_tier"),
            confidence=s.get("confidence"),
            reasoning=s.get("reasoning"),
        )
        if s["matched"]:
            count += 1
    return count


def main() -> None:
    args = parse_args()
    t0 = time.monotonic()

    from storage.db import init_db, save_signals, get_unmatched
    from reporter.daily_report import generate_report

    init_db()

    new_signals = 0
    matched_count = 0

    # ------------------------------------------------------------------
    # Scraping phase
    # ------------------------------------------------------------------
    if not args.no_scrape and not args.report_only:
        all_signals = run_scraping(args)

        # Attach composite id expected by db layer: "{platform}:{external_id}"
        for s in all_signals:
            if "id" not in s:
                s["id"] = f"{s['platform']}:{s['external_id']}"

        new_signals = save_signals(all_signals)

    # ------------------------------------------------------------------
    # Matching phase
    # ------------------------------------------------------------------
    if not args.report_only:
        unmatched = get_unmatched(limit=150)
        if unmatched:
            logger.info("[main] Running Claude matching on %d unmatched signals...", len(unmatched))
            matched_count = run_matching(unmatched)
            logger.info("[main] Matching complete — %d matched", matched_count)
        else:
            logger.info("[main] No unmatched signals to process")

    # ------------------------------------------------------------------
    # Report phase
    # ------------------------------------------------------------------
    logger.info("[main] Generating report...")
    report_path = generate_report()

    elapsed = time.monotonic() - t0
    logger.info(
        "[main] Done in %.1fs — %d new signals, %d matched, report saved to %s",
        elapsed, new_signals, matched_count, report_path,
    )


if __name__ == "__main__":
    main()
