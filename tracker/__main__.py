"""Check every ticket site once (or on a loop) and alert on GA price drops.

    python -m tracker                 # one check of every site
    python -m tracker --loop 15       # keep checking every 15 minutes
    python -m tracker --test-notify   # just send a test notification
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import yaml

from . import notify
from .core import BLOCKED, ERROR, NO_GA, OK, SiteResult, evaluate
from .extract import GAFilter, cheapest, listings_from_cards, listings_from_json, looks_blocked

ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = ROOT / "data" / "state.json"
HISTORY_FILE = ROOT / "data" / "history.csv"


def load_config(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def append_history(results: list[SiteResult], now_iso: str) -> None:
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    new = not HISTORY_FILE.exists()
    with open(HISTORY_FILE, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["checked_at", "site", "status", "cheapest_ga_price", "listing", "url"])
        for r in results:
            w.writerow([now_iso, r.name, r.status, "" if r.price is None else r.price, r.description, r.url or ""])


def with_quantity(url: str, quantity: int) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    query["quantity"] = str(quantity)
    return urlunsplit(parts._replace(query=urlencode(query)))


def discover_url(browser, key: str, site: dict, cfg: dict, state: dict) -> tuple[str | None, str]:
    cached = state.get("sites", {}).get(key, {}).get("url")
    if cached:
        return cached, ""
    page = browser.fetch(site["discover_from"], cfg["ga_pattern"], scrolls=2)
    if looks_blocked(page.status, page.text):
        return None, f"blocked while looking for the event page (HTTP {page.status})"
    pattern = re.compile(site["discover_match"])
    for link in page.links:
        if pattern.search(link):
            return link.split("?")[0].split("#")[0], ""
    return None, "couldn't find the Boston event link on " + site["discover_from"]


def check_site(browser, key: str, site: dict, cfg: dict, state: dict, flt: GAFilter) -> SiteResult:
    name = site.get("name", key)
    url = site.get("url")
    if not url:
        url, note = discover_url(browser, key, site, cfg, state)
        if not url:
            return SiteResult(key, name, BLOCKED if "blocked" in note else ERROR, note=note)

    page = browser.fetch(with_quantity(url, cfg.get("quantity", 1)), cfg["ga_pattern"])
    listings = listings_from_cards(page.cards, flt) + listings_from_json(
        page.json_payloads, flt, in_cents=bool(site.get("json_price_in_cents")))
    best = cheapest(listings)
    if best:
        return SiteResult(key, name, OK, url, best.price, best.description)
    if looks_blocked(page.status, page.text):
        return SiteResult(key, name, BLOCKED, url, note=f"bot protection page (HTTP {page.status})")
    if page.status and page.status >= 400:
        return SiteResult(key, name, ERROR, url, note=f"HTTP {page.status}")
    return SiteResult(key, name, NO_GA, url, note="page loaded but no GA listings found")


def run_once(cfg: dict, only: set[str] | None, send_alerts: bool, headed: bool) -> None:
    from .browser import Browser  # imported here so --test-notify works without Playwright

    state = load_state()
    flt = GAFilter(cfg["ga_pattern"], cfg.get("exclude_pattern"),
                   cfg.get("min_plausible_price", 20), cfg.get("max_plausible_price", 3000))
    sites = {k: v for k, v in cfg["sites"].items() if v.get("enabled", True) and (not only or k in only)}
    now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    results = []
    with Browser(headless=not headed) as browser:
        for key, site in sites.items():
            print(f"Checking {site.get('name', key)} ...", flush=True)
            try:
                result = check_site(browser, key, site, cfg, state, flt)
            except Exception as exc:
                result = SiteResult(key, site.get("name", key), ERROR, site.get("url"),
                                    note=f"{type(exc).__name__}: {str(exc).splitlines()[0][:200]}")
            price = f"${result.price:,.2f}" if result.price is not None else "-"
            print(f"  {result.status:15} {price:>10}  {result.description or result.note}")
            results.append(result)
            time.sleep(random.uniform(2, 5))

    for alert in evaluate(state, results, cfg, now_iso):
        print(f"\nALERT: {alert.title}\n{alert.body}\n")
        if send_alerts:
            notify.send(alert.title, alert.body, alert.click_url, alert.urgent)
    save_state(state)
    append_history(results, now_iso)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(ROOT / "config.yaml"))
    ap.add_argument("--loop", type=float, metavar="MINUTES", help="keep running, checking every N minutes")
    ap.add_argument("--sites", help="comma-separated site keys to check (default: all)")
    ap.add_argument("--no-notify", action="store_true", help="print alerts instead of sending them")
    ap.add_argument("--headed", action="store_true", help="show the browser window (useful for debugging)")
    ap.add_argument("--test-notify", action="store_true", help="send a test notification and exit")
    args = ap.parse_args(argv)

    cfg = load_config(Path(args.config))
    if args.test_notify:
        ok = notify.send("John Summit tracker test", "If you can read this, alerts are working.")
        return 0 if ok else 1

    event_day = date.fromisoformat(str(cfg["event"]["date"]))
    only = set(args.sites.split(",")) if args.sites else None
    while True:
        if date.today() > event_day + timedelta(days=1):
            print("The concert is over -- nothing left to track.")
            return 0
        run_once(cfg, only, send_alerts=not args.no_notify, headed=args.headed)
        if not args.loop:
            return 0
        wait = args.loop * 60 * random.uniform(0.85, 1.15)
        print(f"\nNext check in {wait / 60:.0f} minutes (Ctrl+C to stop).\n")
        time.sleep(wait)


if __name__ == "__main__":
    sys.exit(main())
