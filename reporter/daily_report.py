import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from storage.db import get_report_candidates, mark_included_in_report

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("output")

TIER_ORDER = {"high": 0, "medium": 1, "low": 2}

SECTION_HEADERS = {
    "high":   "## 🔴 High Value (PhD / Professionals)",
    "medium": "## 🟡 Medium Value (College / Early Career)",
    "low":    "## 🟢 Lower Value (High School / Students)",
}


def _format_signal(n: int, s: dict) -> str:
    platform_str = s["platform"]
    if s.get("subreddit"):
        platform_str += f" · r/{s['subreddit']}"

    lines = [
        f"### {n}. {s['title']}",
        f"- **Platform**: {platform_str}",
        f"- **Service**: {s.get('service_match') or 'N/A'}",
        f"- **Confidence**: {s.get('confidence') or 'N/A'}",
        f"- **Why**: {s.get('reasoning') or 'N/A'}",
        f"- **Link**: {s['url']}",
        f"- **Posted**: {s.get('posted_at') or 'unknown'}",
    ]
    return "\n".join(lines)


def _build_markdown(signals: list[dict], date_str: str, now_utc: datetime) -> str:
    by_tier: dict[str, list[dict]] = {"high": [], "medium": [], "low": []}
    for s in signals:
        tier = (s.get("client_tier") or "low").lower()
        by_tier.setdefault(tier, []).append(s)

    h = len(by_tier["high"])
    m = len(by_tier["medium"])
    lo = len(by_tier["low"])
    total = len(signals)

    lines: list[str] = [
        f"# socrates-finds-you — Daily Report {date_str}",
        "",
        f"**{total} leads matched** — {h} high / {m} medium / {lo} low value",
        "",
        "---",
    ]

    if total == 0:
        lines += [
            "",
            "*No leads today. Run again tomorrow.*",
            "",
            "---",
        ]
    else:
        for tier in ("high", "medium", "low"):
            group = by_tier.get(tier, [])
            lines += ["", SECTION_HEADERS[tier], ""]
            if not group:
                lines.append("*No leads in this tier today.*")
            else:
                for i, s in enumerate(group, 1):
                    lines.append(_format_signal(i, s))
                    lines.append("")
            lines.append("---")

    lines += [
        "",
        f"*Generated {now_utc.strftime('%Y-%m-%d %H:%M:%S')} UTC. "
        "Mark leads as actioned in signals.db after review.*",
    ]
    return "\n".join(lines)


def generate_report() -> str:
    now_utc = datetime.now(timezone.utc)
    date_str = now_utc.strftime("%Y-%m-%d")
    output_path = OUTPUT_DIR / f"report_{date_str}.md"

    OUTPUT_DIR.mkdir(exist_ok=True)

    signals = get_report_candidates()

    # Sort: high → medium → low (get_report_candidates already does this,
    # but we re-sort here to be safe in case order changes)
    signals.sort(key=lambda s: TIER_ORDER.get((s.get("client_tier") or "low").lower(), 99))

    markdown = _build_markdown(signals, date_str, now_utc)

    output_path.write_text(markdown, encoding="utf-8")

    if signals:
        mark_included_in_report([s["id"] for s in signals])

    logger.info("[reporter] Saved: %s (%d leads)", output_path, len(signals))
    return str(output_path)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    path = generate_report()
    print(f"Report saved to {path}")
