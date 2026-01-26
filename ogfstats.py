import argparse
import json
import sys
import time
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.request import urlopen, Request
import xml.etree.ElementTree as ET

# --- CONFIGURATION ---
OGF_CHANGESETS_URL = "https://opengeofiction.net/api/0.6/changesets"
VERSION = "3.2"
TARGET_DIR = Path("/var/www/ogfstats")

VERSION_HISTORY = [
    {"v": "3.2", "date": "2026-01-26", "note": "Created local and public versions. Optimized public for static hosting in /var/www/."},
    {"v": "3.1", "date": "2026-01-26", "note": "Added version history, hopefully improved data saving."},
    {"v": "3.0", "date": "2026-01-26", "note": "Added monthly stats, separated charts from tables."},
    {"v": "2.0", "date": "2025-08-22", "note": "First documented version."}
]

INDEX_HTML = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>OGFStats</title>
  
  <script async src="https://www.googletagmanager.com/gtag/js?id=G-7BV9Y2QVPZ"></script>
  <script>
    window.dataLayer = window.dataLayer || [];
    function gtag(){{dataLayer.push(arguments);}}
    gtag('js', new Date());
    gtag('config', 'G-7BV9Y2QVPZ');
  </script>

  <script src="https://code.highcharts.com/highcharts.js"></script>
  <script src="https://code.highcharts.com/modules/exporting.js"></script>
  <script src="https://code.highcharts.com/modules/full-screen.js"></script>
  <style>
    body {{ font-family: sans-serif; background: #fafafa; margin:0; padding:0; }}
    .nav {{ background: #333; color: white; padding: 10px; display: flex; justify-content: center; gap: 20px; position: sticky; top: 0; z-index: 1000; }}
    .nav a {{ color: #ccc; text-decoration: none; font-weight: bold; cursor: pointer; padding: 5px 15px; border-radius: 4px; }}
    .nav a:hover {{ color: white; background: #444; }}
    .nav a.active {{ color: white; background: #007bff; }}
    .wrap {{ max-width: 1300px; margin: 24px auto; padding: 16px; background: #fff; border-radius: 16px; box-shadow: 0 10px 30px rgba(0,0,0,0.06); }}
    .page {{ display: none; }}
    .page.active {{ display: block; }}
    h1 {{ font-size: 22px; margin: 0 0 8px; }}
    p.meta {{ margin: 0 0 16px; color: #666; font-size: 14px; }}
    .charts {{ display: flex; gap: 16px; margin-bottom: 24px; }}
    #chart, #chartDiff {{ flex: 1; height: 520px; }}
    .btns {{ margin-bottom: 12px; }}
    button {{ padding: 6px 12px; margin-right: 8px; border:1px solid #ddd; border-radius: 6px; background:#f5f5f5; cursor:pointer; }}
    button.active {{ background:#007bff; color:white; }}
    .leaderboard-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); gap: 16px; }}
    .leaderboard-card {{ background: #fff; border-radius: 16px; box-shadow: 0 4px 16px rgba(0,0,0,0.05); padding: 16px; }}
    .leaderboard-card h2 {{ font-size: 18px; margin: 0 0 12px; border-bottom: 2px solid #007bff; padding-bottom: 5px; }}
    table {{ width: 100%; border-collapse: separate; border-spacing: 0; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.05); }}
    thead tr {{ background: #007bff; color: #fff; font-weight: bold; }}
    thead tr th {{ padding: 10px; text-align: left; font-size: 14px; }}
    tbody tr td {{ padding: 10px; font-size: 14px; border-top: 1px solid #007bff33; }}
    tbody tr:hover {{ background: #f5f9ff; }}
    .version-item {{ border-bottom: 1px solid #eee; padding: 10px 0; }}
    .version-tag {{ background: #eee; padding: 2px 6px; border-radius: 4px; font-size: 12px; font-weight: bold; }}
  </style>
</head>
<body>
  <div class="nav">
    <a id="navCharts" class="active" onclick="showPage('chartsPage')">Charts</a>
    <a id="navLeaderboards" onclick="showPage('leaderboardPage')">Leaderboards</a>
    <a id="navVersion" onclick="showPage('versionPage')">v{VERSION}</a>
  </div>
  <div class="wrap">
    <div id="chartsPage" class="page active">
        <h1>Changeset ID Over Time</h1>
        <p class="meta">Viewing current month data. File resets every 1st of the month.</p>
        <div class="btns">
          <button id="btnHourly" class="active">Hourly</button>
          <button id="btnDaily">Daily</button>
        </div>
        <div class="charts">
          <div id="chart"></div>
          <div id="chartDiff"></div>
        </div>
    </div>
    <div id="leaderboardPage" class="page">
        <h1>Leaderboards</h1>
        <div class="leaderboard-grid">
          <div class="leaderboard-card">
            <h2>Hourly</h2>
            <table id="hourlyTable">
              <thead><tr><th>User</th><th>UID</th><th>Edits</th><th>Objects</th></tr></thead>
              <tbody></tbody>
            </table>
          </div>
          <div class="leaderboard-card">
            <h2>Daily (Rolling 24h)</h2>
            <table id="dailyTable">
              <thead><tr><th>User</th><th>UID</th><th>Edits</th><th>Objects</th></tr></thead>
              <tbody></tbody>
            </table>
          </div>
          <div class="leaderboard-card">
            <h2>Monthly (Current)</h2>
            <table id="monthlyTable">
              <thead><tr><th>User</th><th>UID</th><th>Edits</th><th>Objects</th></tr></thead>
              <tbody></tbody>
            </table>
          </div>
        </div>
    </div>
    <div id="versionPage" class="page">
        <h1>Version History</h1>
        <div id="versionList"></div>
    </div>
  </div>
<script>
let mode = 'hourly';
let rawData = null;
const history = {json.dumps(VERSION_HISTORY)};

function showPage(pageId) {{
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.nav a').forEach(a => a.classList.remove('active'));
    document.getElementById(pageId).classList.add('active');
    
    // Google Analytics Event Tracking
    if (typeof gtag === 'function') {{
        gtag('event', 'page_view', {{
            page_title: pageId,
            page_path: '/' + pageId
        }});
    }}

    if(pageId === 'chartsPage') {{
        document.getElementById('navCharts').classList.add('active');
        if(rawData) updateCharts(rawData[mode]);
    }} else if(pageId === 'leaderboardPage') {{
        document.getElementById('navLeaderboards').classList.add('active');
    }} else {{
        document.getElementById('navVersion').classList.add('active');
        renderVersionHistory();
    }}
}}

function renderVersionHistory() {{
    const container = document.getElementById('versionList');
    container.innerHTML = history.map(v => `
        <div class="version-item">
            <span class="version-tag">v${{v.v}}</span> <strong>${{v.date}}</strong>
            <p>${{v.note}}</p>
        </div>
    `).join('');
}}

async function load() {{
  try {{
    const resp = await fetch('data.json', {{ cache: 'no-store' }});
    rawData = await resp.json();
    updateCharts(rawData[mode]);
    updateLeaderboards(rawData);
  }} catch(e) {{ console.error("Data load failed", e); }}
}}

function updateCharts(entries) {{
  if(!entries) return;
  const sorted = entries.sort((a,b)=>Date.parse(a.timestamp)-Date.parse(b.timestamp));
  const series = sorted.map(d => [Date.parse(d.timestamp), Number(d.changeset_id)]);
  const diffSeries = sorted.map(d => [Date.parse(d.timestamp), d.change ?? 0]);
  Highcharts.chart('chart', {{
    chart: {{ zoomType: 'x' }},
    title: {{ text: mode === 'hourly' ? 'Hourly Changeset IDs' : 'Daily Changeset IDs' }},
    xAxis: {{ type: 'datetime' }},
    yAxis: {{ title: {{ text: 'ID' }} }},
    legend: {{ enabled: false }},
    series: [{{ type: 'line', data: series }}],
    credits: {{ enabled: false }}
  }});
  Highcharts.chart('chartDiff', {{
    chart: {{ type: 'column', zoomType: 'x' }},
    title: {{ text: mode === 'hourly' ? 'Hourly Change' : 'Daily Change' }},
    xAxis: {{ type: 'datetime' }},
    yAxis: {{ title: {{ text: 'Change' }} }},
    legend: {{ enabled: false }},
    series: [{{ data: diffSeries }}],
    credits: {{ enabled: false }}
  }});
}}

function updateLeaderboards(data) {{
  fillTable('hourlyTable', data.hourly_leaderboards?.slice(-1)[0]?.leaderboard || []);
  fillTable('dailyTable', data.daily_leaderboard || []);
  fillTable('monthlyTable', data.monthly_leaderboard || []);
}}

function fillTable(tableId, list) {{
    const body = document.querySelector(`#${{tableId}} tbody`);
    body.innerHTML = '';
    list.forEach(u => {{
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${{u.user}}</td><td>${{u.uid}}</td><td>${{u.count}}</td><td>${{u.objects}}</td>`;
        body.appendChild(tr);
    }});
}}

document.getElementById('btnHourly').addEventListener('click', ()=>{{ mode = 'hourly'; load(); }});
document.getElementById('btnDaily').addEventListener('click', ()=>{{ mode = 'daily'; load(); }});
load();
</script>
</body>
</html>
"""

# ... [The rest of the Python logic remains identical to your v3.2 script] ...

def get_initial_data():
    return {
        "hourly": [], "daily": [], "hourly_leaderboards": [], 
        "rolling24": [], "monthly_store": [], "monthly_leaderboard": [],
        "last_month_update": ""
    }

def fetch_first_changeset_id(url: str) -> int:
    req = Request(url, headers={"User-Agent": f"ogf-stats-script/{VERSION}"})
    with urlopen(req, timeout=20) as resp:
        xml_bytes = resp.read()
    root = ET.fromstring(xml_bytes)
    first = root.find('changeset')
    return int(first.get('id')) if first is not None else 0

def fetch_changesets_for_hour(start: datetime):
    url = f"{OGF_CHANGESETS_URL}?time={start.strftime('%Y-%m-%dT%H:00:00Z')}"
    req = Request(url, headers={"User-Agent": f"ogf-stats-script/{VERSION}"})
    with urlopen(req, timeout=20) as resp:
        xml_bytes = resp.read()
    root = ET.fromstring(xml_bytes)
    return [{"user": cs.get("user"), "uid": cs.get("uid"), "changes_count": int(cs.get("changes_count", "0"))}
            for cs in root.findall("changeset")]

def tally_users(entries):
    counts = {}
    for e in entries:
        key = (e["user"], e["uid"])
        if key not in counts: counts[key] = {"count": 0, "objects": 0}
        counts[key]["count"] += 1
        counts[key]["objects"] += e.get("changes_count", 0)
    return [{"user": u, "uid": uid, "count": c["count"], "objects": c["objects"]}
            for (u, uid), c in sorted(counts.items(), key=lambda kv: (kv[1]["count"], kv[1]["objects"]), reverse=True)]

def update_data_file(out_json: Path, hour_start: datetime, cid: int, entries: list):
    data = get_initial_data()
    if out_json.exists():
        try: data = json.loads(out_json.read_text(encoding="utf-8") or "{}")
        except: pass

    current_month_str = hour_start.strftime("%Y-%m")
    last_update_ts = data.get("last_month_update", "")
    
    if last_update_ts:
        last_month = last_update_ts[:7]
        if current_month_str != last_month:
            archive_dir = out_json.parent / "monthly_archives"
            archive_dir.mkdir(parents=True, exist_ok=True)
            archive_path = archive_dir / f"{last_month}.json"
            archive_path.write_text(json.dumps(data, indent=2))
            
            temp_rolling = data.get("rolling24", [])
            data = get_initial_data()
            data["rolling24"] = temp_rolling 
            print(f"[{hour_start}] New month: Archive created & data reset.")

    data["last_month_update"] = hour_start.strftime("%Y-%m-%dT%H:%M:%SZ")
    ts_str = hour_start.strftime("%Y-%m-%dT%H:%M:%SZ")
    
    # Charts
    h_list = data.setdefault("hourly", [])
    h_change = 0 if not h_list else cid - h_list[-1]["changeset_id"]
    h_list.append({"timestamp": ts_str, "changeset_id": cid, "change": h_change})
    
    if hour_start.hour == 0:
        d_list = data.setdefault("daily", [])
        d_change = 0 if not d_list else cid - d_list[-1]["changeset_id"]
        d_list.append({"timestamp": ts_str, "changeset_id": cid, "change": d_change})

    # Leaderboards
    data.setdefault("hourly_leaderboards", []).append({"timestamp": ts_str, "leaderboard": tally_users(entries)})
    data["hourly_leaderboards"] = data["hourly_leaderboards"][-48:]
    
    data.setdefault("rolling24", []).append({"timestamp": ts_str, "entries": entries})
    cutoff = hour_start - timedelta(hours=24)
    data["rolling24"] = [r for r in data["rolling24"] if datetime.fromisoformat(r["timestamp"].replace("Z", "+00:00")).replace(tzinfo=timezone.utc) >= cutoff]
    
    data["daily_leaderboard"] = tally_users([e for r in data["rolling24"] for e in r["entries"]])
    data.setdefault("monthly_store", []).extend(entries)
    data["monthly_leaderboard"] = tally_users(data["monthly_store"])

    out_json.write_text(json.dumps(data, indent=2), encoding="utf-8")

def main():
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    index_file = TARGET_DIR / "index.html"
    index_file.write_text(INDEX_HTML, encoding='utf-8')
    data_file = TARGET_DIR / "data.json"

    print(f"OGFStats Collector v{VERSION} running. Writing to {TARGET_DIR}")

    while True:
        now = datetime.now(timezone.utc)
        hour_start = now.replace(minute=0, second=0, microsecond=0)
        try:
            cid = fetch_first_changeset_id(OGF_CHANGESETS_URL)
            entries = fetch_changesets_for_hour(hour_start)
            update_data_file(data_file, hour_start, cid, entries)
            print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Update OK.")
        except Exception as e:
            print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Error: {e}")

        next_run = (now + timedelta(hours=1)).replace(minute=0, second=5, microsecond=0)
        time.sleep(max(1, (next_run - now).total_seconds()))

if __name__ == "__main__":
    main()
