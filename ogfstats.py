import argparse
import json
import sys
import time
import os
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.request import urlopen, Request
import xml.etree.ElementTree as ET

# --- CONFIGURATION ---
OGF_CHANGESETS_URL = "https://opengeofiction.net/api/0.6/changesets"
VERSION = "5.1"
TARGET_DIR = Path("/var/www/ogfstats")

VERSION_HISTORY = [
    {"v": "5.1", "date": "2026-06-15", "note": "Added automatic system dark/light theme support across the entire site."},
    {"v": "5.0", "date": "2026-03-25", "note": "More stats!!!!"},
    {"v": "4.1", "date": "2026-01-28", "note": "Fixed errors with slashes and commas in place names (stupid me thought that would not happen and I put it in a CSV)"},
    {"v": "4.0", "date": "2026-01-28", "note": "New Territory Stats tab. TStats updates daily with node, way, and relation counts for each claimed territory. Seperated all tabss into unique pages to make farther expansion easier."},
    {"v": "3.3", "date": "2026-01-26", "note": "Refined monthly reset logic to preserve chart history."},
    {"v": "3.2", "date": "2026-01-26", "note": "Optimized for static hosting in /var/www/."},
    {"v": "3.1", "date": "2026-01-26", "note": "Updated file structure, version history tab added."},
    {"v": "3.0", "date": "2026-01-26", "note": "Added Monthly Leaderboards, split webpage into tabs."},
    {"v": "2.0", "date": "2025-08-22", "note": "First documented version."}
]


# --- SHARED COMPONENTS ---
NAV_BAR = f"""
  <div class="nav">
    <a href="index.html" id="nav_charts">Charts</a>
    <a href="leaderboards.html" id="nav_leaderboards">Leaderboards</a>
    <a href="territory.html" id="nav_territory">Territory Stats</a>
    <a href="version.html" id="nav_version">v{VERSION}</a>
  </div>
"""

GOOGLE_BLOCK = """
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7BV9Y2QVPZ"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){{dataLayer.push(arguments);}}
  gtag('js', new Date());
  gtag('config', 'G-7BV9Y2QVPZ');
</script>
"""

STYLE_BLOCK = """
  <style>
    /* Default Light Theme Variables */
    :root {
      --primary: #007bff;
      --bg-body: #fafafa;
      --bg-card: #ffffff;
      --text-main: #1e293b;
      --text-muted: #666666;
      --border-color: #eeeeee;
      --table-hover: #f5f9ff;
      --btn-bg: #f5f5f5;
      --btn-border: #dddddd;
    }

    /* Automatic Dark Theme Overrides */
    @media (prefers-color-scheme: dark) {
      :root {
        --bg-body: #121212;
        --bg-card: #1e1e1e;
        --text-main: #f1f5f9;
        --text-muted: #94a3b8;
        --border-color: #2e2e2e;
        --table-hover: #252526;
        --btn-bg: #2d2d2d;
        --btn-border: #444444;
      }
    }

    body { font-family: sans-serif; background: var(--bg-body); margin:0; padding:0; color: var(--text-main); transition: background 0.3s, color 0.3s; }
    .nav { background: #333; color: white; padding: 10px; display: flex; justify-content: center; gap: 20px; position: sticky; top: 0; z-index: 1000; }
    .nav a { color: #ccc; text-decoration: none; font-weight: bold; padding: 5px 15px; border-radius: 4px; transition: 0.2s; }
    .nav a:hover { color: white; background: #444; }
    .nav a.active { color: white; background: var(--primary); }
    .wrap { max-width: 1500px; margin: 24px auto; padding: 16px; }
    .card { background: var(--bg-card); border-radius: 16px; border: 1px solid var(--border-color); padding: 20px; margin-bottom: 24px; box-shadow: 0 4px 12px rgba(0,0,0,0.03); }
    .card.full-width { grid-column: 1 / -1; }
    h1 { font-size: 24px; margin: 0 0 16px; }
    h2 { font-size: 18px; margin-top: 0; color: var(--text-main); border-bottom: 2px solid var(--primary); display: inline-block; padding-bottom: 4px; margin-bottom: 15px; }
    .meta { color: var(--text-muted); font-size: 14px; margin-bottom: 16px; }
    .grid-2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(600px, 1fr)); gap: 20px; }
    .grid-3 { display: grid; grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); gap: 15px; }
    .chart-container { width: 100%; height: 350px; }
    .btns { margin-bottom: 12px; display: flex; gap: 8px; }
    button { padding: 6px 12px; border: 1px solid var(--btn-border); border-radius: 6px; background: var(--btn-bg); color: var(--text-main); cursor:pointer; font-size: 13px; }
    button.active { background: var(--primary); color:white; border-color: var(--primary); }
    .table-container { border-radius: 12px; overflow: hidden; border: 1px solid #007bff33; margin-top: 10px; }
    table { width: 100%; border-collapse: collapse; }
    th { background: #007bff; color: white; padding: 10px; text-align: left; cursor: pointer; font-size: 14px; user-select: none; transition: background 0.2s; }
    th:hover { background: #0056b3; }
    td { padding: 10px; border-bottom: 1px solid var(--border-color); font-size: 12px; color: var(--text-main); }
    tr:hover { background: var(--table-hover); }
    .footer { text-align: center; color: var(--text-muted); font-size: 12px; margin: 40px 0; }
    .leaderboard-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); gap: 16px; }
    .leaderboard-card { background: var(--bg-card); border-radius: 16px; border: 1px solid var(--border-color); padding: 16px; box-shadow: 0 4px 12px rgba(0,0,0,0.03); }
  </style>
"""

# --- 1. INDEX.HTML ---
INDEX_HTML = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" /><title>OGFStats - Dashboard</title>
  {GOOGLE_BLOCK}
  {STYLE_BLOCK}
  <script src="https://code.highcharts.com/highcharts.js"></script>
</head>
<body>
  {NAV_BAR}
  <div class="wrap">
    <h1>Mapping Activity</h1>
    <p class="meta" id="updateTime">Loading...</p>

    <div class="grid-2">
        <div class="card">
            <h2>Latest Changeset ID</h2>
            <div id="chartID" class="chart-container"></div>
        </div>
        <div class="card">
            <h2>Activity Volume</h2>
            <div class="btns">
                <button id="btnHourly" class="active" onclick="setMode('hourly')">Hourly</button>
                <button id="btnDaily" onclick="setMode('daily')">Daily</button>
            </div>
            <div id="chartDiff" class="chart-container"></div>
        </div>

        <div class="card full-width">
            <h2>Active Users (Activity Trends)</h2>
            <div id="mapperChart" class="chart-container" style="height: 400px;"></div>
        </div>

        <div class="card">
            <h2>Top Mappers This Month</h2>
            <div class="btns">
                <button id="btnBarObjs" class="active" onclick="setBarMetric('objects')">By Objects</button>
                <button id="btnBarEdits" onclick="setBarMetric('count')">By Edits</button>
            </div>
            <div id="userBarChart" class="chart-container" style="height: 435px;"></div>
        </div>
        <div class="card">
            <h2>User Activity Summary</h2>
            <div class="table-container">
                <table id="deltaTable">
                    <thead>
                        <tr>
                            <th onclick="sortRows('deltaTable', 0)">Name</th>
                            <th onclick="sortRows('deltaTable', 1)">Today (Objs)</th>
                            <th onclick="sortRows('deltaTable', 2)">Week (Objs)</th>
                            <th onclick="sortRows('deltaTable', 3)">Month (Objs)</th>
                        </tr>
                    </thead>
                    <tbody></tbody>
                </table>
            </div>
        </div>
    </div>
  </div>
  <div class="footer">OGFStats by minimapper :)</div>

  <script>
    document.getElementById('nav_charts').classList.add('active');
    let rawData = null;
    let mode = 'hourly';
    let barMetric = 'objects';
    let sortDirections = {{}};

    // Let Highcharts adjust text colors and elements naturally
    Highcharts.setOptions({{
        chart: {{ backgroundColor: 'transparent' }}
    }});

    function setMode(m) {{
        mode = m;
        document.getElementById('btnHourly').classList.toggle('active', m === 'hourly');
        document.getElementById('btnDaily').classList.toggle('active', m === 'daily');
        renderTrend();
    }}

    function setBarMetric(m) {{
        barMetric = m;
        document.getElementById('btnBarObjs').classList.toggle('active', m === 'objects');
        document.getElementById('btnBarEdits').classList.toggle('active', m === 'count');
        renderBar();
    }}

    function renderTrend() {{
        const entries = rawData[mode];
        const diffSeries = entries.map(d => [Date.parse(d.timestamp), d.change ?? 0]);
        Highcharts.chart('chartDiff', {{
            chart: {{ type: 'column', zoomType: 'x' }},
            title: {{ text: 'Changesets', align: 'left', style: {{ fontWeight: 'bold' }} }},
            xAxis: {{ type: 'datetime', crosshair: true }},
            yAxis: {{ title: {{ text: 'Count' }} }},
            tooltip: {{ shared: true, intersect: false }},
            plotOptions: {{ column: {{ stickyTracking: true, borderWidth: 0 }} }},
            series: [{{ name: 'Changesets', data: diffSeries, color: '#007bff' }}],
            credits: {{ enabled: false }}
        }});

        const idSeries = entries.map(d => [Date.parse(d.timestamp), Number(d.changeset_id)]);
        Highcharts.chart('chartID', {{
            chart: {{ type: 'line', zoomType: 'x' }},
            title: {{ text: 'ID History', align: 'left', style: {{ fontWeight: 'bold' }} }},
            xAxis: {{ type: 'datetime', crosshair: true }},
            yAxis: {{ title: {{ text: 'ID' }}, startOnTick: false, endOnTick: false }},
            tooltip: {{ shared: true, intersect: false }},
            plotOptions: {{ line: {{ stickyTracking: true }} }},
            series: [{{ name: 'Latest ID', data: idSeries, color: '#007bff' }}],
            credits: {{ enabled: false }}
        }});
    }}

    function renderBar() {{
        let sorted = [...rawData.monthly_leaderboard].sort((a,b) => b[barMetric] - a[barMetric]).slice(0, 20);
        Highcharts.chart('userBarChart', {{
            chart: {{ type: 'column' }},
            title: {{ text: 'User Ranking', align: 'left', style: {{ fontWeight: 'bold' }} }},
            xAxis: {{ categories: sorted.map(u => u.user), crosshair: true }},
            yAxis: {{ title: {{ text: barMetric === 'count' ? 'Edits' : 'Objects' }} }},
            tooltip: {{ shared: true, intersect: false }},
            plotOptions: {{ column: {{ stickyTracking: true, borderWidth: 0 }} }},
            series: [{{ name: barMetric === 'count' ? 'Edits' : 'Objects Changed', data: sorted.map(u => u[barMetric]), color: '#007bff' }}],
            credits: {{ enabled: false }}
        }});
    }}

    function sortRows(tableId, colIndex) {{
        const table = document.getElementById(tableId);
        const tbody = table.tBodies[0];
        const rows = Array.from(tbody.rows);
        const sortKey = tableId + colIndex;
        sortDirections[sortKey] = !sortDirections[sortKey];
        const ascending = sortDirections[sortKey];
        const sortedRows = rows.sort((a, b) => {{
            const valA = a.cells[colIndex].innerText;
            const valB = b.cells[colIndex].innerText;
            const numA = parseFloat(valA);
            const numB = parseFloat(valB);
            if (!isNaN(numA) && !isNaN(numB)) return ascending ? numA - numB : numB - numA;
            return ascending ? valA.localeCompare(valB) : valB.localeCompare(valA);
        }});
        tbody.append(...sortedRows);
    }}

    async function load() {{
        const resp = await fetch('data.json', {{ cache: 'no-store' }});
        rawData = await resp.json();
        document.getElementById('updateTime').innerText = "Last Sync: " + rawData.last_month_update;

        const mapperDaily = (rawData.daily_mapper_counts || []).map(d => [Date.parse(d.date), d.count]);
        const mapperWeekly = (rawData.weekly_mapper_counts || []).map(d => [Date.parse(d.date), d.count]);
        const mapperMonthly = (rawData.monthly_mapper_counts || []).map(d => [Date.parse(d.date), d.count]);

        Highcharts.chart('mapperChart', {{
            chart: {{ type: 'line', zoomType: 'x' }},
            title: {{ text: 'Unique Mappers (Rolling)', align: 'left', style: {{ fontWeight: 'bold' }} }},
            xAxis: {{ type: 'datetime', crosshair: true }},
            yAxis: {{ title: {{ text: 'Unique Users' }} }},
            tooltip: {{ shared: true, crosshair: true }},
            series: [
                {{ name: 'Daily Unique', data: mapperDaily, color: '#007bff' }},
                {{ name: 'Weekly Unique', data: mapperWeekly, color: '#28a745', visible: false }},
                {{ name: 'Monthly Unique', data: mapperMonthly, color: '#dc3545', visible: false }}
            ],
            credits: {{ enabled: false }}
        }});

        const tbody = document.querySelector("#deltaTable tbody");
        const sorted = [...rawData.monthly_leaderboard].sort((a,b) => b.objects - a.objects).slice(0, 15);
        tbody.innerHTML = sorted.map(u =>
            `<tr><td>${{u.user}}</td><td>${{u.d_today || 0}}</td><td>${{u.d_week || 0}}</td><td>${{u.objects}}</td></tr>`
        ).join('');

        renderTrend();
        renderBar();
    }}
    load();
  </script>
</body></html>"""

# --- 2. LEADERBOARDS.HTML ---
LEADERBOARD_HTML = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" /><title>OGFStats - Leaderboards</title>
  {GOOGLE_BLOCK}
  {STYLE_BLOCK}
  <script src="https://code.highcharts.com/highcharts.js"></script>
</head>
<body>
  {NAV_BAR}
  <div class="wrap">
    <h1>User Leaderboards</h1>

    <div class="card full-width">
        <h2>Objects Changed (Monthly Overview)</h2>
        <div id="fullUserChart" class="chart-container" style="height: 400px;"></div>
    </div>

    <div class="leaderboard-grid">
      <div class="leaderboard-card"><h2>Hourly</h2><div class="table-container"><table id="hourlyTable"><thead><tr><th onclick="sortRows('hourlyTable', 0)">User</th><th onclick="sortRows('hourlyTable', 1)">UID</th><th onclick="sortRows('hourlyTable', 2)">Edits</th><th onclick="sortRows('hourlyTable', 3)">Objs</th></tr></thead><tbody></tbody></table></div></div>
      <div class="leaderboard-card"><h2>Daily (Rolling 24h)</h2><div class="table-container"><table id="dailyTable"><thead><tr><th onclick="sortRows('dailyTable', 0)">User</th><th onclick="sortRows('dailyTable', 1)">UID</th><th onclick="sortRows('dailyTable', 2)">Edits</th><th onclick="sortRows('dailyTable', 3)">Objs</th></tr></thead><tbody></tbody></table></div></div>
      <div class="leaderboard-card"><h2>Monthly</h2><div class="table-container"><table id="monthlyTable"><thead><tr><th onclick="sortRows('monthlyTable', 0)">User</th><th onclick="sortRows('monthlyTable', 1)">UID</th><th onclick="sortRows('monthlyTable', 2)">Edits</th><th onclick="sortRows('monthlyTable', 3)">Objs</th></tr></thead><tbody></tbody></table></div></div>
    </div>
  </div>

  <script>
    document.getElementById('nav_leaderboards').classList.add('active');
    let sortDirections = {{}};

    Highcharts.setOptions({{
        chart: {{ backgroundColor: 'transparent' }}
    }});

    function renderFullChart(users) {{
        const sorted = [...users].sort((a,b) => b.objects - a.objects);
        Highcharts.chart('fullUserChart', {{
            chart: {{ type: 'column' }},
            title: {{ text: 'Full Distribution (Linear)', align: 'left', style: {{ fontWeight: 'bold' }} }},
            xAxis: {{ categories: sorted.map(u => u.user), labels: {{ enabled: false }}, crosshair: true }},
            yAxis: {{ title: {{ text: 'Objects Changed' }} }},
            tooltip: {{ shared: true, intersect: false }},
            plotOptions: {{ column: {{ stickyTracking: true, borderWidth: 0 }} }},
            series: [{{ name: 'Objects', data: sorted.map(u => u.objects), color: '#007bff' }}],
            credits: {{ enabled: false }}
        }});
    }}

    function fillTable(id, list) {{
        if (!list) return;
        document.querySelector(`#${{id}} tbody`).innerHTML = list.map(u => `<tr><td>${{u.user}}</td><td>${{u.uid}}</td><td>${{u.count}}</td><td>${{u.objects}}</td></tr>`).join('');
    }}

    function sortRows(tableId, colIndex) {{
        const table = document.getElementById(tableId);
        const tbody = table.tBodies[0];
        const rows = Array.from(tbody.rows);
        const sortKey = tableId + colIndex;
        sortDirections[sortKey] = !sortDirections[sortKey];
        const ascending = sortDirections[sortKey];
        const sortedRows = rows.sort((a, b) => {{
            const valA = a.cells[colIndex].innerText;
            const valB = b.cells[colIndex].innerText;
            const numA = parseFloat(valA);
            const numB = parseFloat(valB);
            if (!isNaN(numA) && !isNaN(numB)) return ascending ? numA - numB : numB - numA;
            return ascending ? valA.localeCompare(valB) : valB.localeCompare(valA);
        }});
        tbody.append(...sortedRows);
    }}

    async function load() {{
        const resp = await fetch('data.json', {{ cache: 'no-store' }});
        const data = await resp.json();
        renderFullChart(data.monthly_leaderboard || []);
        fillTable('hourlyTable', data.hourly_leaderboards?.slice(-1)[0]?.leaderboard || []);
        fillTable('dailyTable', data.daily_leaderboard || []);
        fillTable('monthlyTable', data.monthly_leaderboard || []);
    }}
    load();
  </script>
</body></html>"""

# --- 3. VERSION.HTML ---
VERSION_HTML = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8" /><title>Version History</title>{GOOGLE_BLOCK}{STYLE_BLOCK}</head>
<body>
  {NAV_BAR}
  <div class="wrap">
    <div class="card">
        <h1>Version History</h1>
        <div id="versionList"></div>
    </div>
  </div>
  <script>
    document.getElementById('nav_version').classList.add('active');
    const historyData = {json.dumps(VERSION_HISTORY)};
    document.getElementById('versionList').innerHTML = historyData.map(v => `
        <div style="border-bottom: 1px solid var(--border-color); padding: 12px 0;">
            <span style="background: var(--btn-bg); color: var(--text-main); padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 12px;">v\${{v.v}}</span>
            <strong>\Technical terms match standard styling: \${{v.date}}</strong>
            <p style="margin: 8px 0 0; font-size: 14px; color: var(--text-muted);">\${{v.note}}</p>
        </div>
    `).join('');
  </script>
</body></html>"""

# --- PYTHON LOGIC ---

def get_initial_data():
    return {
        "hourly": [], "daily": [], "hourly_leaderboards": [],
        "rolling24": [], "monthly_store": [], "monthly_leaderboard": [],
        "last_month_update": "", "seen_ids": [],
        "daily_mapper_counts": [], "weekly_mapper_counts": [], "monthly_mapper_counts": []
    }

def fetch_recent_changesets(lookback_hours=2):
    start_time = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    url = f"{OGF_CHANGESETS_URL}?time={start_time.strftime('%Y-%m-%dT%H:00:00Z')}"
    req = Request(url, headers={"User-Agent": f"ogf-stats-script/{VERSION}"})
    try:
        with urlopen(req, timeout=20) as resp:
            root = ET.fromstring(resp.read())
        return [{
            "id": cs.get("id"),
            "user": cs.get("user"),
            "uid": cs.get("uid"),
            "changes_count": int(cs.get("changes_count", "0")),
            "ts": cs.get("created_at")
        } for cs in root.findall("changeset")]
    except Exception as e:
        print(f"Fetch error: {e}"); return []

def tally_users(entries):
    counts = {}
    for e in entries:
        key = (e["user"], e["uid"])
        if key not in counts: counts[key] = {"count": 0, "objects": 0}
        counts[key]["count"] += 1; counts[key]["objects"] += e.get("changes_count", 0)
    return [{"user": u, "uid": uid, "count": c["count"], "objects": c["objects"]} for (u, uid), c in sorted(counts.items(), key=lambda kv: (kv[1]["count"], kv[1]["objects"]), reverse=True)]

def run_update(data_file, now):
    data = get_initial_data()
    if data_file.exists():
        try: data = json.loads(data_file.read_text(encoding="utf-8"))
        except: pass

    raw_entries = fetch_recent_changesets()
    seen = set(data.get("seen_ids", []))
    new_entries = [e for e in raw_entries if e["id"] not in seen]
    for e in new_entries: seen.add(e["id"])
    data["seen_ids"] = list(seen)[-3000:]

    bucket_ts = now.replace(minute=0, second=0, microsecond=0)
    ts_str = bucket_ts.strftime("%Y-%m-%dT%H:%M:%SZ")
    data["last_month_update"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    cid = int(raw_entries[0]["id"]) if raw_entries else (data["hourly"][-1]["changeset_id"] if data["hourly"] else 0)

    existing_hourly = next((item for item in data["hourly"] if item["timestamp"] == ts_str), None)
    if existing_hourly:
        existing_hourly["change"] += len(new_entries)
        existing_hourly["changeset_id"] = cid
    else:
        data["hourly"].append({"timestamp": ts_str, "changeset_id": cid, "change": len(new_entries)})
        data["hourly"] = data["hourly"][-720:]

    data.setdefault("monthly_store", []).extend(new_entries)
    this_month = now.strftime("%Y-%m")
    data["monthly_store"] = [e for e in data["monthly_store"] if "ts" in e and e["ts"].startswith(this_month)]

    day_ago = (now - timedelta(days=1)).isoformat()
    week_ago = (now - timedelta(days=7)).isoformat()

    today_list = tally_users([e for e in data["monthly_store"] if e["ts"] >= day_ago])
    week_list = tally_users([e for e in data["monthly_store"] if e["ts"] >= week_ago])
    full_month = tally_users(data["monthly_store"])

    data.setdefault("daily_mapper_counts", []).append({"date": ts_str, "count": len(today_list)})
    data.setdefault("weekly_mapper_counts", []).append({"date": ts_str, "count": len(week_list)})
    data.setdefault("monthly_mapper_counts", []).append({"date": ts_str, "count": len(full_month)})

    data["daily_mapper_counts"] = data["daily_mapper_counts"][-720:]
    data["weekly_mapper_counts"] = data["weekly_mapper_counts"][-720:]
    data["monthly_mapper_counts"] = data["monthly_mapper_counts"][-720:]

    for u in full_month:
        u["d_today"] = next((x["objects"] for x in today_list if x["uid"] == u["uid"]), 0)
        u["d_week"] = next((x["objects"] for x in week_list if x["uid"] == u["uid"]), 0)

    data["monthly_leaderboard"] = full_month
    data["daily_leaderboard"] = today_list

    data.setdefault("hourly_leaderboards", []).append({"timestamp": ts_str, "leaderboard": tally_users(new_entries)})
    data["hourly_leaderboards"] = data["hourly_leaderboards"][-48:]

    data_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

def main():
    # 1. Initialization and Page Writing
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    pages = {"index.html": INDEX_HTML, "leaderboards.html": LEADERBOARD_HTML, "version.html": VERSION_HTML}
    for f, c in pages.items(): 
        (TARGET_DIR / f).write_text(c, encoding='utf-8')

    data_file = TARGET_DIR / "data.json"
    
    # Track the last day ts.py was run to prevent multiple runs if script restarts
    last_ts_run_day = None

    # Load existing data immediately to populate last_ts_run_day if possible
    if data_file.exists():
        try:
            temp_data = json.loads(data_file.read_text(encoding="utf-8"))
            if "last_month_update" in temp_data:
                last_ts_run_day = temp_data["last_month_update"].split('T')[0]
        except:
            pass

    print(f"Starting OGFStats v{VERSION}...")

    while True:
        try:
            now = datetime.now(timezone.utc)
            
            # 2. Main Changeset Update
            run_update(data_file, now)
            
            # 3. Daily Task: Run Territory Stats (ts.py) at 12 AM
            current_day = now.strftime("%Y-%m-%d")
            if now.hour == 0 and last_ts_run_day != current_day:
                print(f"Midnight detected ({current_day} 00:00). Running ts.py...")
                try:
                    # Runs ts.py and waits for it to finish
                    subprocess.run([sys.executable, "ts.py"], check=True)
                    last_ts_run_day = current_day
                    print("✓ ts.py completed successfully.")
                except Exception as e:
                    print(f"❌ Error running ts.py: {e}")

        except Exception as e:
            print(f"Critical Loop error: {e}")

        # 4. Precision Sleep (Prevents Timing Drift so it hits midnight perfectly)
        now = datetime.now(timezone.utc)
        seconds_until_next_hour = 3600 - (now.minute * 60 + now.second) + 5
        
        print(f"Sync complete at {now.strftime('%H:%M:%S')}. Next run in {seconds_until_next_hour}s...")
        time.sleep(max(0, seconds_until_next_hour))

if __name__ == "__main__":
    main()
