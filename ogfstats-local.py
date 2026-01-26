import argparse
import json
import sys
import time
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.request import urlopen, Request
import xml.etree.ElementTree as ET
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import socket

# --- CONFIGURATION ---
OGF_CHANGESETS_URL = "https://opengeofiction.net/api/0.6/changesets"
VERSION = "3.2"
VERSION_HISTORY = [
    {"v": "3.2", "date": "2026-01-26", "note": "Created local and public versions. No changes to local"},
    {"v": "3.1", "date": "2026-01-26", "note": "Added version history, hopefully improved data saving."},
    {"v": "3.0", "date": "2026-01-26", "note": "Added monthly stats, seperated charts from tables into two pages (can be navigated between with the top menu)"},
    {"v": "2.0", "date": "2025-08-22", "note": "First documented version of ogfedit (no clue what happened to v1). Includes hourly/daily stats for changeset id and by-user stats (again, hourly and daily)"}
]

INDEX_HTML = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>OGFStats</title>
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

def get_initial_data():
    return {
        "hourly": [], 
        "daily": [], 
        "hourly_leaderboards": [], 
        "rolling24": [], 
        "monthly_store": [], 
        "monthly_leaderboard": [],
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
    return [
        {"user": cs.get("user"), "uid": cs.get("uid"), "changes_count": int(cs.get("changes_count", "0"))}
        for cs in root.findall("changeset")
    ]

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
    # Load or initialize
    data = get_initial_data()
    if out_json.exists():
        try: data = json.loads(out_json.read_text(encoding="utf-8") or "{}")
        except: pass

    # --- HARD RESET / ARCHIVE LOGIC ---
    current_month_str = hour_start.strftime("%Y-%m")
    last_update_ts = data.get("last_month_update", "")
    
    if last_update_ts:
        last_month = last_update_ts[:7]
        if current_month_str != last_month:
            # 1. Archive the old data
            archive_dir = out_json.parent / "monthly_archives"
            archive_dir.mkdir(exist_ok=True)
            archive_path = archive_dir / f"{last_month}.json"
            archive_path.write_text(json.dumps(data, indent=2))
            
            # 2. PERFORM HARD RESET (Wipe file content completely)
            temp_rolling = data.get("rolling24", []) # Keep rolling 24 for continuity
            data = get_initial_data()
            data["rolling24"] = temp_rolling 
            print(f"[{hour_start}] NEW MONTH DETECTED: Hard reset performed.")

    data["last_month_update"] = hour_start.strftime("%Y-%m-%dT%H:%M:%SZ")

    # --- UPDATE CHART DATA ---
    ts_str = hour_start.strftime("%Y-%m-%dT%H:%M:%SZ")
    
    # Hourly Chart
    mode_list = data.setdefault("hourly", [])
    change = 0 if not mode_list else cid - mode_list[-1]["changeset_id"]
    mode_list.append({"timestamp": ts_str, "changeset_id": cid, "change": change})
    
    # Daily Chart (only at midnight)
    if hour_start.hour == 0:
        d_list = data.setdefault("daily", [])
        d_change = 0 if not d_list else cid - d_list[-1]["changeset_id"]
        d_list.append({"timestamp": ts_str, "changeset_id": cid, "change": d_change})

    # --- UPDATE LEADERBOARD DATA ---
    # 1. Hourly Leaderboard
    data.setdefault("hourly_leaderboards", []).append({
        "timestamp": ts_str,
        "leaderboard": tally_users(entries)
    })
    data["hourly_leaderboards"] = data["hourly_leaderboards"][-48:] # Limit logs
    
    # 2. Rolling 24h Buffer
    data.setdefault("rolling24", []).append({"timestamp": ts_str, "entries": entries})
    cutoff = hour_start - timedelta(hours=24)
    data["rolling24"] = [r for r in data["rolling24"] if datetime.fromisoformat(r["timestamp"].replace("Z", "+00:00")).replace(tzinfo=timezone.utc) >= cutoff]
    
    all_24 = [e for r in data["rolling24"] for e in r["entries"]]
    data["daily_leaderboard"] = tally_users(all_24)

    # 3. Monthly Store
    data.setdefault("monthly_store", []).extend(entries)
    data["monthly_leaderboard"] = tally_users(data["monthly_store"])

    # Write back
    out_json.write_text(json.dumps(data, indent=2), encoding="utf-8")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()

    outdir = Path(__file__).parent.resolve()
    (outdir / "index.html").write_text(INDEX_HTML, encoding='utf-8')

    # Port management
    port = args.port
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("0.0.0.0", port))
    except: port = 0 # Random port if requested is busy

    import threading
    handler = lambda *a, **kw: SimpleHTTPRequestHandler(*a, directory=str(outdir), **kw)
    server = ThreadingHTTPServer(("0.0.0.0", port), handler)
    print(f"OGFStats v{VERSION} serving at http://localhost:{server.server_port}")
    threading.Thread(target=server.serve_forever, daemon=True).start()

    while True:
        now = datetime.now(timezone.utc)
        hour_start = now.replace(minute=0, second=0, microsecond=0)
        
        try:
            cid = fetch_first_changeset_id(OGF_CHANGESETS_URL)
            entries = fetch_changesets_for_hour(hour_start)
            update_data_file(outdir / "data.json", hour_start, cid, entries)
            print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Update successful.")
        except Exception as e:
            print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Error: {e}")

        # Sleep until 5 seconds past the next hour
        next_run = (now + timedelta(hours=1)).replace(minute=0, second=5, microsecond=0)
        time.sleep(max(1, (next_run - now).total_seconds()))

if __name__ == "__main__":
    main()
