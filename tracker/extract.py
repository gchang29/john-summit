"""Turn a loaded ticket page into a list of GA listings with prices.

Two independent strategies are used, because every ticket site is built
differently and changes its layout often:

1. Page cards: small blocks of visible text that mention both "GA" and a "$"
   price (what you would see scrolling the listings yourself).
2. JSON data: the listing data the page downloads in the background, searched
   for objects that have a section/zone name and a price.

Card prices are preferred because they are exactly what the site displays.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

PRICE_RE = re.compile(r"\$\s?(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d{2}))?")

# JSON keys (lower-cased, without _ or -) that name where a ticket is.
SECTION_KEYS = {
    "section", "sectionname", "sectiondisplayname", "sectionmapname",
    "zone", "zonename", "area", "areaname", "tickettype", "tickettypename",
    "ticketclass", "ticketclassname", "category", "categoryname",
    "seatingarea", "level", "levelname",
}
# JSON keys that hold a per-ticket price, best (all-in) first.
PRICE_KEYS = [
    "allinprice", "priceincludingfees", "pricewithfees", "displayprice",
    "totalprice", "price", "rawprice", "listprice", "currentprice",
    "priceperticket", "amount", "value", "total", "prefee",
]
PRICE_KEY_SET = set(PRICE_KEYS)


@dataclass
class Listing:
    price: float
    description: str
    source: str  # "page" or "data"


def _norm_key(key: str) -> str:
    return key.lower().replace("_", "").replace("-", "")


def parse_prices(text: str) -> list[float]:
    prices = []
    for whole, cents in PRICE_RE.findall(text):
        prices.append(float(whole.replace(",", "")) + (float(cents) / 100 if cents else 0))
    return prices


class GAFilter:
    def __init__(self, ga_pattern: str, exclude_pattern: str | None,
                 min_price: float, max_price: float):
        self.ga = re.compile(ga_pattern, re.IGNORECASE)
        self.exclude = re.compile(exclude_pattern, re.IGNORECASE) if exclude_pattern else None
        self.min_price = min_price
        self.max_price = max_price

    def is_ga(self, text: str) -> bool:
        if not self.ga.search(text):
            return False
        return not (self.exclude and self.exclude.search(text))

    def plausible(self, price: float) -> bool:
        return self.min_price <= price <= self.max_price


def listings_from_cards(cards: list[str], flt: GAFilter) -> list[Listing]:
    """`cards` are visible text blocks that contain both a GA word and a price."""
    out = []
    for card in cards:
        text = " ".join(card.split())
        if not flt.is_ga(text):
            continue
        prices = [p for p in parse_prices(text) if flt.plausible(p)]
        if prices:
            # A card can show e.g. an old crossed-out price and the current one;
            # the lowest number is the one you would pay.
            out.append(Listing(min(prices), text[:160], "page"))
    return out


def _price_value(value, in_cents: bool, depth: int = 0) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return value / 100 if in_cents else float(value)
    if isinstance(value, str):
        cleaned = value.replace("$", "").replace(",", "").strip()
        try:
            num = float(cleaned)
        except ValueError:
            return None
        return num / 100 if in_cents and "." not in cleaned else num
    if isinstance(value, dict) and depth < 2:
        normed = {_norm_key(k): v for k, v in value.items()}
        for key in PRICE_KEYS:
            if key in normed:
                found = _price_value(normed[key], in_cents, depth + 1)
                if found is not None:
                    return found
    return None


def _section_text(obj: dict) -> str:
    parts = []
    for key, value in obj.items():
        if _norm_key(key) not in SECTION_KEYS:
            continue
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, dict):
            parts.extend(v for v in value.values() if isinstance(v, str))
    return " ".join(parts)


def listings_from_json(payloads: list, flt: GAFilter, in_cents: bool = False) -> list[Listing]:
    out: list[Listing] = []

    def walk(node, depth=0):
        if depth > 40:
            return
        if isinstance(node, dict):
            section = _section_text(node)
            if section and flt.is_ga(section):
                normed = {_norm_key(k): v for k, v in node.items()}
                for key in PRICE_KEYS:
                    if key in normed:
                        price = _price_value(normed[key], in_cents)
                        if price is not None and flt.plausible(price):
                            out.append(Listing(round(price, 2), section[:160], "data"))
                            break
            for value in node.values():
                walk(value, depth + 1)
        elif isinstance(node, list):
            for value in node:
                walk(value, depth + 1)

    for payload in payloads:
        walk(payload)
    return out


def cheapest(listings: list[Listing]) -> Listing | None:
    """Prefer prices read off the page; fall back to background data."""
    page = [l for l in listings if l.source == "page"]
    pool = page or listings
    return min(pool, key=lambda l: l.price) if pool else None


BLOCK_RE = re.compile(
    r"access denied|pardon our interruption|verify (?:that )?you are (?:a )?human|"
    r"are you a robot|captcha|unusual (?:traffic|activity)|request (?:was )?blocked|"
    r"press (?:&|and) hold",
    re.IGNORECASE,
)


def looks_blocked(status: int | None, text: str) -> bool:
    if status in (401, 403, 429):
        return True
    return bool(BLOCK_RE.search(text[:5000]))
