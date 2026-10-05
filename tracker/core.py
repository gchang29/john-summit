"""Decides when to alert. Kept free of browser code so it can be unit-tested."""

from __future__ import annotations

from dataclasses import dataclass

OK, NO_GA, BLOCKED, ERROR = "ok", "no_ga_listings", "blocked", "error"

# Tell the user once when a site has failed this many checks in a row.
FAILURE_ALERT_AFTER = 6


@dataclass
class SiteResult:
    key: str
    name: str
    status: str
    url: str | None = None
    price: float | None = None
    description: str = ""
    note: str = ""


@dataclass
class Alert:
    title: str
    body: str
    click_url: str | None = None
    urgent: bool = False


def _money(x: float) -> str:
    return f"${x:,.0f}" if float(x).is_integer() else f"${x:,.2f}"


def _cheapest(sites_state: dict) -> tuple[float, str] | None:
    known = [(s["last_price"], key) for key, s in sites_state.items() if s.get("last_price") is not None]
    return min(known) if known else None


def evaluate(state: dict, results: list[SiteResult], cfg: dict, now_iso: str) -> list[Alert]:
    """Update `state` in place with this run's results and return alerts to send."""
    sites_state = state.setdefault("sites", {})
    min_drop = float(cfg.get("min_drop_dollars", 1))
    target = cfg.get("target_price")
    first_run = not state.get("initialized")
    prev_cheapest = _cheapest(sites_state)

    drops: list[str] = []
    alerts: list[Alert] = []
    for r in results:
        s = sites_state.setdefault(r.key, {})
        s["name"] = r.name
        if r.url:
            s["url"] = r.url
        s["last_status"] = r.status
        s["last_checked"] = now_iso
        if r.status in (OK, NO_GA):
            s["consecutive_failures"] = 0
            s["failure_alerted"] = False
            prev = s.get("last_price")
            s["last_price"] = r.price  # None means no GA tickets listed right now
            if r.price is not None:
                s["last_ok"] = now_iso
                if s.get("lowest_price") is None or r.price < s["lowest_price"]:
                    s["lowest_price"] = r.price
                if prev is not None and r.price <= prev - min_drop:
                    drops.append(f"{r.name}: {_money(r.price)} (was {_money(prev)}, down {_money(prev - r.price)})")
        else:
            s["consecutive_failures"] = s.get("consecutive_failures", 0) + 1
            if s["consecutive_failures"] >= FAILURE_ALERT_AFTER and not s.get("failure_alerted"):
                s["failure_alerted"] = True
                alerts.append(Alert(
                    title=f"Heads up: can't read {r.name}",
                    body=(f"{r.name} has failed {s['consecutive_failures']} checks in a row "
                          f"({r.status}: {r.note or 'no details'}). Other sites are still being tracked."),
                    click_url=r.url,
                ))

    cheapest = _cheapest(sites_state)
    lines = []
    for key, s in sorted(sites_state.items(), key=lambda kv: (kv[1].get("last_price") is None, kv[1].get("last_price") or 0)):
        if s.get("last_price") is not None:
            lines.append(f"  {s.get('name', key)}: {_money(s['last_price'])}")
        else:
            lines.append(f"  {s.get('name', key)}: {'no GA listings' if s.get('last_status') == NO_GA else 'unavailable'}")
    summary = "Current cheapest GA per ticket:\n" + "\n".join(lines)

    if cheapest is None:
        if first_run and results:
            state["initialized"] = True
            alerts.append(Alert("John Summit GA tracker is running",
                                "Couldn't read a GA price yet on any site. I'll keep checking.\n\n" + summary))
        return alerts

    price, key = cheapest
    click = sites_state[key].get("url")
    best = state.get("best_ever")
    new_low = best is None or price < best["price"]
    if new_low:
        state["best_ever"] = {"price": price, "site": sites_state[key].get("name", key), "at": now_iso}

    every_drop = cfg.get("alert_on_every_drop", True)
    reasons = list(drops) if every_drop else []
    if every_drop and prev_cheapest is not None and price <= prev_cheapest[0] - min_drop and not drops:
        reasons.append(f"Cheapest GA overall dropped to {_money(price)} on {sites_state[key]['name']} "
                       f"(was {_money(prev_cheapest[0])})")

    target_news = False
    if target is not None:
        last_target_alert = state.get("target_alerted_price")
        if price <= float(target):
            target_news = last_target_alert is None or price <= last_target_alert - min_drop
            if target_news:
                state["target_alerted_price"] = price
        else:
            state["target_alerted_price"] = None  # back above target: re-arm the alert

    name = sites_state[key].get("name", key)
    if target_news:
        body = f"Cheapest GA ticket is {_money(price)} per ticket on {name} (your target: {_money(float(target))})."
        if reasons:
            body += "\n\n" + "\n".join(reasons)
        body += f"\n\n{summary}\n\nBuy here: {click}"
        state["initialized"] = True
        alerts.append(Alert(f"John Summit GA tickets are {_money(price)} on {name}", body,
                            click_url=click, urgent=True))
    elif first_run:
        state["initialized"] = True
        alerts.append(Alert("John Summit GA tracker is running",
                            f"Cheapest GA right now: {_money(price)} on {name}.\n\n{summary}",
                            click_url=click))
    elif reasons:
        body = "\n".join(reasons)
        if new_low:
            body += f"\nNew all-time low: {_money(price)} on {name}"
        body += f"\n\n{summary}"
        alerts.append(Alert(f"John Summit GA price drop: {_money(price)}", body.strip(), click_url=click))
    return alerts
