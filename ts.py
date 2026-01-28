import os
import csv
import json
import time
import requests
from datetime import datetime

# ================= CONFIG =================

TERRITORY_URL = "https://wiki.opengeofiction.net/index.php/OpenGeofiction:Territory_administration?action=raw"
OVERPASS_URL = "https://overpass.opengeofiction.net/api/interpreter"


DATA_DIR = "/var/www/ogfstats/tdata"
ADMIN_DIR = os.path.join(DATA_DIR, "territory-admin")
STATS_DIR = os.path.join(DATA_DIR, "territory")
LATEST_FILE = os.path.join(DATA_DIR, "territory-latest.csv")

HTML_OUTPUT_PATH = "/var/www/ogfstats/territory.html"

os.makedirs(ADMIN_DIR, exist_ok=True)
os.makedirs(STATS_DIR, exist_ok=True)

ADMIN_JSON = os.path.join(ADMIN_DIR, "territory_admin.json")

# ================= HTML TEMPLATE =================
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>OGF Territory Stats</title>
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7BV9Y2QVPZ"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());
  gtag('config', 'G-7BV9Y2QVPZ');
</script>
<script src="https://code.highcharts.com/highcharts.js"></script>
<script src="https://code.highcharts.com/modules/accessibility.js"></script>
<script src="https://unpkg.com/papaparse@5.4.1/papaparse.min.js"></script>
<style>
    :root { --primary: #007bff; --primary-hover: #0056b3; --nav-bg: #333; --border: #e2e8f0; --panel-bg: #ffffff; --body-bg: #fafafa; }
    body { font-family: sans-serif; background: var(--body-bg); margin: 0; padding: 0; color: #1e293b; }
    .nav { background: var(--nav-bg); color: white; padding: 10px; display: flex; justify-content: center; gap: 20px; position: sticky; top: 0; z-index: 1000; }
    .nav a { color: #ccc; text-decoration: none; font-weight: bold; cursor: pointer; padding: 5px 15px; border-radius: 4px; transition: 0.2s; }
    .nav a:hover { color: white; background: #444; }
    .nav a.active { color: white; background: var(--primary); }
    .wrap { max-width: 1500px; margin: 24px auto; padding: 0 16px; }
    .header-section { margin-bottom: 20px; }
    h1 { font-size: 22px; margin: 0 0 8px 0; color: #333; }
    .meta { color: #666; font-size: 14px; }
    .dashboard-container { display: flex; gap: 20px; align-items: flex-start; }
    .control-panel { width: 320px; background: var(--panel-bg); border: 1px solid var(--border); border-radius: 16px; padding: 16px; position: sticky; top: 70px; display: flex; flex-direction: column; max-height: calc(100vh - 100px); box-shadow: 0 10px 30px rgba(0,0,0,0.06); }
    .search-box { width: 100%; padding: 10px; margin-bottom: 12px; border: 1px solid var(--border); border-radius: 6px; box-sizing: border-box; font-size: 14px; outline: none; }
    .btn-group { display: flex; gap: 8px; margin-bottom: 12px; }
    .btn-group button { flex: 1; padding: 8px; cursor: pointer; border-radius: 6px; border: 1px solid var(--border); background: #f5f5f5; font-size: 12px; font-weight: bold; transition: 0.2s; }
    .table-scroll { flex: 1; overflow-y: auto; border: 1px solid #007bff33; border-radius: 8px; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th { position: sticky; top: 0; background: var(--primary); color: white; padding: 10px 8px; text-align: left; z-index: 10; }
    td { padding: 8px; border-bottom: 1px solid #eee; cursor: pointer; }
    tr:hover { background: #f5f9ff; }
    .charts-area { flex: 1; min-width: 0; }
    .chart-card { background: var(--panel-bg); border: 1px solid #eee; border-radius: 16px; padding: 16px; margin-bottom: 24px; box-shadow: 0 4px 12px rgba(0,0,0,0.03); }
    .chart-container { width: 100%; height: 420px; }
    .footer { text-align: center; color: #999; font-size: 12px; margin: 40px 0; }
</style>
</head>
<body>
<div class="nav"><a href="index.html">Charts</a><a href="leaderboards.html">Leaderboards</a><a class="active">Territory Stats</a><a href="version.html">v4.0</a></div>
<div class="wrap">
    <div class="header-section"><h1>Territory Evolution Stats</h1><p class="meta" id="updateTime">Loading data...</p></div>
    <div class="dashboard-container">
        <aside class="control-panel">
            <input type="text" id="search" class="search-box" placeholder="Search territories...">
            <div class="btn-group"><button onclick="toggleAll(true)">Show All</button><button onclick="toggleAll(false)">Hide All</button></div>
            <div class="table-scroll"><table><thead><tr><th width="30"></th><th>Territory</th></tr></thead><tbody id="territoryList"></tbody></table></div>
        </aside>
        <main class="charts-area">
            <div class="chart-card"><div id="nodesHist" class="chart-container"></div></div>
            <div class="chart-card"><div id="waysHist" class="chart-container"></div></div>
            <div class="chart-card"><div id="relationsHist" class="chart-container"></div></div>
            <div class="chart-card"><div id="nodesBar" class="chart-container"></div></div>
            <div class="chart-card"><div id="waysBar" class="chart-container"></div></div>
            <div class="chart-card"><div id="relationsBar" class="chart-container"></div></div>
            <div class="footer">OGFStats by minimapper :)</div>
        </main>
    </div>
</div>
<script>
let lineCharts = [];
let loadedData = {};

async function loadCSV(path) {
    const res = await fetch(path , { cache: "no-store" });
    if (!res.ok) throw new Error("File not found");
    const text = await res.text();
    return Papa.parse(text, { header: true, skipEmptyLines: true }).data;
}

async function buildDashboard() {
    const snapshot = await loadCSV("./tdata/territory-latest.csv");

    // 1. Initialize empty line charts
    lineCharts = [
        createLineChart("nodesHist", "Nodes Over Time", "Nodes"),
        createLineChart("waysHist", "Ways Over Time", "Ways"),
        createLineChart("relationsHist", "Relations Over Time", "Relations")
    ];

    // 2. Load Bar Charts immediately using the snapshot
    const barData = {
        nodes: snapshot.map(r => ({ name: r.territory, y: +r.nodes })),
        ways: snapshot.map(r => ({ name: r.territory, y: +r.ways })),
        relations: snapshot.map(r => ({ name: r.territory, y: +r.relations }))
    };
    createBarChart("nodesBar", "Current Nodes", "Nodes", barData.nodes, '#007bff');
    createBarChart("waysBar", "Current Ways", "Ways", barData.ways, '#007bff');
    createBarChart("relationsBar", "Current Relations", "Relations", barData.relations, '#007bff');

    // 3. Populate List and handle Load-on-Demand
    const listBody = document.getElementById('territoryList');
    snapshot.sort((a,b) => a.territory.localeCompare(b.territory)).forEach((row, i) => {
        const name = row.territory;
        const tr = document.createElement('tr');
        const shouldAutoLoad = i < 5; // Load first 5 automatically

        tr.innerHTML = `<td><input type="checkbox" class="chk" data-name="${name}" data-rel="${row.rel}" ${shouldAutoLoad ? 'checked' : ''}></td><td>${name}</td>`;
        tr.onclick = (e) => {
            if(e.target.type !== 'checkbox') {
                const cb = tr.querySelector('.chk');
                cb.checked = !cb.checked;
                toggleTerritory(name, row.rel, cb.checked);
            }
        };
        tr.querySelector('.chk').onchange = (e) => toggleTerritory(name, row.rel, e.target.checked);
        listBody.appendChild(tr);

        if(shouldAutoLoad) toggleTerritory(name, row.rel, true);
    });

    document.getElementById("updateTime").innerText = "Last update: " + (snapshot[0]?.timestamp || "Unknown");
}

async function toggleTerritory(name, rel, state) {
    if (state) {
        if (!loadedData[name]) {
            const safeName = name.replace(/ /g, "_");
            const file = `tdata/territory/${safeName}_${rel}.csv`;
            try {
                const rows = await loadCSV(file);
                loadedData[name] = {
                    nodes: rows.map(r => [Date.parse(r.timestamp), +r.nodes]),
                    ways: rows.map(r => [Date.parse(r.timestamp), +r.ways]),
                    relations: rows.map(r => [Date.parse(r.timestamp), +r.relations])
                };
            } catch(e) { return; }
        }
        lineCharts[0].addSeries({ id: name, name: name, data: loadedData[name].nodes }, false);
        lineCharts[1].addSeries({ id: name, name: name, data: loadedData[name].ways }, false);
        lineCharts[2].addSeries({ id: name, name: name, data: loadedData[name].relations }, false);
    } else {
        lineCharts.forEach(chart => {
            const s = chart.get(name);
            if (s) s.remove(false);
        });
    }
    lineCharts.forEach(c => c.redraw());
}

function createLineChart(id, title, yAxisName) {
    return Highcharts.chart(id, {
        chart: { type: 'line', zoomType: 'x', style: { fontFamily: 'sans-serif' } },
        title: { text: title, align: 'left', style: { color: '#333', fontWeight: 'bold' } },
        xAxis: { type: 'datetime' },
        yAxis: { title: { text: yAxisName } },
        legend: { enabled: false },
        tooltip: { shared: true, crosshairs: true },
        plotOptions: {
            series: {
                marker: { enabled: false },
                stickyTracking: true,
                findNearestPointBy: 'x',
                turboThreshold: 0,
                animation: false
            }
        },
        credits: { enabled: false },
        series: []
    });
}

function createBarChart(id, title, yAxisName, data, color) {
    data.sort((a,b) => b.y - a.y);
    Highcharts.chart(id, {
        chart: { type: 'column' },
        title: { text: title, align: 'left', style: { color: '#333', fontWeight: 'bold' } },
        xAxis: { categories: data.map(d => d.name), labels: { enabled: false }, crosshair: true },
        yAxis: { title: { text: yAxisName } },
        tooltip: { shared: true, intersect: false },
        plotOptions: { column: { stickyTracking: true, borderWidth: 0 } },
        credits: { enabled: false },
        series: [{ name: yAxisName, data: data.map(d => d.y), color: color }]
    });
}

function toggleAll(state) {
    document.querySelectorAll('.chk').forEach(cb => {
        if(cb.checked !== state) {
            cb.checked = state;
            toggleTerritory(cb.dataset.name, cb.dataset.rel, state);
        }
    });
}

document.getElementById('search').addEventListener('input', (e) => {
    const val = e.target.value.toLowerCase();
    document.querySelectorAll('#territoryList tr').forEach(tr => {
        tr.style.display = tr.innerText.toLowerCase().includes(val) ? '' : 'none';
    });
});

buildDashboard();
</script>
</body>
</html>"""

# ================= HELPERS =================

def fetch_admin_json():
    if os.path.exists(ADMIN_JSON):
        return
    r = requests.get(TERRITORY_URL, timeout=60)
    r.raise_for_status()
    with open(ADMIN_JSON, "w", encoding="utf-8") as f:
        f.write(r.text)

def load_owned_territories():
    with open(ADMIN_JSON, encoding="utf-8") as f:
        data = json.load(f)
    return [t for t in data if t.get("status") == "owned" and t.get("rel")]

def run_overpass(rel_id):
    query = f'[out:json][timeout:900];relation({rel_id})->.rel;.rel map_to_area->.a;(node(area.a);way(area.a);relation(area.a););out count;.rel convert relation ::id = id(), name = t["name:en"] ? t["name:en"] : t["name"];out;'
    r = requests.post(OVERPASS_URL, data=query, timeout=300)
    r.raise_for_status()
    return r.json()

def parse_overpass(data):
    counts = next(el["tags"] for el in data["elements"] if el["type"] == "count")
    name = next((el.get("tags", {}).get("name", "unknown") for el in data["elements"] if el["type"] == "relation"), "unknown")
    
    # SCRUBBING: Remove commas and hidden line breaks
    name = name.replace('\n', ' ').replace('\r', ' ').replace(',', '').strip()
    # Clean up double spaces if any
    name = " ".join(name.split())
    
    return name, {k: int(counts[k]) for k in ["nodes", "ways", "relations", "areas", "total"]}

# ================= MAIN =================

def main():
    fetch_admin_json()
    territories = load_owned_territories()

    with open(HTML_OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(HTML_TEMPLATE)
    print(f"✓ HTML file created at {HTML_OUTPUT_PATH}.")

    timestamp = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    fieldnames = ["territory", "rel", "nodes", "ways", "relations", "areas", "total", "timestamp"]

    print(f"Processing {len(territories)} territories...")

    for i, t in enumerate(territories):
        rel_id = t["rel"]
        try:
            data = run_overpass(rel_id)
            name, stats = parse_overpass(data)
        except Exception as e:
            print(f"  ❌ Failed rel {rel_id}: {e}")
            continue

        # FILENAME SAFETY: Keep scripts like ꢡ, but remove commas and slashes
        safe_name = name.replace("/", "-").replace("\\", "-").replace(" ", "_").replace(",", "")
        
        # 1. Append to History
        hist_path = os.path.join(STATS_DIR, f"{safe_name}_{rel_id}.csv")
        write_h = not os.path.exists(hist_path)
        with open(hist_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
            if write_h: 
                writer.writerow(["timestamp", "nodes", "ways", "relations", "areas", "total"])
            writer.writerow([timestamp, stats["nodes"], stats["ways"], stats["relations"], stats["areas"], stats["total"]])

        # 2. Update Latest Snapshot LIVE
        mode = 'w' if i == 0 else 'a'
        with open(LATEST_FILE, mode, newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_MINIMAL)
            if i == 0: writer.writeheader()
            writer.writerow({"territory": name, "rel": rel_id, **stats, "timestamp": timestamp})

        print(f"[{i+1}/{len(territories)}] Processed: {name}")
        time.sleep(2)

if __name__ == "__main__":
    main()
