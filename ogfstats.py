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
VERSION = "4.0"
TARGET_DIR = Path("/var/www/ogfstats")

VERSION_HISTORY = [
    {"v": "4.0", "date": "2026-01-26", "note": "New Territory Stats tab. TStats updates daily with node, way, and relation counts for each claimed territory. Seperated all tabss into unique pages to make farther expansion easier."},
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

# --- GOOGLE FUNCTIONALITY ---
GOOGLE_BLOCK = """
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7BV9Y2QVPZ"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());
  gtag('config', 'G-7BV9Y2QVPZ');
</script>
"""


STYLE_BLOCK = """
  <style>
    body { font-family: sans-serif; background: #fafafa; margin:0; padding:0; }
    .nav { background: #333; color: white; padding: 10px; display: flex; justify-content: center; gap: 20px; position: sticky; top: 0; z-index: 1000; }
    .nav a { color: #ccc; text-decoration: none; font-weight: bold; padding: 5px 15px; border-radius: 4px; transition: 0.2s; }
    .nav a:hover { color: white; background: #444; }
    .nav a.active { color: white; background: #007bff; }
    .wrap { max-width: 1300px; margin: 24px auto; padding: 16px; background: #fff; border-radius: 16px; box-shadow: 0 10px 30px rgba(0,0,0,0.06); }
    h1 { font-size: 22px; margin: 0 0 8px; }
    .meta { color: #666; font-size: 14px; margin-bottom: 16px; }
    .charts { display: flex; gap: 16px; margin-bottom: 24px; flex-wrap: wrap; }
    #chart, #chartDiff { flex: 1; min-width: 400px; height: 500px; }
    .btns { margin-bottom: 12px; }
    button { padding: 6px 12px; border:1px solid #ddd; border-radius: 6px; background:#f5f5f5; cursor:pointer; }
    button.active { background:#007bff; color:white; }
    .leaderboard-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); gap: 16px; }
    .leaderboard-card { background: #fff; border-radius: 16px; border: 1px solid #eee; padding: 16px; box-shadow: 0 4px 12px rgba(0,0,0,0.03); }
    .leaderboard-card h2 { font-size: 18px; margin-top: 0; color: #333; border-bottom: 2px solid #007bff; display: inline-block; padding-bottom: 4px; }
    .table-container { border-radius: 12px; overflow: hidden; border: 1px solid #007bff33; margin-top: 10px; }
    table { width: 100%; border-collapse: collapse; }
    th { background: #007bff; color: white; padding: 10px; text-align: left; cursor: pointer; font-size: 14px; user-select: none; }
    td { padding: 10px; border-bottom: 1px solid #eee; font-size: 13px; }
    tr:hover { background: #f5f9ff; }
    .version-item { border-bottom: 1px solid #eee; padding: 12px 0; }
    .version-tag { background: #eee; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 12px; }
    .footer { text-align: center; color: #999; font-size: 12px; margin: 40px 0; }
  </style>
"""

# --- 1. INDEX.HTML (CHARTS) ---
INDEX_HTML = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" /><title>OGFStats - Charts</title>
  {GOOGLE_BLOCK}
  {STYLE_BLOCK}
  <script src="https://code.highcharts.com/highcharts.js"></script>
</head>
<body>
  {NAV_BAR}
  <div class="wrap">
    <h1>Changeset Activity</h1>
    <p class="meta" id="updateTime">Loading data...</p>
    <div class="btns">
      <button id="btnHourly" class="active" onclick="setMode('hourly')">Hourly</button>
      <button id="btnDaily" onclick="setMode('daily')">Daily</button>
    </div>
    <div class="charts"><div id="chart"></div><div id="chartDiff"></div></div>
  </div>
  <div class="footer">OGFStats by minimapper :)</div>
  <script>
    document.getElementById('nav_charts').classList.add('active');
    let mode = 'hourly'; let rawData = null;
    function setMode(m) {{
        mode = m;
        document.getElementById('btnHourly').classList.toggle('active', m === 'hourly');
        document.getElementById('btnDaily').classList.toggle('active', m === 'daily');
        updateCharts(rawData[mode]);
    }}
    function updateCharts(entries) {{
        const series = entries.map(d => [Date.parse(d.timestamp), Number(d.changeset_id)]);
        const diffSeries = entries.map(d => [Date.parse(d.timestamp), d.change ?? 0]);
        Highcharts.chart('chart', {{ chart: {{ zoomType: 'x' }}, title: {{ text: 'Changeset ID Trend' }}, xAxis: {{ type: 'datetime' }}, series: [{{ name: 'ID', data: series, color: '#007bff' }}], credits: {{ enabled: false }} }});
        Highcharts.chart('chartDiff', {{ chart: {{ type: 'column', zoomType: 'x' }}, title: {{ text: 'Activity Volume' }}, xAxis: {{ type: 'datetime' }}, series: [{{ name: 'Count', data: diffSeries, color: '#007bff' }}], credits: {{ enabled: false }} }});
    }}
    async function load() {{
        const resp = await fetch('data.json', {{ cache: 'no-store' }});
        rawData = await resp.json();
        document.getElementById('updateTime').innerText = "Last Sync: " + rawData.last_month_update;
        updateCharts(rawData[mode]);
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
</head>
<body>
  {NAV_BAR}
  <div class="wrap">
    <h1>Leaderboards</h1>
    <div class="leaderboard-grid">
      <div class="leaderboard-card"><h2>Hourly</h2><div class="table-container"><table id="hourlyTable"><thead><tr><th>User</th><th>UID</th><th>Edits</th><th>Objs</th></tr></thead><tbody></tbody></table></div></div>
      <div class="leaderboard-card"><h2>Daily</h2><div class="table-container"><table id="dailyTable"><thead><tr><th>User</th><th>UID</th><th>Edits</th><th>Objs</th></tr></thead><tbody></tbody></table></div></div>
      <div class="leaderboard-card"><h2>Monthly</h2><div class="table-container"><table id="monthlyTable"><thead><tr><th>User</th><th>UID</th><th>Edits</th><th>Objs</th></tr></thead><tbody></tbody></table></div></div>
    </div>
  </div>
  <script>
    document.getElementById('nav_leaderboards').classList.add('active');
    function fillTable(id, list) {{
        document.querySelector(`#${{id}} tbody`).innerHTML = list.map(u => `<tr><td>${{u.user}}</td><td>${{u.uid}}</td><td>${{u.count}}</td><td>${{u.objects}}</td></tr>`).join('');
    }}
    async function load() {{
        const resp = await fetch('data.json', {{ cache: 'no-store' }});
        const data = await resp.json();
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
    <h1>Version History</h1>
    <div id="versionList"></div>
  </div>
  <script>
    document.getElementById('nav_version').classList.add('active');
    const historyData = {json.dumps(VERSION_HISTORY)};
    document.getElementById('versionList').innerHTML = historyData.map(v => `
        <div class="version-item">
            <span class="version-tag">v${{v.v}}</span> <strong>${{v.date}}</strong>
            <p style="margin: 8px 0 0; font-size: 14px; color: #444;">${{v.note}}</p>
        </div>
    `).join('');
  </script>
</body></html>"""

def get_initial_data():
    return {"hourly": [], "daily": [], "hourly_leaderboards": [], "rolling24": [], "monthly_store": [], "monthly_leaderboard": [], "last_month_update": "", "seen_ids": []}

def fetch_recent_changesets(lookback_hours=2):
    start_time = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    url = f"{OGF_CHANGESETS_URL}?time={start_time.strftime('%Y-%m-%dT%H:00:00Z')}"
    req = Request(url, headers={"User-Agent": f"ogf-stats-script/{VERSION}"})
    try:
        with urlopen(req, timeout=20) as resp:
            root = ET.fromstring(resp.read())
        return [{"id": cs.get("id"), "user": cs.get("user"), "uid": cs.get("uid"), "changes_count": int(cs.get("changes_count", "0"))} for cs in root.findall("changeset")]
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
    # Load existing data or start fresh
    data = get_initial_data()
    if data_file.exists():
        try:
            data = json.loads(data_file.read_text(encoding="utf-8"))
        except:
            pass

    # 1. ARCHIVING (End of month logic)
    current_month = now.strftime("%Y-%m")
    last_update = data.get("last_month_update", "")
    if last_update and current_month != last_update[:7]:
        archive_dir = data_file.parent / "monthly_archives"
        archive_dir.mkdir(parents=True, exist_ok=True)
        (archive_dir / f"{last_update[:7]}.json").write_text(json.dumps(data, indent=2))
        # Reset monthly counters
        data["monthly_store"], data["monthly_leaderboard"] = [], []

    # 2. FETCHING NEW DATA
    raw_entries = fetch_recent_changesets()
    seen = set(data.get("seen_ids", []))
    new_entries = [e for e in raw_entries if e["id"] not in seen]
    for e in new_entries:
        seen.add(e["id"])
    data["seen_ids"] = list(seen)[-2000:]

    # 3. BUCKETING LOGIC
    bucket_ts = now.replace(minute=0, second=0, microsecond=0)
    ts_str = bucket_ts.strftime("%Y-%m-%dT%H:%M:%SZ")
    data["last_month_update"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Determine latest Changeset ID
    if raw_entries:
        cid = int(raw_entries[0]["id"])
    elif data["hourly"]:
        cid = data["hourly"][-1]["changeset_id"]
    else:
        cid = 0

    # Hourly Updates
    existing_hourly = next((item for item in data["hourly"] if item["timestamp"] == ts_str), None)
    if existing_hourly:
        existing_hourly["change"] += len(new_entries)
        existing_hourly["changeset_id"] = cid
    else:
        data["hourly"].append({"timestamp": ts_str, "changeset_id": cid, "change": len(new_entries)})
        data["hourly"] = data["hourly"][-720:] # Keep 30 days of hourly data

    # 4. DAILY TASK (ts.py)
    last_dc = data.get("last_dc_run", "")
    today_str = now.strftime("%Y-%m-%d")
    if last_dc != today_str:
        print(f"[{now.strftime('%H:%M:%S')}] Launching daily territory scan (ts.py)...")
        try:
            # Runs your territory script as a separate process
            subprocess.run([sys.executable, "ts.py"], check=True)
            data["last_dc_run"] = today_str
        except Exception as e:
            print(f"Error running ts.py: {e}")

    # 5. LEADERBOARDS
    # Hourly Leaderboard (Last hour only)
    data.setdefault("hourly_leaderboards", []).append({"timestamp": ts_str, "leaderboard": tally_users(new_entries)})
    data["hourly_leaderboards"] = data["hourly_leaderboards"][-48:]

    # Daily Leaderboard (Rolling 24h)
    data.setdefault("rolling24", []).append({"timestamp": ts_str, "entries": new_entries})
    cutoff = now - timedelta(hours=24)
    data["rolling24"] = [r for r in data["rolling24"] if datetime.fromisoformat(r["timestamp"].replace("Z", "+00:00")).replace(tzinfo=timezone.utc) >= cutoff]
    data["daily_leaderboard"] = tally_users([e for r in data["rolling24"] for e in r["entries"]])

    # Monthly Leaderboard
    data.setdefault("monthly_store", []).extend(new_entries)
    data["monthly_leaderboard"] = tally_users(data["monthly_store"])

    # 6. SAVE
    data_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"[{now.strftime('%H:%M:%S')}] Success: {cid} (+{len(new_entries)} new) bucketed to {ts_str}")

def main():
    # Ensure the web directory exists
    TARGET_DIR.mkdir(parents=True, exist_ok=True)

    # Define the files to be created
    pages = {
        "index.html": INDEX_HTML,
        "leaderboards.html": LEADERBOARD_HTML,
        "version.html": VERSION_HTML
    }

    # Write the HTML files
    for filename, content in pages.items():
        (TARGET_DIR / filename).write_text(content, encoding='utf-8')
        print(f"Initialized {filename}")

    data_file = TARGET_DIR / "data.json"

    # Run the first update immediately
    run_update(data_file, datetime.now(timezone.utc))

    # The Infinite Loop (runs once per hour)
    while True:
        now = datetime.now(timezone.utc)
        # Calculate time until the next top-of-the-hour + 5 seconds
        next_run = (now + timedelta(hours=1)).replace(minute=0, second=5, microsecond=0)
        sleep_time = (next_run - now).total_seconds()

        print(f"Waiting {int(sleep_time)}s until next hourly sync...")
        time.sleep(sleep_time)

        run_update(data_file, datetime.now(timezone.utc))

if __name__ == "__main__":
    main()
