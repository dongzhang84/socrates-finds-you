"""
socrates-finds-you — Local Web UI
Run: python3 app.py
Visit: http://localhost:5000
"""

import sqlite3
import subprocess
import threading
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

from flask import Flask, jsonify, render_template_string

app = Flask(__name__)

DB_PATH = "data/signals.db"
OUTPUT_DIR = Path("output")

# Pipeline run state (in-memory, single process)
_pipeline_state = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "exit_code": None,
    "log": "",
}
_state_lock = threading.Lock()


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _get_leads(hours: int = 48) -> list[dict]:
    """Return matched signals scraped within the last `hours` hours, newest first."""
    if not Path(DB_PATH).exists():
        return []
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT id, platform, subreddit, title, url, service_match,
                   client_tier, confidence, reasoning, posted_at, scraped_at
            FROM signals
            WHERE matched = TRUE AND scraped_at >= ?
            ORDER BY scraped_at DESC
            """,
            (cutoff,),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def _db_stats() -> dict:
    """Return total / matched / unmatched counts."""
    if not Path(DB_PATH).exists():
        return {"total": 0, "matched": 0, "unmatched": 0}
    conn = sqlite3.connect(DB_PATH)
    try:
        total = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
        matched = conn.execute("SELECT COUNT(*) FROM signals WHERE matched=TRUE").fetchone()[0]
    except Exception:
        total = matched = 0
    finally:
        conn.close()
    return {"total": total, "matched": matched, "unmatched": total - matched}


def _latest_report_time() -> str | None:
    """Return modification time of today's (or most recent) report."""
    reports = sorted(OUTPUT_DIR.glob("report_*.md"), reverse=True)
    if not reports:
        return None
    mtime = reports[0].stat().st_mtime
    dt = datetime.fromtimestamp(mtime, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M UTC")


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------

def _run_pipeline():
    with _state_lock:
        _pipeline_state["running"] = True
        _pipeline_state["started_at"] = datetime.now(timezone.utc).isoformat()
        _pipeline_state["finished_at"] = None
        _pipeline_state["exit_code"] = None
        _pipeline_state["log"] = ""

    try:
        proc = subprocess.Popen(
            ["python3", "main.py", "--reddit-only"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        log_lines = []
        for line in proc.stdout:
            log_lines.append(line.rstrip())
            with _state_lock:
                _pipeline_state["log"] = "\n".join(log_lines[-200:])  # keep last 200 lines
        proc.wait()
        with _state_lock:
            _pipeline_state["exit_code"] = proc.returncode
            _pipeline_state["log"] = "\n".join(log_lines)
    except Exception as exc:
        with _state_lock:
            _pipeline_state["log"] += f"\n[error] {exc}"
            _pipeline_state["exit_code"] = -1
    finally:
        with _state_lock:
            _pipeline_state["running"] = False
            _pipeline_state["finished_at"] = datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>socrates-finds-you</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         background: #f5f5f5; color: #1a1a1a; line-height: 1.5; }

  /* Header */
  .header { background: #1a1a2e; color: #fff; padding: 20px 32px;
            display: flex; align-items: center; justify-content: space-between;
            flex-wrap: wrap; gap: 12px; }
  .header h1 { font-size: 1.3rem; font-weight: 600; letter-spacing: -0.3px; }
  .header h1 span { color: #7c9eff; }
  .meta { font-size: 0.8rem; color: #aaa; }

  /* Stats bar */
  .stats { background: #fff; border-bottom: 1px solid #e5e5e5;
           padding: 14px 32px; display: flex; align-items: center; gap: 24px;
           flex-wrap: wrap; }
  .stat { text-align: center; }
  .stat-num { font-size: 1.4rem; font-weight: 700; }
  .stat-label { font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.5px; color: #888; }
  .stat.high .stat-num { color: #e53e3e; }
  .stat.medium .stat-num { color: #d97706; }
  .stat.low .stat-num { color: #38a169; }
  .stat.total .stat-num { color: #3b82f6; }
  .divider { width: 1px; height: 36px; background: #e5e5e5; }

  /* Run button */
  .run-wrap { margin-left: auto; display: flex; align-items: center; gap: 10px; }
  #run-btn { padding: 8px 20px; background: #3b82f6; color: #fff;
             border: none; border-radius: 6px; font-size: 0.875rem; font-weight: 500;
             cursor: pointer; transition: background 0.15s; }
  #run-btn:hover:not(:disabled) { background: #2563eb; }
  #run-btn:disabled { background: #93c5fd; cursor: not-allowed; }
  #run-status { font-size: 0.8rem; color: #555; }

  /* Main layout */
  .main { max-width: 920px; margin: 28px auto; padding: 0 20px 60px; }

  /* Tier section */
  .tier-section { margin-bottom: 32px; }
  .tier-header { display: flex; align-items: center; gap: 10px;
                 padding: 10px 0; border-bottom: 2px solid; margin-bottom: 14px; }
  .tier-header.high { border-color: #e53e3e; }
  .tier-header.medium { border-color: #d97706; }
  .tier-header.low { border-color: #38a169; }
  .tier-title { font-size: 0.95rem; font-weight: 600; text-transform: uppercase;
                letter-spacing: 0.4px; }
  .tier-count { font-size: 0.78rem; color: #888;
                background: #f0f0f0; border-radius: 10px; padding: 1px 8px; }

  /* Lead card */
  .lead { background: #fff; border: 1px solid #e8e8e8; border-radius: 10px;
          padding: 16px 18px; margin-bottom: 10px;
          transition: box-shadow 0.15s; }
  .lead:hover { box-shadow: 0 3px 12px rgba(0,0,0,0.08); }
  .lead-title { font-size: 0.95rem; font-weight: 600; margin-bottom: 8px; color: #111; }
  .lead-title a { color: inherit; text-decoration: none; }
  .lead-title a:hover { text-decoration: underline; color: #2563eb; }
  .lead-meta { display: flex; flex-wrap: wrap; gap: 6px; font-size: 0.78rem; }
  .badge { display: inline-flex; align-items: center; gap: 3px;
           padding: 2px 8px; border-radius: 12px; font-weight: 500; }
  .badge-platform { background: #eff6ff; color: #1d4ed8; }
  .badge-service  { background: #f0fdf4; color: #166534; }
  .badge-conf-high   { background: #fef3c7; color: #92400e; }
  .badge-conf-medium { background: #fff7ed; color: #9a3412; }
  .badge-conf-low    { background: #fafafa; color: #555; }
  .lead-reasoning { font-size: 0.82rem; color: #555; margin-top: 8px;
                    padding-top: 8px; border-top: 1px solid #f0f0f0; }

  /* Empty state */
  .empty { text-align: center; padding: 48px 20px; color: #888; font-size: 0.9rem; }
  .empty p { margin-bottom: 8px; }

  /* Log drawer */
  #log-drawer { display: none; background: #111; color: #d4d4d4;
                border-radius: 8px; padding: 16px; margin-top: 16px;
                font-family: "SF Mono", "Fira Code", monospace; font-size: 0.75rem;
                max-height: 320px; overflow-y: auto; white-space: pre-wrap; }

  .spinner { display: inline-block; width: 14px; height: 14px;
             border: 2px solid #fff; border-top-color: transparent;
             border-radius: 50%; animation: spin 0.6s linear infinite;
             vertical-align: middle; margin-right: 4px; }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
</head>
<body>

<div class="header">
  <h1>socrates<span>-finds-you</span></h1>
  <div class="meta" id="last-updated">
    {% if last_report %}Last report: {{ last_report }}{% else %}No report yet{% endif %}
  </div>
</div>

<div class="stats">
  <div class="stat total"><div class="stat-num">{{ stats.total }}</div><div class="stat-label">Total signals</div></div>
  <div class="divider"></div>
  <div class="stat high"><div class="stat-num">{{ counts.high }}</div><div class="stat-label">High value</div></div>
  <div class="stat medium"><div class="stat-num">{{ counts.medium }}</div><div class="stat-label">Medium value</div></div>
  <div class="stat low"><div class="stat-num">{{ counts.low }}</div><div class="stat-label">Low value</div></div>
  <div class="run-wrap">
    <span id="run-status"></span>
    <button id="run-btn" onclick="runPipeline()">▶ Run Pipeline</button>
  </div>
</div>

<div class="main">

  {% for tier, emoji, label, cls in [
      ("high",   "🔴", "High Value — PhD / Professionals",   "high"),
      ("medium", "🟡", "Medium Value — College / Early Career", "medium"),
      ("low",    "🟢", "Low Value — High School / Students",  "low"),
  ] %}
  <div class="tier-section">
    <div class="tier-header {{ cls }}">
      <span>{{ emoji }}</span>
      <span class="tier-title">{{ label }}</span>
      <span class="tier-count">{{ leads_by_tier[tier]|length }}</span>
    </div>

    {% if leads_by_tier[tier] %}
      {% for lead in leads_by_tier[tier] %}
      <div class="lead">
        <div class="lead-title">
          <a href="{{ lead.url }}" target="_blank" rel="noopener">{{ lead.title }}</a>
        </div>
        <div class="lead-meta">
          <span class="badge badge-platform">
            {{ lead.platform }}{% if lead.subreddit %} · r/{{ lead.subreddit }}{% endif %}
          </span>
          {% if lead.service_match %}
          <span class="badge badge-service">{{ lead.service_match }}</span>
          {% endif %}
          {% if lead.confidence %}
          <span class="badge badge-conf-{{ lead.confidence }}">{{ lead.confidence }} confidence</span>
          {% endif %}
        </div>
        {% if lead.reasoning %}
        <div class="lead-reasoning">{{ lead.reasoning }}</div>
        {% endif %}
      </div>
      {% endfor %}
    {% else %}
      <div style="color:#aaa;font-size:0.85rem;padding:10px 2px;font-style:italic;">No leads in this tier.</div>
    {% endif %}
  </div>
  {% endfor %}

  {% if total_leads == 0 %}
  <div class="empty">
    <p>No matched leads in the last 48 hours.</p>
    <p>Click <strong>Run Pipeline</strong> to scrape and match new signals.</p>
  </div>
  {% endif %}

  <div id="log-drawer"></div>

</div>

<script>
let pollTimer = null;

function runPipeline() {
  const btn = document.getElementById('run-btn');
  const status = document.getElementById('run-status');
  const log = document.getElementById('log-drawer');

  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>Running…';
  status.textContent = '';
  log.style.display = 'block';
  log.textContent = 'Starting pipeline…\\n';

  fetch('/run', { method: 'POST' })
    .then(r => r.json())
    .then(data => {
      if (data.error) {
        btn.disabled = false;
        btn.innerHTML = '▶ Run Pipeline';
        status.textContent = data.error;
        return;
      }
      pollTimer = setInterval(pollStatus, 1500);
    })
    .catch(err => {
      btn.disabled = false;
      btn.innerHTML = '▶ Run Pipeline';
      status.textContent = 'Request failed';
    });
}

function pollStatus() {
  fetch('/status')
    .then(r => r.json())
    .then(data => {
      const log = document.getElementById('log-drawer');
      const btn = document.getElementById('run-btn');
      const status = document.getElementById('run-status');

      log.textContent = data.log || '(no output yet)';
      log.scrollTop = log.scrollHeight;

      if (!data.running) {
        clearInterval(pollTimer);
        btn.disabled = false;
        btn.innerHTML = '▶ Run Pipeline';

        if (data.exit_code === 0) {
          status.textContent = '✓ Done — refreshing…';
          setTimeout(() => location.reload(), 1200);
        } else {
          status.textContent = '✗ Pipeline exited with code ' + data.exit_code;
        }
      }
    });
}
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    leads = _get_leads(hours=48)

    tier_order = {"high": 0, "medium": 1, "low": 2}
    leads.sort(key=lambda s: tier_order.get((s.get("client_tier") or "low").lower(), 99))

    leads_by_tier: dict[str, list] = {"high": [], "medium": [], "low": []}
    for lead in leads:
        tier = (lead.get("client_tier") or "low").lower()
        leads_by_tier.setdefault(tier, []).append(lead)

    counts = {t: len(v) for t, v in leads_by_tier.items()}
    stats = _db_stats()

    return render_template_string(
        PAGE,
        leads_by_tier=leads_by_tier,
        counts=counts,
        stats=stats,
        total_leads=len(leads),
        last_report=_latest_report_time(),
    )


@app.route("/run", methods=["POST"])
def run():
    with _state_lock:
        if _pipeline_state["running"]:
            return jsonify({"error": "Pipeline already running"}), 409
    thread = threading.Thread(target=_run_pipeline, daemon=True)
    thread.start()
    return jsonify({"ok": True})


@app.route("/status")
def status():
    with _state_lock:
        return jsonify({
            "running": _pipeline_state["running"],
            "started_at": _pipeline_state["started_at"],
            "finished_at": _pipeline_state["finished_at"],
            "exit_code": _pipeline_state["exit_code"],
            "log": _pipeline_state["log"],
        })


if __name__ == "__main__":
    print("socrates-finds-you UI → http://localhost:5000")
    app.run(debug=False, port=5000)
