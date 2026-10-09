import os
import csv
import json
import time
import argparse
import requests
from datetime import datetime, timezone

# ================= CONFIG =================

TERRITORY_URL = "https://wiki.opengeofiction.net/index.php/OpenGeofiction:Territory_administration?action=raw"
OVERPASS_URL = "https://overpass.opengeofiction.net/api/interpreter"

DATA_DIR = "/var/www/ogfstats/tdata"
ADMIN_DIR = os.path.join(DATA_DIR, "territory-admin")
STATS_DIR = os.path.join(DATA_DIR, "territory")
LATEST_FILE = os.path.join(DATA_DIR, "territory-latest.csv")
ADMIN_JSON = os.path.join(ADMIN_DIR, "territory_admin.json")
WEEK_IN_SECONDS = 604800  # 7 days * 24h * 60m * 60s

# ================= HELPERS =================

def fetch_admin_json():
    """Downloads the territory admin file if missing or older than 1 week."""
    should_download = False

    if not os.path.exists(ADMIN_JSON):
        print("Admin JSON missing. Downloading...")
        should_download = True
    else:
        # Check file age
        file_age = time.time() - os.path.getmtime(ADMIN_JSON)
        if file_age > WEEK_IN_SECONDS:
            print("Admin JSON is over a week old. Updating...")
            should_download = True

    if should_download:
        try:
            r = requests.get(TERRITORY_URL, timeout=60)
            r.raise_for_status()
            with open(ADMIN_JSON, "w", encoding="utf-8") as f:
                f.write(r.text)
            print("✓ Admin JSON updated successfully.")
        except Exception as e:
            print(f"❌ Failed to update Admin JSON: {e}")
            if not os.path.exists(ADMIN_JSON):
                raise # Exit if we don't even have a stale version to fall back on

def load_owned_territories():
    with open(ADMIN_JSON, encoding="utf-8") as f:
        data = json.load(f)
    valid_statuses = {"owned", "collaborative", "collabrative"}
    return [t for t in data if t.get("status") in valid_statuses and t.get("rel")]


def run_overpass(rel_id):
    query = f'[out:json][timeout:900];relation({rel_id})->.rel;.rel map_to_area->.a;(node(area.a);way(area.a);relation(area.a););out count;.rel convert relation ::id = id(), name = t["name:en"] ? t["name:en"] : t["name"];out;'
    r = requests.post(OVERPASS_URL, data=query, timeout=300)
    r.raise_for_status()
    return r.json()

def parse_overpass(data):
    counts = next(el["tags"] for el in data["elements"] if el["type"] == "count")
    name = next((el.get("tags", {}).get("name", "unknown") for el in data["elements"] if el["type"] == "relation"), "unknown")

    # SCRUBBING: Remove commas and hidden line breaks for CSV safety
    name = name.replace('\n', ' ').replace('\r', ' ').replace(',', '').strip()
    name = " ".join(name.split())

    return name, {k: int(counts[k]) for k in ["nodes", "ways", "relations", "areas", "total"]}

# ================= MAIN =================

def main():
    global DATA_DIR, ADMIN_DIR, STATS_DIR, LATEST_FILE, ADMIN_JSON
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", help="site base dir (default /var/www/ogfstats); data goes in <outdir>/tdata")
    args = ap.parse_args()
    if args.outdir:
        DATA_DIR = os.path.join(args.outdir, "tdata")
        ADMIN_DIR = os.path.join(DATA_DIR, "territory-admin")
        STATS_DIR = os.path.join(DATA_DIR, "territory")
        LATEST_FILE = os.path.join(DATA_DIR, "territory-latest.csv")
        ADMIN_JSON = os.path.join(ADMIN_DIR, "territory_admin.json")
    os.makedirs(ADMIN_DIR, exist_ok=True)
    os.makedirs(STATS_DIR, exist_ok=True)

    fetch_admin_json()
    territories = load_owned_territories()

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    fieldnames = ["territory", "rel", "nodes", "ways", "relations", "areas", "total", "timestamp"]
    print(f"Processing {len(territories)} territories...")

    # Build the snapshot in a temp file and swap it in at the end, so the website
    # never sees a half-written file (and a failed first territory can't break the header).
    tmp_latest = LATEST_FILE + ".tmp"
    with open(tmp_latest, "w", newline="", encoding="utf-8") as lf:
        latest = csv.DictWriter(lf, fieldnames=fieldnames, quoting=csv.QUOTE_MINIMAL)
        latest.writeheader()
        for i, t in enumerate(territories):
            rel_id = t["rel"]
            try:
                data = run_overpass(rel_id)
                name, stats = parse_overpass(data)
            except Exception as e:
                print(f"  Failed rel {rel_id}: {e}")
                continue

            safe_name = name.replace(",", "").replace("/", "-").replace("\\", "-").replace(" ", "_")
            hist_path = os.path.join(STATS_DIR, f"{safe_name}_{rel_id}.csv")
            write_h = not os.path.exists(hist_path)
            with open(hist_path, "a", newline="", encoding="utf-8") as f:
                w = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
                if write_h:
                    w.writerow(["timestamp", "nodes", "ways", "relations", "areas", "total"])
                w.writerow([timestamp, stats["nodes"], stats["ways"], stats["relations"], stats["areas"], stats["total"]])

            latest.writerow({"territory": name, "rel": rel_id, **stats, "timestamp": timestamp})
            lf.flush()
            print(f"[{i+1}/{len(territories)}] Processed: {name}")
            time.sleep(2)
    os.replace(tmp_latest, LATEST_FILE)


if __name__ == "__main__":
    main()
