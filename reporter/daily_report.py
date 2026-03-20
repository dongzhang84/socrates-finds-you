import html
import logging
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent.parent))

from storage.db import get_report_candidates

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("output")

TIER_ORDER = {"high": 0, "medium": 1, "low": 2}

SERVICE_PRIORITY = {
    "AI Career Path Planning": 0,
    "AI Upskilling for Professionals": 1,
    "Applied AI Project Coaching for Career Switchers": 2,
    "PhD to Industry Transition Coaching": 3,
    "AI / ML Learning Path Coaching": 4,
    "AP / SAT / ACT Math Tutoring": 5,
    "College-Level STEM Tutoring": 6,
}

SECTION_HEADERS = {
    "high":   "## 🔴 High Value (PhD / Professionals)",
    "medium": "## 🟡 Medium Value (College / Early Career)",
    "low":    "## 🟢 Lower Value (High School / Students)",
}

TIER_META = {
    "high":   ("🔴", "High Value — PhD / Professionals",    "#e53e3e"),
    "medium": ("🟡", "Medium Value — College / Early Career", "#d97706"),
    "low":    ("🟢", "Low Value — High School / Students",  "#38a169"),
}


def _group_by_tier(signals: list[dict]) -> dict[str, list[dict]]:
    by_tier: dict[str, list[dict]] = {"high": [], "medium": [], "low": []}
    for s in signals:
        tier = (s.get("client_tier") or "low").lower()
        by_tier.setdefault(tier, []).append(s)
    for group in by_tier.values():
        group.sort(key=lambda s: SERVICE_PRIORITY.get(s.get("service_match") or "", 99))
    return by_tier


def _format_signal_md(n: int, s: dict) -> str:
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
    if s.get("suggested_reply"):
        lines.append(f"- **Suggested reply**: {s['suggested_reply']}")
    return "\n".join(lines)


def _build_markdown(signals: list[dict], date_str: str, now_utc: datetime) -> str:
    by_tier = _group_by_tier(signals)

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
        lines += ["", "*No leads today. Run again tomorrow.*", "", "---"]
    else:
        for tier in ("high", "medium", "low"):
            group = by_tier.get(tier, [])
            lines += ["", SECTION_HEADERS[tier], ""]
            if not group:
                lines.append("*No leads in this tier today.*")
            else:
                for i, s in enumerate(group, 1):
                    lines.append(_format_signal_md(i, s))
                    lines.append("")
            lines.append("---")

    lines += [
        "",
        f"*Generated {now_utc.strftime('%Y-%m-%d %H:%M:%S')} Seattle time. "
        "Mark leads as actioned in signals.db after review.*",
    ]
    return "\n".join(lines)


def _build_html(signals: list[dict], date_str: str, now_utc: datetime) -> str:
    by_tier = _group_by_tier(signals)
    h = len(by_tier["high"])
    m = len(by_tier["medium"])
    lo = len(by_tier["low"])
    total = len(signals)

    def e(s: str) -> str:
        return html.escape(str(s or ""))

    cards_html = ""
    for tier in ("high", "medium", "low"):
        emoji, label, color = TIER_META[tier]
        group = by_tier.get(tier, [])
        count = len(group)

        cards_html += f"""
  <div class="tier-section">
    <div class="tier-header" style="border-color:{color}">
      <span>{emoji}</span>
      <span class="tier-title">{label}</span>
      <span class="tier-count">{count}</span>
    </div>
"""
        if not group:
            cards_html += '    <p style="color:#aaa;font-style:italic;font-size:0.85rem;">No leads in this tier today.</p>\n'
        else:
            for idx, s in enumerate(group):
                platform_str = e(s["platform"])
                if s.get("subreddit"):
                    platform_str += f" · r/{e(s['subreddit'])}"
                title = e(s["title"])
                url = e(s["url"])
                service = e(s.get("service_match") or "")
                confidence = e(s.get("confidence") or "")
                reasoning = e(s.get("reasoning") or "")
                reply = e(s.get("suggested_reply") or "")
                reply_id = f"reply-{tier}-{idx}"

                reply_html = ""
                if reply:
                    reply_html = (
                        f'<div class="reply-section">'
                        f'<div class="reply-label">Suggested reply</div>'
                        f'<div class="reply-text" id="{reply_id}">{reply}</div>'
                        f'<button class="copy-btn" onclick="copyReply(\'{reply_id}\', this)">Copy</button>'
                        f'<button class="replied-btn" onclick="markReplied(this)">Mark as Replied</button>'
                        f'</div>'
                    )

                cards_html += f"""    <div class="lead">
      <div class="lead-title"><a href="{url}" target="_blank" rel="noopener">{title}</a></div>
      <div class="lead-meta">
        <span class="badge badge-platform">{platform_str}</span>
        {f'<span class="badge badge-service">{service}</span>' if service else ""}
        {f'<span class="badge badge-conf">{confidence} confidence</span>' if confidence else ""}
      </div>
      {f'<div class="lead-reasoning">{reasoning}</div>' if reasoning else ""}
      {reply_html}
    </div>
"""
        cards_html += "  </div>\n"

    no_leads_msg = ""
    if total == 0:
        no_leads_msg = '<div class="empty"><p>No matched leads today.</p><p>Run the pipeline to scrape and match new signals.</p></div>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>socrates-finds-you — {date_str}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         background: #f5f5f5; color: #1a1a1a; line-height: 1.5; }}
  .header {{ background: #1a1a2e; color: #fff; padding: 20px 32px; }}
  .header h1 {{ font-size: 1.3rem; font-weight: 600; }}
  .header h1 span {{ color: #7c9eff; }}
  .header .sub {{ font-size: 0.85rem; color: #aaa; margin-top: 4px; }}
  .stats {{ background: #fff; border-bottom: 1px solid #e5e5e5;
           padding: 14px 32px; display: flex; gap: 24px; flex-wrap: wrap; }}
  .stat {{ text-align: center; }}
  .stat-num {{ font-size: 1.4rem; font-weight: 700; }}
  .stat-label {{ font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.5px; color: #888; }}
  .stat.high .stat-num {{ color: #e53e3e; }}
  .stat.medium .stat-num {{ color: #d97706; }}
  .stat.low .stat-num {{ color: #38a169; }}
  .stat.total .stat-num {{ color: #3b82f6; }}
  .divider {{ width: 1px; height: 36px; background: #e5e5e5; }}
  .main {{ max-width: 920px; margin: 28px auto; padding: 0 20px 60px; }}
  .tier-section {{ margin-bottom: 32px; }}
  .tier-header {{ display: flex; align-items: center; gap: 10px;
                 padding: 10px 0; border-bottom: 2px solid; margin-bottom: 14px; }}
  .tier-title {{ font-size: 0.95rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.4px; }}
  .tier-count {{ font-size: 0.78rem; color: #888; background: #f0f0f0;
                border-radius: 10px; padding: 1px 8px; }}
  .lead {{ background: #fff; border: 1px solid #e8e8e8; border-radius: 10px;
          padding: 16px 18px; margin-bottom: 10px; }}
  .lead-title {{ font-size: 0.95rem; font-weight: 600; margin-bottom: 8px; color: #111; }}
  .lead-title a {{ color: inherit; text-decoration: none; }}
  .lead-title a:hover {{ text-decoration: underline; color: #2563eb; }}
  .lead-meta {{ display: flex; flex-wrap: wrap; gap: 6px; font-size: 0.78rem; }}
  .badge {{ display: inline-flex; align-items: center; padding: 2px 8px;
           border-radius: 12px; font-weight: 500; }}
  .badge-platform {{ background: #eff6ff; color: #1d4ed8; }}
  .badge-service {{ background: #f0fdf4; color: #166534; }}
  .badge-conf {{ background: #fef3c7; color: #92400e; }}
  .lead-reasoning {{ font-size: 0.82rem; color: #555; margin-top: 8px;
                    padding-top: 8px; border-top: 1px solid #f0f0f0; }}
  .reply-section {{ margin-top: 10px; padding-top: 10px; border-top: 1px solid #f0f0f0; }}
  .reply-label {{ font-size: 0.7rem; font-weight: 600; text-transform: uppercase;
                 letter-spacing: 0.5px; color: #888; margin-bottom: 5px; }}
  .reply-text {{ font-size: 0.82rem; color: #333; line-height: 1.55;
                background: #f8f9ff; border-left: 3px solid #93c5fd;
                padding: 8px 10px; border-radius: 0 6px 6px 0; white-space: pre-wrap; }}
  .copy-btn, .replied-btn {{ margin-top: 6px; padding: 3px 10px; font-size: 0.75rem; font-weight: 500;
              background: #fff; border: 1px solid #d1d5db; border-radius: 5px;
              cursor: pointer; color: #555; transition: all 0.15s; }}
  .copy-btn {{ margin-right: 4px; }}
  .copy-btn:hover, .replied-btn:hover {{ background: #f0f0f0; border-color: #aaa; }}
  .copy-btn.copied {{ background: #d1fae5; border-color: #6ee7b7; color: #065f46; }}
  .replied-btn.done {{ background: #d1fae5; border-color: #6ee7b7; color: #065f46; }}
  .empty {{ text-align: center; padding: 48px 20px; color: #888; font-size: 0.9rem; }}
  .footer {{ text-align: center; font-size: 0.75rem; color: #aaa; margin-top: 40px; }}
</style>
</head>
<body>
<div class="header">
  <h1>socrates<span>-finds-you</span></h1>
  <div class="sub">Daily Lead Report — {date_str}</div>
</div>
<div class="stats">
  <div class="stat total"><div class="stat-num">{total}</div><div class="stat-label">Total leads</div></div>
  <div class="divider"></div>
  <div class="stat high"><div class="stat-num">{h}</div><div class="stat-label">High value</div></div>
  <div class="stat medium"><div class="stat-num">{m}</div><div class="stat-label">Medium value</div></div>
  <div class="stat low"><div class="stat-num">{lo}</div><div class="stat-label">Low value</div></div>
</div>
<div class="main">
{cards_html}
{no_leads_msg}
  <div class="footer">Generated {now_utc.strftime("%Y-%m-%d %H:%M:%S")} Seattle time</div>
</div>
<script>
function copyReply(id, btn) {{
  var text = document.getElementById(id).textContent;
  navigator.clipboard.writeText(text).then(function() {{
    btn.textContent = 'Copied!';
    btn.classList.add('copied');
    setTimeout(function() {{ btn.textContent = 'Copy'; btn.classList.remove('copied'); }}, 2000);
  }});
}}
function markReplied(btn) {{
  btn.textContent = '✅ Replied';
  btn.classList.add('done');
}}
</script>
</body>
</html>"""


def generate_report() -> str:
    now = datetime.now(ZoneInfo("America/Los_Angeles"))
    date_str = now.strftime("%Y-%m-%d")

    OUTPUT_DIR.mkdir(exist_ok=True)

    signals = get_report_candidates(date_str)
    signals.sort(key=lambda s: TIER_ORDER.get((s.get("client_tier") or "low").lower(), 99))

    md_path = OUTPUT_DIR / f"report_{date_str}.md"
    html_path = OUTPUT_DIR / f"report_{date_str}.html"

    md_path.write_text(_build_markdown(signals, date_str, now), encoding="utf-8")
    html_path.write_text(_build_html(signals, date_str, now), encoding="utf-8")

    logger.info("[reporter] Saved: %s and %s (%d leads)", md_path, html_path, len(signals))
    return str(html_path)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    path = generate_report()
    print(f"Report saved to {path}")
