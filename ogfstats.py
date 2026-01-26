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

OGF_CHANGESETS_URL = "https://opengeofiction.net/api/0.6/changesets"

INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>OGFStats</title>
  <script src="https://code.highcharts.com/highcharts.js"></script>
  <script src="https://code.highcharts.com/modules/exporting.js"></script>
  <script src="https://code.highcharts.com/modules/full-screen.js"></script>
  <style>
    body { font-family: sans-serif; background: #fafafa; margin:0; padding:0; }
    .nav { background: #333; color: white; padding: 10px; display: flex; justify-content: center; gap: 20px; position: sticky; top: 0; z-index: 1000; }
    .nav a { color: #ccc; text-decoration: none; font-weight: bold; cursor: pointer; padding: 5px 15px; border-radius: 4px; }
    .nav a:hover { color: white; background: #444; }
    .nav a.active { color: white; background: #007bff; }

    .wrap { max-width: 1300px; margin: 24px auto; padding: 16px; background: #fff; border-radius: 16px; box-shadow: 0 10px 30px rgba(0,0,0,0.06); }
    .page { display: none; }
    .page.active { display: block; }

    h1 { font-size: 22px; margin: 0 0 8px; }
    p.meta { margin: 0 0 16px; color: #666; font-size: 14px; }
    .charts { display: flex; gap: 16px; margin-bottom: 24px; }
    #chart, #chartDiff { flex: 1; height: 520px; }
    .btns { margin-bottom: 12px; }
    button { padding: 6px 12px; margin-right: 8px; border:1px solid #ddd; border-radius: 6px; background:#f5f5f5; cursor:pointer; }
    button.active { background:#007bff; color:white; }

    /* leaderboard styling */
    .leaderboard-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); gap: 16px; }
    .leaderboard-card { background: #fff; border-radius: 16px; box-shadow: 0 4px 16px rgba(0,0,0,0.05); padding: 16px; }
    .leaderboard-card h2 { font-size: 18px; margin: 0 0 12px; border-bottom: 2px solid #007bff; padding-bottom: 5px; }
    table { width: 100%; border-collapse: separate; border-spacing: 0; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.05); }
    thead tr { background: #007bff; color: #fff; font-weight: bold; }
    thead tr th { padding: 10px; text-align: left; font-size: 14px; }
    tbody tr td { padding: 10px; font-size: 14px; border-top: 1px solid #007bff33; }
    tbody tr:hover { background: #f5f9ff; }
  </style>
</head>
<body>
  <div class="nav">
    <a id="navCharts" class="active" onclick="showPage('chartsPage')">Charts</a>
    <a id="navLeaderboards" onclick="showPage('leaderboardPage')">Leaderboards</a>
  </div>

  <div class="wrap">
    <div id="chartsPage" class="page active">
        <h1>Changeset ID Over Time</h1>
        <p class="meta">The latest changeset id every hour (or day) over time :)</p>
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
        <h1>leaderboards</h1>
        <p class="meta">Leaderboards by hour, day, and month. Monthly leaderbaords reset at the start of each month but old months are saved.</p>
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
            <h2>Monthly (Reset Monthly)</h2>
            <table id="monthlyTable">
              <thead><tr><th>User</th><th>UID</th><th>Edits</th><th>Objects</th></tr></thead>
              <tbody></tbody>
            </table>
          </div>
        </div>
    </div>
  </div>

<script>
let mode = 'hourly';
let rawData = null;

function showPage(pageId) {
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.nav a').forEach(a => a.classList.remove('active'));
    document.getElementById(pageId).classList.add('active');
    
    if(pageId === 'chartsPage') {
        document.getElementById('navCharts').classList.add('active');
        if(rawData) updateCharts(rawData[mode]);
    } else {
        document.getElementById('navLeaderboards').classList.add('active');
    }
}

async function load() {
  const resp = await fetch('data.json', { cache: 'no-store' });
  rawData = await resp.json();
  updateCharts(rawData[mode]);
  updateLeaderboards(rawData);
}

function updateCharts(entries) {
  const sorted = entries.sort((a,b)=>Date.parse(a.timestamp)-Date.parse(b.timestamp));
  const series = sorted.map(d => [Date.parse(d.timestamp), Number(d.changeset_id)]);
  const diffSeries = sorted.map(d => [Date.parse(d.timestamp), d.change ?? 0]);

  Highcharts.chart('chart', {
    chart: { zoomType: 'x' },
    title: { text: mode === 'hourly' ? 'Hourly Changeset IDs' : 'Daily Changeset IDs' },
    xAxis: { type: 'datetime' },
    yAxis: { title: { text: 'ID' } },
    legend: { enabled: false },
    series: [{ type: 'line', data: series }],
    credits: { enabled: false }
  });

  Highcharts.chart('chartDiff', {
    chart: { type: 'column', zoomType: 'x' },
    title: { text: mode === 'hourly' ? 'Hourly Change' : 'Daily Change' },
    xAxis: { type: 'datetime' },
    yAxis: { title: { text: 'Change' } },
    legend: { enabled: false },
    series: [{ data: diffSeries }],
    credits: { enabled: false }
  });
}

function updateLeaderboards(data) {
  const hourly = data.hourly_leaderboards?.slice(-1)[0]?.leaderboard || [];
  const daily = data.daily_leaderboard || [];
  const monthly = data.monthly_leaderboard || [];

  fillTable('hourlyTable', hourly);
  fillTable('dailyTable', daily);
  fillTable('monthlyTable', monthly);
}

function fillTable(tableId, list) {
    const body = document.querySelector(`#${tableId} tbody`);
    body.innerHTML = '';
    list.forEach(u => {
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${u.user}</td><td>${u.uid}</td><td>${u.count}</td><td>${u.objects}</td>`;
        body.appendChild(tr);
    });
}

document.getElementById('btnHourly').addEventListener('click', ()=>{ mode = 'hourly'; load(); });
document.getElementById('btnDaily').addEventListener('click', ()=>{ mode = 'daily'; load(); });

load();
</script>
</body>
</html>
"""

def fetch_first_changeset_id(url: str) -> int:
    req = Request(url, headers={"User-Agent": "ogf-stats-script/1.0"})
    with urlopen(req, timeout=20) as resp:
        xml_bytes = resp.read()
    root = ET.fromstring(xml_bytes)
    first = root.find('changeset')
    return int(first.get('id')) if first is not None else 0

def fetch_changesets_for_hour(start: datetime):
    url = f"{OGF_CHANGESETS_URL}?time={start.strftime('%Y-%m-%dT%H:00:00Z')}"
    req = Request(url, headers={"User-Agent": "ogf-stats-script/1.0"})
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

def update_leaderboards(out_json: Path, hour_start: datetime, entries):
    data = {"hourly": [], "daily": [], "hourly_leaderboards": [], "rolling24": [], "monthly_store": [], "monthly_leaderboard": []}
    if out_json.exists():
        try: data = json.loads(out_json.read_text(encoding="utf-8") or "{}")
        except: pass

    # Archive check: If the month has changed since the last update
    current_month_str = hour_start.strftime("%Y-%m")
    last_update_ts = data.get("last_month_update")
    
    if last_update_ts:
        last_month = last_update_ts[:7] # YYYY-MM
        if current_month_str != last_month:
            # SAVE ARCHIVE
            archive_dir = out_json.parent / "monthly_archives"
            archive_dir.mkdir(exist_ok=True)
            archive_path = archive_dir / f"{last_month}.json"
            archive_path.write_text(json.dumps({
                "month": last_month,
                "leaderboard": data.get("monthly_leaderboard", [])
            }, indent=2))
            # RESET
            data["monthly_store"] = []
            data["monthly_leaderboard"] = []

    data["last_month_update"] = hour_start.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Hourly update
    data.setdefault("hourly_leaderboards", []).append({
        "timestamp": hour_start.strftime("%Y-%m-%dT%H:00:00Z"),
        "leaderboard": tally_users(entries)
    })
    
    # Rolling 24h
    data.setdefault("rolling24", []).append({"timestamp": hour_start.isoformat(), "entries": entries})
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    data["rolling24"] = [r for r in data["rolling24"] if datetime.fromisoformat(r["timestamp"]) >= cutoff]
    
    # Monthly Cumulative Store
    data.setdefault("monthly_store", []).extend(entries)
    
    # Calculate Leaderboards
    all_24 = [e for r in data["rolling24"] for e in r["entries"]]
    data["daily_leaderboard"] = tally_users(all_24)
    data["monthly_leaderboard"] = tally_users(data["monthly_store"])
    
    # Trim hourly logs to keep file size reasonable (last 48 hours)
    data["hourly_leaderboards"] = data["hourly_leaderboards"][-48:]
    
    out_json.write_text(json.dumps(data, indent=2), encoding="utf-8")

def append_to_json(out_json: Path, changeset_id: int, ts: str, mode: str) -> None:
    data = {"hourly": [], "daily": []}
    if out_json.exists():
        try: data = json.loads(out_json.read_text(encoding='utf-8') or "{}")
        except: pass
    data.setdefault(mode, [])
    change = 0 if not data[mode] else changeset_id - data[mode][-1]["changeset_id"]
    data[mode].append({"timestamp": ts, "changeset_id": changeset_id, "change": change})
    # Keep only last 1000 records to prevent massive files
    data[mode] = data[mode][-1000:]
    out_json.write_text(json.dumps(data, indent=2), encoding='utf-8')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()

    outdir = Path(__file__).parent.resolve()
    (outdir / "data.json").touch(exist_ok=True)
    (outdir / "index.html").write_text(INDEX_HTML, encoding='utf-8')

    port = 8001
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("0.0.0.0", args.port))
        port = args.port
        s.close()
    except: port = 0

    import threading
    handler = lambda *a, **kw: SimpleHTTPRequestHandler(*a, directory=str(outdir), **kw)
    server = ThreadingHTTPServer(("0.0.0.0", port), handler)
    print(f"Server started at http://localhost:{server.server_port}")
    threading.Thread(target=server.serve_forever, daemon=True).start()

    while True:
        now = datetime.now(timezone.utc)
        hour_start = now.replace(minute=0, second=0, microsecond=0)
        
        # 1. Update Charts
        cid = fetch_first_changeset_id(OGF_CHANGESETS_URL)
        append_to_json(outdir / "data.json", cid, now.strftime("%Y-%m-%dT%H:%M:%SZ"), "hourly")
        
        # 2. Update Leaderboards (Hourly, Rolling 24h, Monthly)
        try:
            entries = fetch_changesets_for_hour(hour_start)
            update_leaderboards(outdir / "data.json", hour_start, entries)
            print(f"[{now}] Data updated successfully.")
        except Exception as e:
            print(f"Update error: {e}")

        if now.hour == 0: # Daily log at midnight
            append_to_json(outdir / "data.json", cid, now.strftime("%Y-%m-%dT%H:%M:%SZ"), "daily")

        # Sleep until next hour
        next_run = (now + timedelta(hours=1)).replace(minute=0, second=5)
        time.sleep((next_run - now).total_seconds())

if __name__ == "__main__":
    main()
