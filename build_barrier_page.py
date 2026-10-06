"""Scan today's UK + Irish racecards for ITM Barrier Trial horses and build a
static results page (index.html) for GitHub Pages.

This is the hosted version of barrier_trial_watch.py. It runs on a schedule via
GitHub Actions (first thing each morning), using the Ladbrokes API key stored
as a GitHub Secret in the environment variable LADS_API_KEY. It never prints or
embeds the key.

The barrier-trial horse list lives in barrier_trial_horses.csv (columns:
batch, position, horse). Matching is on exact normalised name.

Usage (local test):
    set LADS_API_KEY=...        (Windows)   / export on mac/linux
    python build_barrier_page.py
    python build_barrier_page.py --countries UK,IRE --day today
"""

import argparse
import csv
import html
import re
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

UK_TZ = ZoneInfo("Europe/London")  # always show the time in UK local time,
                                   # whatever timezone the build machine uses

import console_utf8  # noqa: F401  (force UTF-8 console output on Windows)
from lads_client import LadsClient, detect_country, parse_event_name

HORSES_FILE = "barrier_trial_horses.csv"
DEFAULT_COUNTRIES = ("UK", "IRE")
TRIAL_LABEL = "ITM Barrier Trials \u2013 Leopardstown, 26 August"


def _log(msg):
    print(msg, flush=True)


def _norm(name: str) -> str:
    """Normalise a horse name for exact matching (case/punctuation-insensitive)."""
    s = name.strip().lower()
    s = re.sub(r"\(.*?\)", "", s)
    s = s.replace("&", " and ")
    s = re.sub(r"[^a-z0-9 ]", "", s)
    s = " ".join(s.split())
    return s


def _event_dt(event: dict):
    dt_str = event.get("eventDateTime", "") or ""
    if not dt_str:
        return None
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt.astimezone()
    except (ValueError, TypeError):
        return None


def _race_day(event: dict):
    dt = _event_dt(event)
    return dt.date() if dt else None


def _race_date(event: dict, fallback: str) -> str:
    dt = _event_dt(event)
    return dt.strftime("%a %d %b %Y") if dt else fallback


def load_horses(path: str) -> dict:
    horses = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            name = (row.get("horse") or "").strip()
            if not name:
                continue
            horses[_norm(name)] = {
                "name": name,
                "batch": (row.get("batch") or "").strip(),
                "position": (row.get("position") or "").strip(),
            }
    return horses


def scan(countries, target_day, workers):
    """Return a list of hit dicts (barrier-trial horses declared to run)."""
    horses = load_horses(HORSES_FILE)
    _log(f"Watching for {len(horses)} barrier-trial horses.")

    client = LadsClient()
    today = date.today()
    events = client.get_all_real_events()
    country_set = {c.upper() for c in countries}

    todays = []
    for e in events:
        time_str, track, _ = parse_event_name(e.get("eventName", ""))
        if not time_str:
            continue
        if detect_country(e) not in country_set:
            continue
        rday = _race_day(e)
        if rday is not None and rday < today:
            continue
        if target_day is not None and rday is not None and rday != target_day:
            continue
        todays.append((e, time_str, track))

    _log(f"Races to scan: {len(todays)}")
    event_by_id = {e.get("key"): (e, t, trk) for (e, t, trk) in todays}
    runners_by_id = client.get_runners_bulk(
        list(event_by_id.keys()), max_workers=workers)

    hits = []
    today_str = datetime.now().strftime("%a %d %b %Y")
    for eid, runners in runners_by_id.items():
        e, time_str, track = event_by_id[eid]
        race_date = _race_date(e, today_str)
        sort_day = _race_day(e) or date.max
        for r in runners:
            key = _norm(r["name"])
            if key in horses:
                info = horses[key]
                hits.append({
                    "horse": info["name"],
                    "trial_batch": info["batch"],
                    "trial_pos": info["position"],
                    "racecard_name": r["name"],
                    "date": race_date,
                    "_sort_day": sort_day,
                    "time": time_str,
                    "course": track,
                    "country": detect_country(e),
                    "price": r.get("price_decimal") or "",
                    "non_runner": bool(r.get("is_nr")),
                })
    hits.sort(key=lambda h: (h["_sort_day"], h["time"], h["course"]))
    return hits


def build_html(hits, countries, day_label):
    """Return the full index.html string."""
    esc = html.escape
    now_uk = datetime.now(UK_TZ)
    # e.g. "Tuesday 06 October 2026, 21:49 BST"
    generated = now_uk.strftime("%A %d %B %Y, %H:%M %Z")
    def row_html(h):
        nr = " <span class='nr'>NON-RUNNER</span>" if h["non_runner"] else ""
        price = esc(str(h["price"])) if h["price"] else "&ndash;"
        return (
            "<tr>"
            f"<td class='t'>{esc(h['time'])}</td>"
            f"<td class='course'>{esc(h['course'])} <span class='ctry'>{esc(h['country'])}</span></td>"
            f"<td class='horse'>{esc(h['horse'])}{nr}</td>"
            f"<td class='t'>Batch {esc(h['trial_batch'])}, pos {esc(h['trial_pos'])}</td>"
            f"<td class='num'>{price}</td>"
            "</tr>\n"
        )

    if hits:
        # Group hits by race day, preserving the chronological sort order.
        groups = []  # list of (date_label, [hits])
        for h in hits:
            if groups and groups[-1][0] == h["date"]:
                groups[-1][1].append(h)
            else:
                groups.append((h["date"], [h]))

        blocks = ""
        for date_label, day_hits in groups:
            rows = "".join(row_html(h) for h in day_hits)
            blocks += (
                f"<h2 class='day'>{esc(date_label)} "
                f"<span class='daycount'>{len(day_hits)} horse"
                f"{'s' if len(day_hits) != 1 else ''}</span></h2>"
                "<table><thead><tr>"
                "<th>Time</th><th>Course</th><th>Horse</th>"
                "<th>Trial</th><th>Price</th></tr></thead>"
                f"<tbody>{rows}</tbody></table>"
            )

        body = (
            f"<p class='count'>&#11088; {len(hits)} barrier-trial horse(s) "
            f"declared to run ({esc(day_label)})</p>"
            + blocks
        )
    else:
        body = (f"<p class='none'>No barrier-trial horses are declared to run "
                f"({esc(day_label)}) in {esc('/'.join(countries))}.</p>")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Barrier Trial Watch</title>
<style>
  :root {{ --blue:#4ec3ff; --ink:#1b2733; --muted:#64748b; --line:#e2e8f0; --bg:#f1f5f9; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,
         Helvetica,Arial,sans-serif; background:var(--bg); color:var(--ink); }}
  header {{ background:var(--blue); color:#063047; padding:18px 20px; }}
  header h1 {{ margin:0; font-size:22px; }}
  header p {{ margin:4px 0 0; font-size:13px; color:#0a3f5c; }}
  main {{ padding:16px 20px 40px; }}
  .count {{ font-size:16px; font-weight:700; margin:6px 0 14px; }}
  h2.day {{ font-size:15px; margin:22px 0 8px; color:#063047;
            border-bottom:2px solid var(--blue); padding-bottom:6px; }}
  h2.day .daycount {{ font-weight:400; color:var(--muted); font-size:13px; }}
  .none {{ font-size:16px; color:var(--muted); background:#fff; border:1px solid var(--line);
          border-radius:10px; padding:18px; }}
  table {{ width:100%; border-collapse:collapse; background:#fff;
          border:1px solid var(--line); border-radius:10px; overflow:hidden; }}
  th,td {{ text-align:left; padding:10px 12px; font-size:14px; border-bottom:1px solid var(--line); }}
  th {{ background:#f8fafc; color:var(--muted); font-weight:600; }}
  tr:last-child td {{ border-bottom:none; }}
  td.horse {{ font-weight:700; }}
  td.course {{ font-weight:600; }}
  .ctry {{ color:var(--muted); font-size:11px; font-weight:400; }}
  .num {{ text-align:left; font-variant-numeric:tabular-nums; }}
  .nr {{ color:#b91c1c; font-size:11px; font-weight:700; margin-left:6px; }}
  footer {{ padding:0 20px 30px; font-size:12px; color:var(--muted); }}
</style>
</head>
<body>
<header>
  <h1>Barrier Trial Watch</h1>
  <p>{esc(TRIAL_LABEL)} &middot; horses declared to run under rules</p>
</header>
<main>
  {body}
</main>
<footer>
  Updated {esc(generated)} &middot; scanning {esc('/'.join(countries))} &middot;
  prices &amp; cards from the Ladbrokes feed. Matching is by exact horse name.
</footer>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description="Build the barrier-trial results page")
    parser.add_argument("--countries", default=",".join(DEFAULT_COUNTRIES))
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--day", default="today",
                        help="'today' (default), 'tomorrow', 'all', or YYYY-MM-DD")
    parser.add_argument("--output", default="index.html")
    args = parser.parse_args()

    countries = tuple(c.strip().upper() for c in args.countries.split(",") if c.strip())

    day_arg = args.day.strip().lower()
    if day_arg == "today":
        target_day = date.today()
    elif day_arg == "tomorrow":
        target_day = date.today() + timedelta(days=1)
    elif day_arg == "all":
        target_day = None
    else:
        try:
            target_day = date.fromisoformat(args.day.strip())
        except ValueError:
            raise SystemExit(f"--day must be today/tomorrow/all/YYYY-MM-DD (got '{args.day}')")

    day_label = ("today onwards" if target_day is None
                 else target_day.strftime("%a %d %b %Y"))

    hits = scan(countries, target_day, args.workers)

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(build_html(hits, countries, day_label))
    _log(f"Wrote {args.output} with {len(hits)} hit(s).")


if __name__ == "__main__":
    main()
