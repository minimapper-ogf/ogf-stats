"""Builds users/<uid>.html from users/<uid>.json (the raw per-user changeset lists).
ogfstats.py calls this automatically; you can still run it by hand:
    python generate_user_pages.py            # all users
    python generate_user_pages.py --uid 123  # one user
"""
import argparse, html, json, os, re
from pathlib import Path

TEMPLATE_PATH = Path(__file__).resolve().parent / "web" / "user_template.html"
MARKER = ".pages_version"


def atomic_write(path, text):
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def norm_editor(s):
    s = (s or "").strip()
    return re.split(r"[\s/]", s, maxsplit=1)[0] if s else ""


def build_user_data(uid, lst):
    lst = sorted(lst, key=lambda x: x.get("created_at") or "")
    days, hours, editors, sources, seen_pts, pts = {}, [0] * 24, {}, {}, set(), []
    total_objs = 0
    for e in lst:
        ts = e.get("created_at") or ""
        try:
            objs = int(e.get("changes_count") or 0)
        except (TypeError, ValueError):
            objs = 0
        total_objs += objs
        if len(ts) >= 10:
            d = days.setdefault(ts[:10], [0, 0])
            d[0] += 1
            d[1] += objs
        if len(ts) >= 13 and ts[11:13].isdigit() and int(ts[11:13]) < 24:
            hours[int(ts[11:13])] += 1
        ed = norm_editor(e.get("created_by"))
        if ed:
            editors[ed] = editors.get(ed, 0) + 1
        src = (e.get("source") or "").strip()
        if src:
            sources[src] = sources.get(src, 0) + 1
    for e in reversed(lst):  # newest first, capped
        if len(pts) >= 400:
            break
        try:
            p = (round(float(e["lat"]), 3), round(float(e["lon"]), 3))
        except (KeyError, TypeError, ValueError):
            continue
        if p not in seen_pts:
            seen_pts.add(p)
            pts.append(list(p))
    recent = [{"id": e.get("id"), "t": e.get("created_at"), "c": (e.get("comment") or "")[:200],
               "e": norm_editor(e.get("created_by")), "o": int(e.get("changes_count") or 0)}
              for e in reversed(lst[-15:])]
    top_sources = dict(sorted(sources.items(), key=lambda kv: -kv[1])[:30])
    return {"uid": uid, "user": lst[-1].get("user") or "", "first": lst[0].get("created_at") or "",
            "last": lst[-1].get("created_at") or "", "total_cs": len(lst), "total_objs": total_objs,
            "days": days, "hours": hours, "editors": editors, "sources": top_sources,
            "recent": recent, "points": pts}


def render_page(data, version, template):
    payload = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    payload = payload.replace("</", "<\\/").replace("<!--", "<\\!--")
    return (template.replace("__TITLE__", html.escape(data["user"] or "Unknown"))
            .replace("__V__", version).replace("__DATA__", payload))  # __DATA__ last on purpose


def update_index(users_dir, names, rebuild=False):
    idx_file = users_dir / "index.json"
    cur = {}
    if not rebuild and idx_file.exists():
        try:
            cur = {str(i["uid"]): i.get("user", "") for i in json.loads(idx_file.read_text(encoding="utf-8"))}
        except Exception:
            cur = {}
    cur.update(names)
    out = sorted(({"uid": u, "user": n} for u, n in cur.items()), key=lambda i: (i["user"] or "").lower())
    atomic_write(idx_file, json.dumps(out, indent=2))


def generate_pages(users_dir, version, uids=None, template_path=TEMPLATE_PATH):
    """uids=None regenerates every user (and rebuilds index.json)."""
    users_dir = Path(users_dir)
    users_dir.mkdir(parents=True, exist_ok=True)
    template = Path(template_path).read_text(encoding="utf-8")
    if uids is None:
        files = [f for f in sorted(users_dir.glob("*.json")) if f.name != "index.json"]
    else:
        files = [users_dir / f"{u}.json" for u in uids]
    names = {}
    for f in files:
        try:
            lst = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"Skipping {f.name}: {e}")
            continue
        if not lst:
            continue
        data = build_user_data(f.stem, lst)
        atomic_write(users_dir / f"{f.stem}.html", render_page(data, version, template))
        names[f.stem] = data["user"]
    update_index(users_dir, names, rebuild=uids is None)
    return len(names)


def pages_current(users_dir, version):
    m = Path(users_dir) / MARKER
    return m.exists() and m.read_text().strip() == version


def mark_pages(users_dir, version):
    (Path(users_dir) / MARKER).write_text(version)


def main():
    import ogfstats  # lazy: ogfstats imports this module
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", help="site base dir (uses <outdir>/users)")
    ap.add_argument("--uid", action="append", help="only this uid (repeatable)")
    a = ap.parse_args()
    users = (Path(a.outdir).resolve() / "users") if a.outdir else ogfstats.USERS_DIR
    n = generate_pages(users, ogfstats.VERSION, a.uid)
    if not a.uid:
        mark_pages(users, ogfstats.VERSION)
    print(f"Generated {n} user pages.")


if __name__ == "__main__":
    main()
