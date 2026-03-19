"""
socrates-finds-you — Local Web UI
Run: python3 app.py
Visit: http://localhost:8080
"""

import sqlite3
import subprocess
import threading
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

from flask import Flask, jsonify, render_template_string, request
from storage.db import init_db, mark_actioned

app = Flask(__name__)
init_db()  # ensures schema + migrations run on every startup

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

def _get_matched_dates() -> list[str]:
    """Return distinct dates (YYYY-MM-DD) that have matched signals, newest first."""
    if not Path(DB_PATH).exists():
        return []
    conn = sqlite3.connect(DB_PATH)
    try:
        rows = conn.execute(
            "SELECT DISTINCT DATE(scraped_at) FROM signals WHERE matched = TRUE ORDER BY scraped_at DESC"
        ).fetchall()
    finally:
        conn.close()
    return [r[0] for r in rows if r[0]]


def _get_leads(date: str) -> list[dict]:
    """Return matched signals scraped on the given date (YYYY-MM-DD), newest first."""
    if not Path(DB_PATH).exists():
        return []
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT id, platform, subreddit, title, url, service_match,
                   client_tier, confidence, reasoning, suggested_reply, posted_at, scraped_at,
                   actioned
            FROM signals
            WHERE matched = TRUE AND DATE(scraped_at) = ?
            ORDER BY scraped_at DESC
            """,
            (date,),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def _get_linkedin_signals(limit: int = 100) -> list[dict]:
    """Return all LinkedIn signals, newest first."""
    if not Path(DB_PATH).exists():
        return []
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT title, url, author, body, matched, service_match, scraped_at
            FROM signals
            WHERE platform = 'linkedin'
            ORDER BY scraped_at DESC
            LIMIT ?
            """,
            (limit,),
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


def _unmark_actioned(id: str) -> None:
    import sqlite3 as _sqlite3
    conn = _sqlite3.connect(DB_PATH)
    try:
        conn.execute("UPDATE signals SET actioned = FALSE WHERE id = ?", (id,))
        conn.commit()
    finally:
        conn.close()


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
            ["python3", "main.py"],
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

  /* Suggested reply */
  .reply-section { margin-top: 10px; padding-top: 10px; border-top: 1px solid #f0f0f0; }
  .reply-label { font-size: 0.7rem; font-weight: 600; text-transform: uppercase;
                 letter-spacing: 0.5px; color: #888; margin-bottom: 5px; }
  .reply-text { font-size: 0.82rem; color: #333; line-height: 1.55;
                background: #f8f9ff; border-left: 3px solid #93c5fd;
                padding: 8px 10px; border-radius: 0 6px 6px 0; white-space: pre-wrap; }
  .copy-btn { margin-top: 6px; padding: 3px 10px; font-size: 0.75rem; font-weight: 500;
              background: #fff; border: 1px solid #d1d5db; border-radius: 5px;
              cursor: pointer; color: #555; transition: all 0.15s; }
  .copy-btn:hover { background: #f0f0f0; border-color: #aaa; }
  .copy-btn.copied { background: #d1fae5; border-color: #6ee7b7; color: #065f46; }

  /* LinkedIn section */
  .linkedin-section { margin-top: 48px; }
  .linkedin-header { display: flex; align-items: center; gap: 10px;
                     padding: 10px 0; border-bottom: 2px solid #0a66c2; margin-bottom: 14px; }
  .linkedin-title { font-size: 0.95rem; font-weight: 600; text-transform: uppercase;
                    letter-spacing: 0.4px; color: #0a66c2; }
  .li-card { background: #fff; border: 1px solid #e8e8e8; border-radius: 10px;
             padding: 14px 18px; margin-bottom: 8px; transition: box-shadow 0.15s; }
  .li-card:hover { box-shadow: 0 3px 12px rgba(0,0,0,0.08); }
  .li-card-title { font-size: 0.92rem; font-weight: 600; margin-bottom: 5px; }
  .li-card-title a { color: #111; text-decoration: none; }
  .li-card-title a:hover { text-decoration: underline; color: #0a66c2; }
  .li-card-meta { font-size: 0.75rem; color: #888; margin-bottom: 6px; }
  .li-card-body { font-size: 0.82rem; color: #444; line-height: 1.5; }
  .badge-matched { background: #f0fdf4; color: #166534; }
  .badge-unmatched { background: #fafafa; color: #888; }

  /* Replied button */
  .replied-btn { margin-top: 6px; padding: 3px 10px; font-size: 0.75rem; font-weight: 500;
                 background: #fff; border: 1px solid #d1d5db; border-radius: 5px;
                 cursor: pointer; color: #555; transition: all 0.15s; }
  .replied-btn:hover { background: #f0f0f0; border-color: #aaa; }
  .replied-btn.done { background: #d1fae5; border-color: #6ee7b7; color: #065f46; cursor: pointer; }

  /* Date selector */
  .date-select { padding: 5px 10px; font-size: 0.82rem; border: 1px solid #d1d5db;
                 border-radius: 6px; background: #fff; color: #1a1a1a; cursor: pointer;
                 outline: none; }
  .date-select:focus { border-color: #3b82f6; box-shadow: 0 0 0 2px rgba(59,130,246,0.15); }

  /* Filter toggle */
  .filter-bar { display: flex; align-items: center; gap: 10px; margin-bottom: 20px; }
  .filter-bar label { font-size: 0.82rem; color: #555; font-weight: 500; }
  .toggle-wrap { display: flex; background: #f0f0f0; border-radius: 6px; padding: 2px; }
  .toggle-btn { padding: 4px 14px; border: none; border-radius: 5px; font-size: 0.78rem;
                font-weight: 500; cursor: pointer; background: transparent; color: #666;
                transition: all 0.15s; }
  .toggle-btn.active { background: #fff; color: #1a1a1a; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }

  /* Hidden-replied state */
  .lead.replied-hidden { display: none; }

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

  <div class="filter-bar">
    <label>Date:</label>
    <select class="date-select" onchange="location.href='/?date='+this.value">
      {% for opt in date_options %}
      <option value="{{ opt.value }}" {% if opt.value == selected_date %}selected{% endif %}>{{ opt.label }}</option>
      {% endfor %}
      {% if not date_options %}
      <option value="{{ selected_date }}">Today ({{ selected_date }})</option>
      {% endif %}
    </select>
    <div style="width:16px"></div>
    <label>Show:</label>
    <div class="toggle-wrap">
      <button class="toggle-btn active" id="btn-all" onclick="setFilter('all')">Show All</button>
      <button class="toggle-btn" id="btn-hide" onclick="setFilter('hide')">Hide Replied</button>
    </div>
  </div>

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
      <div class="lead{% if lead.actioned %} lead-actioned{% endif %}" data-id="{{ lead.id }}">
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
        {% if lead.suggested_reply %}
        <div class="reply-section">
          <div class="reply-label">Suggested reply</div>
          <div class="reply-text" id="reply-{{ loop.index0 }}-{{ tier }}">{{ lead.suggested_reply }}</div>
          <button class="copy-btn" onclick="copyReply('reply-{{ loop.index0 }}-{{ tier }}', this)">Copy</button>
          <button class="replied-btn{% if lead.actioned %} done{% endif %}"
                  onclick="markReplied(this)">
            {% if lead.actioned %}✅ Replied{% else %}Mark as Replied{% endif %}
          </button>
        </div>
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

  <!-- LinkedIn all signals -->
  <div class="linkedin-section">
    <div class="linkedin-header">
      <span>📌</span>
      <span class="linkedin-title">LinkedIn — All Signals</span>
      <span class="tier-count">{{ linkedin_signals|length }}</span>
    </div>

    {% if linkedin_signals %}
      {% for s in linkedin_signals %}
      <div class="li-card">
        <div class="li-card-title">
          <a href="{{ s.url }}" target="_blank" rel="noopener">{{ s.title }}</a>
        </div>
        <div class="li-card-meta">
          {% if s.author %}<strong>{{ s.author }}</strong> · {% endif %}
          {% if s.matched %}
            <span class="badge badge-matched">matched{% if s.service_match %}: {{ s.service_match }}{% endif %}</span>
          {% else %}
            <span class="badge badge-unmatched">unmatched</span>
          {% endif %}
        </div>
        {% if s.body %}
        <div class="li-card-body">{{ s.body[:200] }}{% if s.body|length > 200 %}…{% endif %}</div>
        {% endif %}
      </div>
      {% endfor %}
    {% else %}
      <div style="color:#aaa;font-size:0.85rem;padding:10px 2px;font-style:italic;">No LinkedIn signals in the database yet.</div>
    {% endif %}
  </div>

</div>

<script>
let pollTimer = null;
let currentFilter = 'all';

function setFilter(mode) {
  currentFilter = mode;
  document.getElementById('btn-all').classList.toggle('active', mode === 'all');
  document.getElementById('btn-hide').classList.toggle('active', mode === 'hide');
  document.querySelectorAll('.lead.lead-actioned').forEach(el => {
    el.classList.toggle('replied-hidden', mode === 'hide');
  });
}

// Apply default filter on load
document.addEventListener('DOMContentLoaded', () => setFilter('all'));

function markReplied(btn) {
  const card = btn.closest('.lead');
  const id = card.dataset.id;
  const isActioned = card.classList.contains('lead-actioned');
  fetch('/api/mark-replied', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id, actioned: !isActioned }),
  }).then(r => r.json()).then(data => {
    if (data.ok) {
      if (!isActioned) {
        card.classList.add('lead-actioned');
        btn.textContent = '✅ Replied';
        btn.classList.add('done');
      } else {
        card.classList.remove('lead-actioned', 'replied-hidden');
        btn.textContent = 'Mark as Replied';
        btn.classList.remove('done');
      }
    }
  });
}

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

function copyReply(id, btn) {
  const text = document.getElementById(id).textContent;
  navigator.clipboard.writeText(text).then(() => {
    btn.textContent = 'Copied!';
    btn.classList.add('copied');
    setTimeout(() => { btn.textContent = 'Copy'; btn.classList.remove('copied'); }, 2000);
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
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")

    matched_dates = _get_matched_dates()
    selected_date = request.args.get("date", "")
    if selected_date not in matched_dates:
        # Default to today if present, else most recent available date
        selected_date = today if today in matched_dates else (matched_dates[0] if matched_dates else today)

    def _label(d: str) -> str:
        if d == today:
            return f"Today ({d})"
        if d == yesterday:
            return f"Yesterday ({d})"
        return d

    date_options = [{"value": d, "label": _label(d)} for d in matched_dates]

    leads = _get_leads(selected_date)

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
        linkedin_signals=_get_linkedin_signals(),
        date_options=date_options,
        selected_date=selected_date,
    )


@app.route("/run", methods=["POST"])
def run():
    with _state_lock:
        if _pipeline_state["running"]:
            return jsonify({"error": "Pipeline already running"}), 409
    thread = threading.Thread(target=_run_pipeline, daemon=True)
    thread.start()
    return jsonify({"ok": True})


@app.route("/api/mark-replied", methods=["POST"])
def api_mark_replied():
    data = request.get_json(force=True)
    signal_id = data.get("id", "").strip()
    actioned = data.get("actioned", True)
    if not signal_id:
        return jsonify({"error": "missing id"}), 400
    if actioned:
        mark_actioned(signal_id)
    else:
        _unmark_actioned(signal_id)
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
    print("socrates-finds-you UI → http://localhost:8080")
    app.run(debug=False, port=8080)
