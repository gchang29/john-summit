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

    # Target mode: stay quiet until the cheapest GA first reaches the target,
    # then email on every change after that (down or up, even back above it).
    name = sites_state[key].get("name", key)
    target_news = False
    target_title = lead = ""
    if target is not None:
        target = float(target)
        last_sent = state.get("last_emailed_price")
        if not state.get("target_reached"):
            if price <= target:
                state["target_reached"] = True
                target_news = True
                target_title = f"John Summit GA tickets hit {_money(price)} on {name}"
                lead = f"The cheapest GA ticket is now {_money(price)} per ticket on {name} (your target: {_money(target)})."
        elif last_sent is None or abs(price - last_sent) >= min_drop:
            target_news = True
            if last_sent is None:
                target_title = f"John Summit GA tickets: {_money(price)} on {name}"
                lead = f"The cheapest GA ticket is {_money(price)} per ticket on {name}."
            else:
                went = "dropped" if price < last_sent else "went up"
                target_title = f"John Summit GA {went} to {_money(price)} on {name}"
                lead = (f"The cheapest GA ticket {went} to {_money(price)} per ticket on {name} "
                        f"(was {_money(last_sent)}, {'down' if price < last_sent else 'up'} "
                        f"{_money(abs(price - last_sent))}).")
        if target_news:
            state["last_emailed_price"] = price

    if target_news:
        body = lead
        if new_low:
            body += "\nThat's the lowest price seen so far."
        body += f"\n\n{summary}\n\nBuy here: {click}"
        state["initialized"] = True
        alerts.append(Alert(target_title, body, click_url=click,
                            urgent=price <= float(target)))
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
