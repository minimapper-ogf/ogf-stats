import argparse
import json
import os
from pathlib import Path
from datetime import datetime
import statistics

from ogfstats import TARGET_DIR, USERS_DIR, NAV_BAR, STYLE_BLOCK, GOOGLE_BLOCK, VERSION

# OUT_DIR will be assigned at runtime based on args or default USERS_DIR
OUT_DIR = None

# Using clear placeholder tags like {{TITLE}} makes replacement foolproof
PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>{{TITLE}} - OGFStats</title>
  {{GOOGLE}}
  {{STYLE}}
  <script src="https://code.highcharts.com/highcharts.js"></script>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
</head>
<body>
  {{NAV}}
  <div class="wrap">
    <h1>{{DISPLAY_NAME}}</h1>
    <p class="meta">UID: {{UID}} &nbsp; | &nbsp; First: {{FIRST_TS}} &nbsp; | &nbsp; Last: {{LAST_TS}}</p>

    <div class="grid-2">
      <div class="card">
        <h2>Changesets per Day</h2>
        <div id="cs_count" class="chart-container"></div>
      </div>
      <div class="card">
        <h2>Objects Changed per Day</h2>
        <div id="obj_count" class="chart-container"></div>
      </div>

      <div class="card">
        <h2>Editor Usage</h2>
        <div id="editor_pie" class="chart-container" style="height:300px"></div>
      </div>
      <div class="card">
        <h2>Mapping Hours</h2>
        <div id="hour_bar" class="chart-container" style="height:300px"></div>
      </div>

      <div class="card full-width">
        <h2>Sources (Top)</h2>
        <div class="table-container"><table><thead><tr><th>Source</th><th>Count</th></tr></thead><tbody id="sources_table"></tbody></table></div>
      </div>

      <div class="card">
        <h2>Map</h2>
        <div id="map" style="height:360px; border-radius:12px; overflow:hidden"></div>
      </div>
      <div class="card">
        <h2>Summary</h2>
        <p>Total changesets: {{TOTAL_CS}}</p>
        <p>Total objects changed: {{TOTAL_OBJS}}</p>
        <p>Average changeset position: {{AVG_POS}}</p>
      </div>
    </div>

  </div>
  <div class="footer">OGFStats v{{VERSION}} by minimapper :)</div>

<script>
  const userData = {{DATA_JSON}};

  // Prepare daily series
  const csByDay = Object.entries(userData.per_day_cs).sort((a,b)=>new Date(a[0])-new Date(b[0]));
  const objByDay = Object.entries(userData.per_day_objs).sort((a,b)=>new Date(a[0])-new Date(b[0]));

  Highcharts.chart('cs_count', { chart: { type: 'column' }, title: { text: 'Changesets per Day' }, xAxis: { categories: csByDay.map(a=>a[0]) }, series: [{ name: 'Changesets', data: csByDay.map(a=>a[1]) }] });

  Highcharts.chart('obj_count', { chart: { type: 'column' }, title: { text: 'Objects Changed per Day' }, xAxis: { categories: objByDay.map(a=>a[0]) }, series: [{ name: 'Objects', data: objByDay.map(a=>a[1]) }] });

  Highcharts.chart('editor_pie', { chart: { type: 'pie' }, title: { text: 'Editor Usage' }, series: [{ name: 'Uses', data: Object.entries(userData.editors).map(e=>({name:e[0], y:e[1]})) }] });

  Highcharts.chart('hour_bar', { chart: { type: 'column' }, title: { text: 'Mapping Hours' }, xAxis: { categories: [...Array(24).keys()].map(h=>String(h)) }, series: [{ name: 'Changesets', data: Array.from({length:24}, (_,i)=>userData.hours[i]||0) }] });

  // sources table
  const tbody = document.getElementById('sources_table');
  const sortedSources = Object.entries(userData.sources).sort((a,b)=>b[1]-a[1]).slice(0,50);
  tbody.innerHTML = sortedSources.map(s=>`<tr><td>${s[0]}</td><td>${s[1]}</td></tr>`).join('');

  // map
  const map = L.map('map', { center: [userData.map_center.lat||0, userData.map_center.lon||0], zoom: 6 });
  L.tileLayer('https://tile.opengeofiction.net/ogf-carto/{z}/{x}/{y}.png', { maxZoom: 19, attribution: 'OGF Tiles' }).addTo(map);
  if(userData.last_pos.lat && userData.last_pos.lon) L.marker([userData.last_pos.lat, userData.last_pos.lon]).addTo(map).bindPopup('Latest changeset');
  if(userData.first_pos.lat && userData.first_pos.lon) L.marker([userData.first_pos.lat, userData.first_pos.lon]).addTo(map).bindPopup('First tracked changeset');
  if(userData.avg_pos.lat && userData.avg_pos.lon) L.circleMarker([userData.avg_pos.lat, userData.avg_pos.lon], { radius:6, color:'#007bff' }).addTo(map).bindPopup('Average position');

</script>
</body>
</html>
"""


def build_user_page(userfile: Path):
    try:
        lst = json.loads(userfile.read_text(encoding='utf-8'))
    except Exception as e:
        print(f"Failed to read {userfile}: {e}")
        return
    if not lst:
        return
    # sort by created_at
    lst_sorted = sorted(lst, key=lambda x: x.get('created_at') or '')
    uid = userfile.stem
    user = lst_sorted[-1].get('user', '')

    per_day_cs = {}
    per_day_objs = {}
    editors = {}
    sources = {}
    hours = [0]*24
    lats = []
    lons = []

    for e in lst_sorted:
        ts = e.get('created_at') or e.get('created_at') or ''
        day = ts.split('T')[0] if 'T' in ts else ts
        per_day_cs[day] = per_day_cs.get(day, 0) + 1
        per_day_objs[day] = per_day_objs.get(day, 0) + int(e.get('changes_count') or e.get('changes_count')==0 and 0 or 0) if e.get('changes_count') is not None else per_day_objs.get(day,0)
        ed = e.get('created_by') or ''
        if ed: editors[ed] = editors.get(ed,0)+1
        src = e.get('source') or ''
        if src: sources[src] = sources.get(src,0)+1
        try:
            cts = e.get('created_at')
            h = 0
            if cts and 'T' in cts:
                h = int(cts.split('T')[1].split(':')[0])
            hours[h] += 1
        except:
            pass
        if e.get('lat') is not None and e.get('lon') is not None:
            try:
                lats.append(float(e.get('lat')))
                lons.append(float(e.get('lon')))
            except:
                pass

    total_cs = len(lst_sorted)
    total_objs = sum([int(e.get('changes_count') or 0) for e in lst_sorted])
    avg_pos = {'lat': None, 'lon': None}
    if lats and lons:
        avg_pos['lat'] = sum(lats)/len(lats)
        avg_pos['lon'] = sum(lons)/len(lons)

    first_ts = lst_sorted[0].get('created_at','')
    last_ts = lst_sorted[-1].get('created_at','')
    first_pos = {'lat': lst_sorted[0].get('lat'), 'lon': lst_sorted[0].get('lon')}
    last_pos = {'lat': lst_sorted[-1].get('lat'), 'lon': lst_sorted[-1].get('lon')}

    data_json = json.dumps({
        'per_day_cs': per_day_cs,
        'per_day_objs': per_day_objs,
        'editors': editors,
        'sources': sources,
        'hours': hours,
        'map_center': avg_pos,
        'avg_pos': avg_pos,
        'first_pos': first_pos,
        'last_pos': last_pos,
    })

    # Switched from .format() to clean text replacement chains
    html = (PAGE_TEMPLATE
            .replace("{{TITLE}}", f"OGFStats - {user}")
            .replace("{{GOOGLE}}", GOOGLE_BLOCK)
            .replace("{{STYLE}}", STYLE_BLOCK)
            .replace("{{NAV}}", NAV_BAR)
            .replace("{{DISPLAY_NAME}}", user or 'Unknown')
            .replace("{{UID}}", uid)
            .replace("{{FIRST_TS}}", first_ts)
            .replace("{{LAST_TS}}", last_ts)
            .replace("{{TOTAL_CS}}", str(total_cs))
            .replace("{{TOTAL_OBJS}}", str(total_objs))
            .replace("{{AVG_POS}}", f"{avg_pos.get('lat')},{avg_pos.get('lon')}")
            .replace("{{DATA_JSON}}", data_json)
            .replace("{{VERSION}}", VERSION))

    outpath = OUT_DIR / f"{uid}.html"
    outpath.write_text(html, encoding='utf-8')
    print(f"Wrote {outpath}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--outdir', type=str, default=None, help='Base output directory (e.g. ./site). Uses <outdir>/users as input and output.')
    args = parser.parse_args()

    global OUT_DIR
    if args.outdir:
        base = Path(args.outdir).resolve()
        users_src = base / 'users'
        OUT_DIR = users_src
    else:
        users_src = USERS_DIR
        OUT_DIR = USERS_DIR

    # ensure output dir exists
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    files = sorted(users_src.glob('*.json'))
    for f in files:
        if f.name == 'index.json':
            continue
        build_user_page(f)

    # rebuild index.json (uid + user)
    index = []
    for f in files:
        if f.name == 'index.json':
            continue
        try:
            lst = json.loads(f.read_text(encoding='utf-8'))
            if not lst:
                continue
            index.append({'uid': f.stem, 'user': lst[-1].get('user','')})
        except:
            continue
    (OUT_DIR / 'index.json').write_text(json.dumps(index, indent=2), encoding='utf-8')
    print('User pages generation complete.')


if __name__ == '__main__':
    main()