# OGFStats
- `ogfstats.py` – long-running service (hourly sync, user pages, launches `ts.py` once a day)
- `ts.py` – territory snapshot (data only)
- `generate_user_pages.py` – builds `users/<uid>.html` (called automatically; manual run optional)
- `web/` – all HTML/CSS/JS for the site (**must be deployed next to the .py files**)

Update: copy the files over, then `sudo systemctl restart ogfstats` (check name with `systemctl list-units | grep -i ogf`).
Logs: `journalctl -u ogfstats -f`. Local test: `python ogfstats.py --once` (writes to ./site).
