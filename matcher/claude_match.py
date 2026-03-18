import json
import logging
import os
import re

import anthropic
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-5"
BATCH_SIZE = 10

SYSTEM_PROMPT = """You are a matching assistant for Dong Zhang, Ph.D. — a STEM and AI mentor.

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
- AI Literacy for Students"""


def _build_user_prompt(batch: list[dict]) -> str:
    posts = [
        {
            "id": s["id"],
            "title": s["title"],
            "body": (s.get("body") or "")[:600],
            "platform": s["platform"],
            "subreddit": s.get("subreddit"),
        }
        for s in batch
    ]
    return (
        "Evaluate these posts. For each return:\n"
        "- matched: true if there is a real learning/coaching/transition need\n"
        "- service_match: specific service name from the list (or null)\n"
        "- client_tier: 'high', 'medium', or 'low'\n"
        "- confidence: 'high', 'medium', or 'low'\n"
        "- reasoning: one sentence max\n"
        "- suggested_reply: if matched=true, write a short Reddit reply (2-4 sentences) that "
        "directly addresses the person's specific problem, provides genuine value, and ends with "
        "a soft invitation like 'Happy to share more if useful' or 'Feel free to DM if you want "
        "to dig into this'. Sound like a real person, not a consultant. If matched=false, return null.\n\n"
        f"Posts:\n{json.dumps(posts)}\n\n"
        "Return a JSON array only. No other text."
    )


def _strip_fences(text: str) -> str:
    """Remove ```json ... ``` or ``` ... ``` fences if present."""
    return re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE).strip()


def match_signals(signals: list[dict]) -> list[dict]:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("[matcher] ANTHROPIC_API_KEY not set in .env")
        return signals

    client = anthropic.Anthropic(api_key=api_key)

    # Index signals by id for result merging
    results: dict[str, dict] = {s["id"]: dict(s) for s in signals}

    total_matched = 0
    total_processed = 0

    for batch_num, start in enumerate(range(0, len(signals), BATCH_SIZE), 1):
        batch = signals[start : start + BATCH_SIZE]
        try:
            message = client.messages.create(
                model=MODEL,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": _build_user_prompt(batch)}],
            )
            raw = message.content[0].text
            parsed = json.loads(_strip_fences(raw))

            batch_matched = 0
            for item in parsed:
                signal_id = item.get("id")
                if signal_id not in results:
                    continue
                results[signal_id].update({
                    "matched": bool(item.get("matched", False)),
                    "service_match": item.get("service_match"),
                    "client_tier": item.get("client_tier"),
                    "confidence": item.get("confidence"),
                    "reasoning": item.get("reasoning"),
                    "suggested_reply": item.get("suggested_reply"),
                })
                if item.get("matched"):
                    batch_matched += 1

            total_matched += batch_matched
            total_processed += len(batch)
            logger.info(
                "[matcher] Batch %d: %d/%d matched",
                batch_num, batch_matched, len(batch),
            )

        except json.JSONDecodeError as exc:
            logger.warning("[matcher] Batch %d: JSON parse error — %s", batch_num, exc)
            continue
        except Exception as exc:
            logger.warning("[matcher] Batch %d: failed — %s", batch_num, exc)
            continue

    logger.info("[matcher] Total: %d/%d matched", total_matched, total_processed)
    return list(results.values())


def generate_replies(signals: list[dict]) -> list[dict]:
    """For already-matched signals, generate suggested_reply and return updated dicts."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("[matcher] ANTHROPIC_API_KEY not set in .env")
        return signals

    client = anthropic.Anthropic(api_key=api_key)
    results: dict[str, dict] = {s["id"]: dict(s) for s in signals}

    for batch_num, start in enumerate(range(0, len(signals), BATCH_SIZE), 1):
        batch = signals[start : start + BATCH_SIZE]
        posts = [
            {
                "id": s["id"],
                "title": s["title"],
                "body": (s.get("body") or "")[:600],
                "service_match": s.get("service_match"),
                "reasoning": s.get("reasoning"),
            }
            for s in batch
        ]
        prompt = (
            "For each of these already-matched leads, write a suggested_reply: "
            "a short Reddit reply (2-4 sentences) that directly addresses the person's "
            "specific problem, provides genuine value, and ends with a soft invitation like "
            "'Happy to share more if useful' or 'Feel free to DM if you want to dig into this'. "
            "Sound like a real person, not a consultant.\n\n"
            f"Leads:\n{json.dumps(posts)}\n\n"
            "Return a JSON array with objects containing 'id' and 'suggested_reply' only. No other text."
        )
        try:
            message = client.messages.create(
                model=MODEL,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            parsed = json.loads(_strip_fences(message.content[0].text))
            for item in parsed:
                signal_id = item.get("id")
                if signal_id in results and item.get("suggested_reply"):
                    results[signal_id]["suggested_reply"] = item["suggested_reply"]
            logger.info("[matcher] generate_replies batch %d: %d replies", batch_num, len(parsed))
        except json.JSONDecodeError as exc:
            logger.warning("[matcher] generate_replies batch %d: JSON parse error — %s", batch_num, exc)
        except Exception as exc:
            logger.warning("[matcher] generate_replies batch %d: failed — %s", batch_num, exc)

    return list(results.values())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test = [
        {
            "id": "test:1",
            "title": "Just finished Physics PhD, completely lost on how to break into ML",
            "body": "Been in academia 6 years, no idea how to position myself for industry roles",
            "platform": "reddit",
            "subreddit": "PhD",
        }
    ]
    results = match_signals(test)
    for r in results:
        print(json.dumps(r, indent=2))
