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
VERSION = "3.3"
TARGET_DIR = Path("/var/www/ogfstats")

VERSION_HISTORY = [
    {"v": "3.3", "date": "2026-01-26", "note": "Refined monthly reset logic to preserve chart history."},
    {"v": "3.2", "date": "2026-01-26", "note": "Optimized for static hosting in /var/www/."},
    {"v": "3.1", "date": "2026-01-26", "note": "Updated file structure, version history tab added."},
    {"v": "3.0", "date": "2026-01-26", "note": "Added Monthly Leaderboards, split webpage into tabs."},
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
  <script src="https://code.highcharts.com/modules/accessibility.js"></script>
  <style>
    body {{ font-family: sans-serif; background: #fafafa; margin:0; padding:0; }}
    .nav {{ background: #333; color: white; padding: 10px; display: flex; justify-content: center; gap: 20px; position: sticky; top: 0; z-index: 1000; }}
    .nav a {{ color: #ccc; text-decoration: none; font-weight: bold; cursor: pointer; padding: 5px 15px; border-radius: 4px; transition: 0.2s; }}
    .nav a:hover {{ color: white; background: #444; }}
    .nav a.active {{ color: white; background: #007bff; }}
    .wrap {{ max-width: 1300px; margin: 24px auto; padding: 16px; background: #fff; border-radius: 16px; box-shadow: 0 10px 30px rgba(0,0,0,0.06); }}
    .page {{ display: none; }}
    .page.active {{ display: block; }}
    h1 {{ font-size: 22px; margin: 0 0 8px; }}
    .meta {{ color: #666; font-size: 14px; margin-bottom: 16px; }}
    .charts {{ display: flex; gap: 16px; margin-bottom: 24px; flex-wrap: wrap; }}
    #chart, #chartDiff {{ flex: 1; min-width: 400px; height: 500px; }}
    .btns {{ margin-bottom: 12px; }}
    button {{ padding: 6px 12px; border:1px solid #ddd; border-radius: 6px; background:#f5f5f5; cursor:pointer; }}
    button.active {{ background:#007bff; color:white; }}
    
    .leaderboard-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); gap: 16px; }}
    .leaderboard-card {{ background: #fff; border-radius: 16px; border: 1px solid #eee; padding: 16px; box-shadow: 0 4px 12px rgba(0,0,0,0.03); }}
    .leaderboard-card h2 {{ font-size: 18px; margin-top: 0; color: #333; border-bottom: 2px solid #007bff; display: inline-block; padding-bottom: 4px; }}
    .table-container {{ border-radius: 12px; overflow: hidden; border: 1px solid #007bff33; margin-top: 10px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th {{ background: #007bff; color: white; padding: 10px; text-align: left; cursor: pointer; font-size: 14px; user-select: none; }}
    th:hover {{ background: #0056b3; }}
    td {{ padding: 10px; border-bottom: 1px solid #eee; font-size: 13px; }}
    tr:last-child td {{ border-bottom: none; }}
    tr:hover {{ background: #f5f9ff; }}
    
    .version-item {{ border-bottom: 1px solid #eee; padding: 12px 0; }}
    .version-tag {{ background: #eee; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 12px; }}
    .footer {{ text-align: center; color: #999; font-size: 12px; margin: 40px 0; }}
  </style>
</head>
<body>
  <div class="nav">
    <a id="nav_chartsPage" class="active" onclick="showPage('chartsPage')">Charts</a>
    <a id="nav_leaderboardPage" onclick="showPage('leaderboardPage')">Leaderboards</a>
    <a id="nav_versionPage" onclick="showPage('versionPage')">v{VERSION}</a>
  </div>
  <div class="wrap">
    <div id="chartsPage" class="page active">
        <h1>Changeset Activity</h1>
        <p class="meta" id="updateTime">Loading data...</p>
        <div class="btns">
          <button id="btnHourly" class="active" onclick="setMode('hourly')">Hourly</button>
          <button id="btnDaily" onclick="setMode('daily')">Daily</button>
        </div>
        <div class="charts">
          <div id="chart"></div>
          <div id="chartDiff"></div>
        </div>
    </div>

    <div id="leaderboardPage" class="page">
        <h1>Leaderboards</h1>
        <p class="meta">Click headers to sort. Daily is a rolling 24-hour window.</p>
        <div class="leaderboard-grid">
          <div class="leaderboard-card">
            <h2>Hourly</h2>
            <div class="table-container">
              <table id="hourlyTable">
                <thead><tr><th>User</th><th>UID</th><th>Edits</th><th>Objs</th></tr></thead>
                <tbody></tbody>
              </table>
            </div>
          </div>
          <div class="leaderboard-card">
            <h2>Daily (Rolling 24h)</h2>
            <div class="table-container">
              <table id="dailyTable">
                <thead><tr><th>User</th><th>UID</th><th>Edits</th><th>Objs</th></tr></thead>
                <tbody></tbody>
              </table>
            </div>
          </div>
          <div class="leaderboard-card">
            <h2>Monthly</h2>
            <div class="table-container">
              <table id="monthlyTable">
                <thead><tr><th>User</th><th>UID</th><th>Edits</th><th>Objs</th></tr></thead>
                <tbody></tbody>
              </table>
            </div>
          </div>
        </div>
    </div>

    <div id="versionPage" class="page">
        <h1>Version History</h1>
        <div id="versionList"></div>
    </div>
  </div>
  <div class="footer">OGFStats by minimapper :)</div>

<script>
let mode = 'hourly';
let rawData = null;
const historyData = {json.dumps(VERSION_HISTORY)};

function showPage(pageId) {{
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.nav a').forEach(a => a.classList.remove('active'));
    
    document.getElementById(pageId).classList.add('active');
    document.getElementById('nav_' + pageId).classList.add('active');
    
    if (typeof gtag === 'function') {{
        gtag('event', 'page_view', {{ page_title: pageId, page_path: '/' + pageId }});
    }}
    if(pageId === 'chartsPage' && rawData) updateCharts(rawData[mode]);
    if(pageId === 'versionPage') renderVersionHistory();
}}

function setMode(m) {{
    mode = m;
    document.getElementById('btnHourly').classList.toggle('active', m === 'hourly');
    document.getElementById('btnDaily').classList.toggle('active', m === 'daily');
    updateCharts(rawData[mode]);
}}

function renderVersionHistory() {{
    const container = document.getElementById('versionList');
    container.innerHTML = historyData.map(v => `
        <div class="version-item">
            <span class="version-tag">v${{v.v}}</span> <strong>${{v.date}}</strong>
            <p style="margin: 8px 0 0; font-size: 14px; color: #444;">${{v.note}}</p>
        </div>
    `).join('');
}}

async function load() {{
  try {{
    const resp = await fetch('data.json', {{ cache: 'no-store' }});
    rawData = await resp.json();
    document.getElementById('updateTime').innerText = "Last Sync: " + rawData.last_month_update;
    updateCharts(rawData[mode]);
    updateLeaderboards(rawData);
    initSorting();
  }} catch(e) {{ console.error("Load failed", e); }}
}}

function updateCharts(entries) {{
  if(!entries) return;
  const series = entries.map(d => [Date.parse(d.timestamp), Number(d.changeset_id)]);
  const diffSeries = entries.map(d => [Date.parse(d.timestamp), d.change ?? 0]);
  
  Highcharts.chart('chart', {{
    accessibility: {{ enabled: true }},
    chart: {{ zoomType: 'x' }},
    title: {{ text: 'Changeset ID Trend' }},
    xAxis: {{ type: 'datetime' }},
    yAxis: {{ title: {{ text: 'ID' }} }},
    series: [{{ name: 'ID', data: series, color: '#007bff' }}],
    credits: {{ enabled: false }}
  }});
  
  Highcharts.chart('chartDiff', {{
    accessibility: {{ enabled: true }},
    chart: {{ type: 'column', zoomType: 'x' }},
    title: {{ text: 'Activity Volume' }},
    xAxis: {{ type: 'datetime' }},
    yAxis: {{ title: {{ text: 'New Changesets' }} }},
    series: [{{ name: 'Count', data: diffSeries, color: '#7cb5ec' }}],
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
    body.innerHTML = list.map(u => `<tr><td>${{u.user}}</td><td>${{u.uid}}</td><td>${{u.count}}</td><td>${{u.objects}}</td></tr>`).join('');
}}

function initSorting() {{
    document.querySelectorAll("th").forEach(th => {{
        th.addEventListener("click", () => {{
            const table = th.closest("table");
            const tbody = table.querySelector("tbody");
            const rows = Array.from(tbody.querySelectorAll("tr"));
            const index = Array.from(th.parentElement.children).indexOf(th);
            const ascending = !th.classList.contains("asc");

            rows.sort((a, b) => {{
                let valA = a.children[index].innerText;
                let valB = b.children[index].innerText;
                if (!isNaN(valA) && !isNaN(valB)) {{
                    return ascending ? valA - valB : valB - valA;
                }}
                return ascending ? valA.localeCompare(valB) : valB.localeCompare(valA);
            }});

            table.querySelectorAll("th").forEach(h => h.classList.remove("asc", "desc"));
            th.classList.toggle("asc", ascending);
            th.classList.toggle("desc", !ascending);
            tbody.innerHTML = "";
            rows.forEach(row => tbody.appendChild(row));
        }});
    }});
}}

load();
setInterval(load, 300000); 
</script>
</body>
</html>
"""

def get_initial_data():
    return {
        "hourly": [], "daily": [], "hourly_leaderboards": [], 
        "rolling24": [], "monthly_store": [], "monthly_leaderboard": [],
        "last_month_update": ""
    }

def fetch_first_changeset_id(url: str) -> int:
    req = Request(url, headers={"User-Agent": f"ogf-stats-script/{VERSION}"})
    with urlopen(req, timeout=20) as resp:
        return int(ET.fromstring(resp.read()).find('changeset').get('id'))

def fetch_changesets_for_hour(start: datetime):
    url = f"{OGF_CHANGESETS_URL}?time={start.strftime('%Y-%m-%dT%H:00:00Z')}"
    req = Request(url, headers={"User-Agent": f"ogf-stats-script/{VERSION}"})
    with urlopen(req, timeout=20) as resp:
        root = ET.fromstring(resp.read())
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
        try: data = json.loads(out_json.read_text(encoding="utf-8"))
        except: pass

    current_month_str = hour_start.strftime("%Y-%m")
    last_update_ts = data.get("last_month_update", "")
    if last_update_ts and current_month_str != last_update_ts[:7]:
        archive_dir = out_json.parent / "monthly_archives"
        archive_dir.mkdir(parents=True, exist_ok=True)
        archive_path = archive_dir / f"{last_update_ts[:7]}.json"
        archive_path.write_text(json.dumps(data, indent=2))
        data["monthly_store"] = []
        data["monthly_leaderboard"] = []
        print(f"Archived month {last_update_ts[:7]}")

    ts_str = hour_start.strftime("%Y-%m-%dT%H:%M:%SZ")
    data["last_month_update"] = ts_str
    
    h_list = data.setdefault("hourly", [])
    h_change = 0 if not h_list else cid - h_list[-1]["changeset_id"]
    h_list.append({"timestamp": ts_str, "changeset_id": cid, "change": h_change})
    data["hourly"] = h_list[-720:] 

    if hour_start.hour == 0:
        d_list = data.setdefault("daily", [])
        d_change = 0 if not d_list else cid - d_list[-1]["changeset_id"]
        d_list.append({"timestamp": ts_str, "changeset_id": cid, "change": d_change})

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
    
    while True:
        now = datetime.now(timezone.utc)
        hour_start = now.replace(minute=0, second=0, microsecond=0)
        try:
            cid = fetch_first_changeset_id(OGF_CHANGESETS_URL)
            entries = fetch_changesets_for_hour(hour_start)
            update_data_file(TARGET_DIR / "data.json", hour_start, cid, entries)
            print(f"[{now}] Update Success: {cid}")
        except Exception as e:
            print(f"[{now}] Error: {e}")

        next_run = (now + timedelta(hours=1)).replace(minute=0, second=5, microsecond=0)
        time.sleep(max(1, (next_run - now).total_seconds()))

if __name__ == "__main__":
    main()
