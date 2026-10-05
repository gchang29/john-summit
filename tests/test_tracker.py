from pathlib import Path

import pytest

from tracker.core import BLOCKED, NO_GA, OK, SiteResult, evaluate
from tracker.extract import GAFilter, cheapest, listings_from_cards, listings_from_json, parse_prices

FLT = GAFilter(r"(?:general\s+admission|\bGA\b|\bG\.A\.)", r"(?:\bVIP\b|parking)", 20, 3000)
CFG = {"min_drop_dollars": 1, "target_price": None}


def test_parse_prices():
    assert parse_prices("Was $1,299.50 now $180") == [1299.5, 180.0]


def test_ga_filter():
    assert FLT.is_ga("GA Floor")
    assert FLT.is_ga("General Admission Standing")
    assert FLT.is_ga("FLOOR GA")
    assert not FLT.is_ga("VIP GA Early Entry")
    assert not FLT.is_ga("Section 101 Garage")  # "ga" inside a word is not GA
    assert not FLT.is_ga("Loge 12")


def test_cards_take_lowest_shown_price_and_skip_non_ga():
    cards = ["GA Floor\n$199.00 $176.40\nincl. fees", "Section 101\n$90", "VIP GA\n$50", "GA\n$5 off"]
    got = listings_from_cards(cards, FLT)
    assert [l.price for l in got] == [176.40]


def test_json_listings_and_cents():
    data = {"a": [{"zone": {"name": "General Admission"}, "price": {"total": 15500}},
                  {"zone": "Upper Level", "price": {"total": 4000}}]}
    got = listings_from_json([data], FLT, in_cents=True)
    assert [l.price for l in got] == [155.0]


def test_page_prices_preferred_over_data():
    from tracker.extract import Listing
    best = cheapest([Listing(150, "x", "data"), Listing(170, "y", "page")])
    assert best.price == 170


def _run(state, *prices, statuses=None):
    results = []
    for i, p in enumerate(prices):
        status = (statuses or {}).get(i, OK if p is not None else NO_GA)
        results.append(SiteResult(f"s{i}", f"Site{i}", status, f"https://x/{i}", p if status == OK else None))
    return evaluate(state, results, CFG, "2026-10-01T00:00:00+00:00")


def test_first_run_sends_status_then_only_drops():
    state = {}
    first = _run(state, 200, 180)
    assert len(first) == 1 and "running" in first[0].title and "$180" in first[0].body
    assert _run(state, 200, 180) == []          # no change -> no alert
    assert _run(state, 205, 185) == []          # went up -> no alert
    drop = _run(state, 205, 170)
    assert len(drop) == 1 and "$170" in drop[0].title and "was $185" in drop[0].body
    assert "all-time low" in drop[0].body


def test_blocked_site_keeps_last_price_no_false_alert():
    state = {}
    _run(state, 200, 150)
    assert _run(state, 200, None, statuses={1: BLOCKED}) == []
    assert _run(state, 200, 150) == []          # back to same price: not a "drop"


def test_failure_heads_up_once():
    state = {}
    _run(state, 200, 150)
    alerts = [a for _ in range(10) for a in _run(state, 200, None, statuses={1: BLOCKED})]
    assert len(alerts) == 1 and "can't read" in alerts[0].title


def test_target_price_alert():
    state = {}
    cfg = {"min_drop_dollars": 1, "target_price": 500, "alert_on_every_drop": False}
    run = lambda p: evaluate(state, [SiteResult("a", "Gametime", OK, "https://g", p)], cfg, "t")
    assert "running" in run(538)[0].title       # first check: status message
    assert run(520) == []                        # drop above target: silent in target-only mode
    hit = run(499)
    assert len(hit) == 1 and hit[0].urgent and "$499" in hit[0].title and "https://g" in hit[0].body
    assert run(499) == [] and run(499.5) == []   # no repeats at the same price
    assert "$480" in run(480)[0].title           # even lower -> alert again
    assert run(560) == []                        # back above target -> re-armed, silent
    assert "$495" in run(495)[0].title           # under again -> alert


def test_target_already_met_on_first_check():
    state = {}
    cfg = {"min_drop_dollars": 1, "target_price": 500, "alert_on_every_drop": False}
    alerts = evaluate(state, [SiteResult("a", "A", OK, "u", 450)], cfg, "t")
    assert len(alerts) == 1 and alerts[0].urgent and "$450" in alerts[0].title


def test_no_ga_check_does_not_trigger_target_again():
    state = {}
    cfg = {"min_drop_dollars": 1, "target_price": 500, "alert_on_every_drop": False}
    evaluate(state, [SiteResult("a", "A", OK, "u", 450)], cfg, "t")
    evaluate(state, [SiteResult("a", "A", NO_GA, "u", None)], cfg, "t")
    assert evaluate(state, [SiteResult("a", "A", OK, "u", 450)], cfg, "t") == []


def test_browser_finds_ga_cards():
    pytest.importorskip("playwright")
    from tracker.browser import Browser
    url = (Path(__file__).parent / "fixtures" / "fake_listings.html").resolve().as_uri()
    try:
        with Browser() as b:
            page = b.fetch(url, FLT.ga.pattern, scrolls=1)
    except Exception as exc:  # no Chromium installed
        pytest.skip(f"browser unavailable: {exc}")
    cards = listings_from_cards(page.cards, FLT)
    assert sorted(l.price for l in cards) == [176.40, 181.0]
    data = listings_from_json(page.json_payloads, FLT)
    assert [l.price for l in data] == [170.5]
    assert cheapest(cards + data).price == 176.40
