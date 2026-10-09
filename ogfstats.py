import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from bisect import bisect_left
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.request import urlopen, Request
import xml.etree.ElementTree as ET

import generate_user_pages
from generate_user_pages import atomic_write

# --- CONFIGURATION ---
HERE = Path(__file__).resolve().parent
WEB_DIR = HERE / "web"
OGF_CHANGESETS_URL = "https://opengeofiction.net/api/0.6/changesets"
VERSION = "7.0"
TARGET_DIR = Path("/var/www/ogfstats")
CACHE_DIR = TARGET_DIR / "user_cache"
USERS_DIR = TARGET_DIR / "users"
ROLLING_DAYS = 31          # how much raw changeset history is kept for rolling windows
HISTORY_POINTS = 24 * 400  # hourly points kept for the rolling mapper series
HOURLY_POINTS = 720

VERSION_HISTORY = [
    {"v": "7.0", "date": "2026-10-09", "note": "Site redesign with shared theme, light/dark toggle and better search. User pages now update automatically every hour. Rolling daily/weekly/monthly mapper counts no longer reset at the start of each month."},
    {"v": "6.0", "date": "2026-06-16", "note": "Individual user data :)"},
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



def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def get_initial_data():
    return {
        "hourly": [], "daily": [], "hourly_leaderboards": [],
        "rolling24": [], "monthly_store": [], "monthly_leaderboard": [],
        "last_month_update": "", "last_daily_run_day": "", "seen_ids": [],
        "daily_mapper_counts": [], "weekly_mapper_counts": [], "monthly_mapper_counts": []
    }


def fetch_recent_changesets(lookback_hours=2):
    start_time = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    url = f"{OGF_CHANGESETS_URL}?time={start_time.strftime('%Y-%m-%dT%H:00:00Z')}"
    req = Request(url, headers={"User-Agent": f"ogf-stats-script/{VERSION}"})
    try:
        with urlopen(req, timeout=20) as resp:
            root = ET.fromstring(resp.read())

        out = []
        for cs in root.findall("changeset"):
            tags = {t.get('k'): t.get('v') for t in cs.findall('tag')}
            try:
                min_lat = float(cs.get('min_lat')) if cs.get('min_lat') else None
                min_lon = float(cs.get('min_lon')) if cs.get('min_lon') else None
                max_lat = float(cs.get('max_lat')) if cs.get('max_lat') else None
                max_lon = float(cs.get('max_lon')) if cs.get('max_lon') else None
            except:
                min_lat = min_lon = max_lat = max_lon = None

            lat = None; lon = None
            if min_lat is not None and max_lat is not None:
                lat = (min_lat + max_lat) / 2.0
            if min_lon is not None and max_lon is not None:
                lon = (min_lon + max_lon) / 2.0

            out.append({
                "id": cs.get("id"),
                "user": cs.get("user"),
                "uid": cs.get("uid"),
                "changes_count": int(cs.get("changes_count", "0")),
                "created_at": cs.get("created_at"),
                "closed_at": cs.get("closed_at"),
                # FIX: Explicitly pass "ts" down so monthly filtering condition handles it properly
                "ts": cs.get("created_at"),
                "comment": tags.get('comment',''),
                "created_by": tags.get('created_by',''),
                "source": tags.get('source',''),
                "min_lat": min_lat,
                "min_lon": min_lon,
                "max_lat": max_lat,
                "max_lon": max_lon,
                "lat": lat,
                "lon": lon
            })
        return out
    except Exception as e:
        print(f"Fetch error: {e}"); return []

def tally_users(entries):
    counts = {}
    for e in entries:
        key = (e["user"], e["uid"])
        if key not in counts: counts[key] = {"count": 0, "objects": 0}
        counts[key]["count"] += 1; counts[key]["objects"] += e.get("changes_count", 0)
    return [{"user": u, "uid": uid, "count": c["count"], "objects": c["objects"]} for (u, uid), c in sorted(counts.items(), key=lambda kv: (kv[1]["count"], kv[1]["objects"]), reverse=True)]

def dedupe(entries):
    seen, out = set(), []
    for e in entries:
        if e.get("id") in seen:
            continue
        seen.add(e.get("id"))
        out.append(e)
    return out


def load_cache_entries(since_dt):
    """Entries from the per-day cache files (written by every run since the start)."""
    out = []
    if not CACHE_DIR.exists():
        return out
    since_day = (since_dt - timedelta(days=1)).strftime("%Y-%m-%d")
    for f in sorted(CACHE_DIR.glob("*.json")):
        if f.stem < since_day:
            continue
        try:
            for e in json.loads(f.read_text(encoding="utf-8")):
                e.setdefault("ts", e.get("created_at"))
                out.append(e)
        except Exception:
            continue
    return out


def rebuild_rolling_history(data):
    """One-time repair: recompute the old (month-reset) rolling mapper counts from the cache files."""
    spans = {"daily_mapper_counts": 1, "weekly_mapper_counts": 7, "monthly_mapper_counts": 30}
    dates = [p["date"] for k in spans for p in data.get(k, [])]
    if not dates:
        return 0
    entries = dedupe(load_cache_entries(parse_iso(min(dates)) - timedelta(days=31)))
    people = sorted((e["ts"], f'{e.get("user")}|{e.get("uid")}') for e in entries if e.get("ts"))
    if not people:
        return 0
    times = [t for t, _ in people]
    fixed = 0
    for key, days in spans.items():
        for p in data.get(key, []):
            start = iso(parse_iso(p["date"]) - timedelta(days=days))
            if start < times[0]:
                continue  # cache doesn't cover this window, leave as is
            lo = bisect_left(times, start)
            hi = bisect_left(times, p["date"] + "~")  # everything up to and including this timestamp
            p["count"] = len({u for _, u in people[lo:hi]})
            fixed += 1
    return fixed


def downsample(points, keep=24 * 14):
    """Older points -> one per day, recent ones untouched (keeps stats.json small)."""
    if len(points) <= keep:
        return points
    older, recent = points[:-keep], points[-keep:]
    by_day = {}
    for p in older:
        by_day[p["date"][:10]] = p
    return list(by_day.values()) + recent


def write_public_stats(data):
    """Slim file for the website (data.json also contains the big internal state)."""
    hl = data.get("hourly_leaderboards", [])
    out = {
        "last_month_update": data.get("last_month_update", ""),
        "hourly": data.get("hourly", []), "daily": data.get("daily", []),
        "monthly_leaderboard": data.get("monthly_leaderboard", []),
        "daily_leaderboard": data.get("daily_leaderboard", []),
        "hourly_leaderboards": hl[-1:],
        "daily_mapper_counts": downsample(data.get("daily_mapper_counts", [])),
        "weekly_mapper_counts": downsample(data.get("weekly_mapper_counts", [])),
        "monthly_mapper_counts": downsample(data.get("monthly_mapper_counts", [])),
    }
    atomic_write(TARGET_DIR / "stats.json", json.dumps(out, separators=(",", ":")))


def run_update(data_file, now):
    """Fetch new changesets, update data.json / user files. Returns {uid: username} of changed users."""
    data = get_initial_data()
    if data_file.exists():
        data.update(json.loads(data_file.read_text(encoding="utf-8")))  # raises on corrupt file: never overwrite it

    raw_entries = fetch_recent_changesets()
    seen_list = list(data.get("seen_ids", []))
    seen = set(seen_list)
    new_entries = []
    for e in raw_entries:
        if e["id"] in seen:
            continue
        seen.add(e["id"]); seen_list.append(e["id"]); new_entries.append(e)
    data["seen_ids"] = seen_list[-5000:]

    bucket_ts = now.replace(minute=0, second=0, microsecond=0)
    ts_str = iso(bucket_ts)
    data["last_month_update"] = iso(now)
    cid = int(raw_entries[0]["id"]) if raw_entries else (data["hourly"][-1]["changeset_id"] if data["hourly"] else 0)

    existing_hourly = next((i for i in data["hourly"] if i["timestamp"] == ts_str), None)
    if existing_hourly:
        existing_hourly["change"] += len(new_entries)
        existing_hourly["changeset_id"] = cid
    else:
        data["hourly"].append({"timestamp": ts_str, "changeset_id": cid, "change": len(new_entries)})
        data["hourly"] = data["hourly"][-HOURLY_POINTS:]

    # daily totals (previously never filled in); seeded from the hourly history the first time
    day_ts = now.strftime("%Y-%m-%dT00:00:00Z")
    daily = data.get("daily") or []
    if not daily:
        by_day = {}
        for h in data["hourly"]:
            d = h["timestamp"][:10] + "T00:00:00Z"
            r = by_day.setdefault(d, {"timestamp": d, "changeset_id": 0, "change": 0})
            r["change"] += h.get("change", 0); r["changeset_id"] = h["changeset_id"]
        daily = list(by_day.values())
    elif daily[-1]["timestamp"] == day_ts:
        daily[-1]["change"] += len(new_entries); daily[-1]["changeset_id"] = cid
    else:
        daily.append({"timestamp": day_ts, "changeset_id": cid, "change": len(new_entries)})
    data["daily"] = daily[-1000:]

    # --- rolling store: keep ~31 days so day/week/30-day windows never reset at month change
    store = data.get("monthly_store") or []
    if not data.get("store_backfilled"):
        store = store + load_cache_entries(now - timedelta(days=ROLLING_DAYS))
        data["store_backfilled"] = True
    store = dedupe(store + new_entries)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    keep_from = iso(min(month_start, now - timedelta(days=ROLLING_DAYS)))
    store = [e for e in store if (e.get("ts") or "") >= keep_from]
    data["monthly_store"] = store

    this_month = now.strftime("%Y-%m")
    t24, t7, t30 = (iso(now - timedelta(days=d)) for d in (1, 7, 30))
    today_list = tally_users([e for e in store if (e.get("ts") or "") >= t24])
    week_list = tally_users([e for e in store if (e.get("ts") or "") >= t7])
    roll30 = tally_users([e for e in store if (e.get("ts") or "") >= t30])
    full_month = tally_users([e for e in store if (e.get("ts") or "").startswith(this_month)])

    for key, lst in (("daily_mapper_counts", today_list), ("weekly_mapper_counts", week_list), ("monthly_mapper_counts", roll30)):
        data.setdefault(key, []).append({"date": ts_str, "count": len(lst)})
        data[key] = data[key][-HISTORY_POINTS:]

    today_map = {x["uid"]: x["objects"] for x in today_list}
    week_map = {x["uid"]: x["objects"] for x in week_list}
    for u in full_month:
        u["d_today"] = today_map.get(u["uid"], 0)
        u["d_week"] = week_map.get(u["uid"], 0)
    data["monthly_leaderboard"] = full_month   # calendar month, by design
    data["daily_leaderboard"] = today_list

    data.setdefault("hourly_leaderboards", []).append({"timestamp": ts_str, "leaderboard": tally_users(new_entries)})
    data["hourly_leaderboards"] = data["hourly_leaderboards"][-48:]
    atomic_write(data_file, json.dumps(data, indent=2))
    write_public_stats(data)

    changed = {}
    if new_entries:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        USERS_DIR.mkdir(parents=True, exist_ok=True)
        dayfile = CACHE_DIR / (now.strftime("%Y-%m-%d") + ".json")
        daily_cache = []
        if dayfile.exists():
            try: daily_cache = json.loads(dayfile.read_text(encoding="utf-8"))
            except Exception: daily_cache = []
        daily_cache.extend(new_entries)
        atomic_write(dayfile, json.dumps(daily_cache, indent=2))

        by_uid = {}
        for e in new_entries:
            by_uid.setdefault(str(e.get("uid") or "unknown"), []).append(e)
        for uid, es in by_uid.items():
            userfile = USERS_DIR / f"{uid}.json"
            ulist = []
            if userfile.exists():
                try:
                    ulist = json.loads(userfile.read_text(encoding="utf-8"))
                except Exception:
                    shutil.copyfile(userfile, userfile.with_name(f"{uid}.json.corrupt"))
                    ulist = []
            for e in es:
                entry = {k: e.get(k) for k in ["id", "created_at", "closed_at", "comment", "created_by", "source", "changes_count", "lat", "lon"]}
                entry["user"] = e.get("user"); entry["uid"] = uid
                ulist.append(entry)
            atomic_write(userfile, json.dumps(ulist, indent=2))
            changed[uid] = es[-1].get("user") or ""
    return changed


def install_site():
    """Copy web/ (html, css, js) into the served directory and write assets/meta.js."""
    if not WEB_DIR.is_dir():
        raise SystemExit(f"web/ folder not found next to ogfstats.py ({WEB_DIR}) - copy it from the repo.")
    for src in WEB_DIR.rglob("*"):
        if src.is_dir() or src.name.endswith("_template.html"):
            continue
        dst = TARGET_DIR / src.relative_to(WEB_DIR)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.suffix in (".html", ".css", ".js"):
            atomic_write(dst, src.read_text(encoding="utf-8").replace("__V__", VERSION))
        else:
            shutil.copyfile(src, dst)
    meta = {"version": VERSION, "history": VERSION_HISTORY}
    atomic_write(TARGET_DIR / "assets" / "meta.js", "window.OGF_META = " + json.dumps(meta) + ";")


def update_user_pages(changed):
    try:
        if changed:
            generate_user_pages.generate_pages(USERS_DIR, VERSION, uids=list(changed))
    except Exception as e:
        print(f"User page generation error: {e}")


def startup_maintenance(data_file):
    """Automatic one-time jobs after an upgrade (no manual steps needed)."""
    if data_file.exists():
        data = json.loads(data_file.read_text(encoding="utf-8"))
        if not data.get("rolling_rebuilt"):
            n = rebuild_rolling_history(data)
            data["rolling_rebuilt"] = True
            atomic_write(data_file, json.dumps(data, indent=2))
            print(f"Rebuilt {n} rolling-count points from cache.")
        write_public_stats(data)
    if USERS_DIR.exists() and not generate_user_pages.pages_current(USERS_DIR, VERSION):
        print("Regenerating all user pages for this version...")
        n = generate_user_pages.generate_pages(USERS_DIR, VERSION)
        generate_user_pages.mark_pages(USERS_DIR, VERSION)
        print(f"Generated {n} user pages.")


def territory_job(data_file, now, state):
    """Runs ts.py once per UTC day in the background so hourly syncs are never blocked."""
    today = now.strftime("%Y-%m-%d")
    proc = state.get("proc")
    if proc is not None:
        rc = proc.poll()
        if rc is None:
            return
        state["proc"] = None
        if rc == 0:
            print("ts.py finished OK")
            try:
                d = json.loads(data_file.read_text(encoding="utf-8"))
                d["last_daily_run_day"] = state["day"]
                atomic_write(data_file, json.dumps(d, indent=2))
            except Exception as e:
                print(f"Could not record ts.py run: {e}")
        else:
            state["fails"][state["day"]] = state["fails"].get(state["day"], 0) + 1
            print(f"ts.py failed (exit {rc})")
    try:
        last = json.loads(data_file.read_text(encoding="utf-8")).get("last_daily_run_day")
    except Exception:
        last = None
    if last == today or state["fails"].get(today, 0) >= 3:
        return
    print(f"Starting ts.py for {today} ...")
    state["proc"] = subprocess.Popen([sys.executable, str(HERE / "ts.py"), "--outdir", str(TARGET_DIR)], cwd=str(HERE))
    state["day"] = today


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Run a single update and exit (good for testing)")
    parser.add_argument("--outdir", type=str, default=None, help="Override output directory (e.g. ./site)")
    args = parser.parse_args()

    global TARGET_DIR, CACHE_DIR, USERS_DIR
    if args.once and not args.outdir:
        args.outdir = str(HERE / "site")
    if args.outdir:
        TARGET_DIR = Path(args.outdir).resolve()
        CACHE_DIR = TARGET_DIR / "user_cache"
        USERS_DIR = TARGET_DIR / "users"
    TARGET_DIR.mkdir(parents=True, exist_ok=True)

    install_site()
    data_file = TARGET_DIR / "data.json"
    print(f"Starting OGFStats v{VERSION}...")
    startup_maintenance(data_file)

    if args.once:
        update_user_pages(run_update(data_file, datetime.now(timezone.utc)))
        print("One-shot update done.")
        return

    state = {"proc": None, "day": None, "fails": {}}
    while True:
        try:
            now = datetime.now(timezone.utc)
            update_user_pages(run_update(data_file, now))
            territory_job(data_file, now, state)
        except Exception as e:
            print(f"Critical Loop error: {e}")
        now = datetime.now(timezone.utc)
        wait = 3600 - (now.minute * 60 + now.second) + 5
        print(f"Sync complete at {now.strftime('%H:%M:%S')}. Next run in {wait}s...")
        time.sleep(max(0, wait))


if __name__ == "__main__":
    main()
