"""Loads ticket pages in a real (headless) Chrome so JavaScript-heavy sites work."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
)

# Finds the smallest page elements whose visible text contains both a GA word
# and a "$" price -- i.e. individual listing cards.
CARDS_JS = """
(gaPattern) => {
  const ga = new RegExp(gaPattern, 'i');
  const price = /\\$\\s?\\d/;
  const matched = [];
  const hasMatchedChild = new Set();
  for (const el of document.body.querySelectorAll('*')) {
    if (['SCRIPT', 'STYLE', 'NOSCRIPT'].includes(el.tagName)) continue;
    const text = el.innerText || '';
    if (text.length > 600 || !price.test(text) || !ga.test(text)) continue;
    matched.push(el);
  }
  for (const el of matched) {
    let p = el.parentElement;
    while (p) { hasMatchedChild.add(p); p = p.parentElement; }
  }
  return matched.filter(el => !hasMatchedChild.has(el)).map(el => el.innerText);
}
"""

LINKS_JS = "() => Array.from(document.querySelectorAll('a[href]')).map(a => a.href)"


@dataclass
class PageResult:
    url: str
    status: int | None
    text: str = ""
    cards: list[str] = field(default_factory=list)
    json_payloads: list = field(default_factory=list)
    links: list[str] = field(default_factory=list)


class Browser:
    def __init__(self, headless: bool = True):
        self.headless = headless

    def __enter__(self):
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            headless=self.headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        self._context = self._browser.new_context(
            user_agent=USER_AGENT,
            locale="en-US",
            timezone_id="America/New_York",
            viewport={"width": 1366, "height": 900},
        )
        self._context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        return self

    def __exit__(self, *exc):
        self._context.close()
        self._browser.close()
        self._pw.stop()

    def fetch(self, url: str, ga_pattern: str, scrolls: int = 6) -> PageResult:
        page = self._context.new_page()
        payloads: list = []

        def on_response(response):
            ctype = response.headers.get("content-type", "")
            if "json" not in ctype:
                return
            try:
                payloads.append(response.json())
            except Exception:
                pass

        page.on("response", on_response)
        try:
            response = page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            result = PageResult(url=page.url, status=response.status if response else None)
            try:
                page.wait_for_load_state("networkidle", timeout=20_000)
            except PlaywrightError:
                pass  # some sites never go fully idle; that's fine
            # Scroll so lazy-loaded listings appear.
            for _ in range(scrolls):
                page.mouse.wheel(0, 1400)
                page.wait_for_timeout(random.randint(900, 1600))
            page.wait_for_timeout(1500)

            result.text = page.inner_text("body")
            result.cards = page.evaluate(CARDS_JS, ga_pattern)
            result.links = page.evaluate(LINKS_JS)
            # Data embedded in the page itself (e.g. Next.js __NEXT_DATA__).
            for raw in page.eval_on_selector_all(
                "script[type='application/json'], script[type='application/ld+json']",
                "els => els.map(e => e.textContent)",
            ):
                try:
                    payloads.append(json.loads(raw))
                except (ValueError, TypeError):
                    pass
            result.json_payloads = payloads
            return result
        finally:
            page.close()
