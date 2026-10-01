# John Summit GA ticket price tracker 🎟️

Checks the resale sites for **John Summit – CTRL ESCAPE Arena Tour, TD Garden
(Boston), Thu Oct 29, 2026** and sends a notification to your phone when the
cheapest **GA (general admission)** ticket gets cheaper.

Sites checked: **StubHub, Vivid Seats, SeatGeek, Ticketmaster (incl. resale),
Gametime, TickPick**. You can add more in `config.yaml`.

## What you'll get

- When it starts: one message listing the cheapest GA price on every site.
- After that, only when something gets cheaper, e.g.

  > **John Summit GA price drop: $142**
  > StubHub: $142 (was $158, down $16)
  > New all-time low: $142 on StubHub
  > Current cheapest GA per ticket: StubHub $142 · Gametime $149 · Vivid Seats $155 …

  Tapping the notification opens the cheapest site.
- Optional **"BUY NOW?"** alert when GA reaches a price you set (`target_price`
  in `config.yaml`).
- A one-time heads-up if a site keeps blocking the tracker.
- It stops by itself after the concert.

A record of every check is saved in `data/history.csv`. You can open it in
Excel or Google Sheets to see how prices changed.

---

## Setup (about 10 minutes, no coding)

### 1. Get phone notifications (ntfy, free, no account)

1. Install the **ntfy** app ([iPhone](https://apps.apple.com/app/ntfy/id1625396347) /
   [Android](https://play.google.com/store/apps/details?id=io.heckel.ntfy)).
2. Tap **+** and subscribe to a topic with a long random name nobody would guess,
   e.g. `john-summit-ga-7f3k29xq`. (Anyone who knows the name can read it.)

### 2. Give the tracker your topic name

In this GitHub repo: **Settings → Secrets and variables → Actions → New
repository secret**

- Name: `NTFY_TOPIC`
- Secret: your topic name, e.g. `john-summit-ga-7f3k29xq`

(Optional extras: `DISCORD_WEBHOOK_URL` for Discord, or `SMTP_HOST`,
`SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_TO` for email.)

### 3. Turn it on

The schedule lives in `.github/workflows/track-prices.yml`. GitHub only runs
scheduled jobs from the repo's **default branch** (`main`), so this code needs
to be on `main`.

Then go to the **Actions** tab → **Track John Summit GA prices** → **Run
workflow** to do the first check right away. You should get the "tracker is
running" notification within a few minutes. After that it runs by itself
every 30 minutes.

### ⚠️ Private repo? Watch your free minutes

This repo is private. GitHub gives free accounts **2,000 Actions minutes per
month** for private repos, and one check takes ~3–4 minutes. Every 30 minutes
would use them up in about 10 days, and then checks just stop (you won't be
charged unless you added a payment method with a spending limit). Either:

- **Make the repo public** (Settings → General → Danger Zone). Public repos get
  unlimited free minutes. Your notification topic stays secret because it's
  stored as a secret, not in the code. **Or**
- In `track-prices.yml`, change `"*/30 * * * *"` to `"0 */2 * * *"` (every 2 hours).

---

## Running it on your own computer instead (often works better)

Some ticket sites block traffic from cloud servers like GitHub's. If the
tracker keeps saying a site is "blocked", run it on your own computer. Your
home internet looks like a normal visitor. You need [Python 3.10+](https://www.python.org/downloads/).

```bash
pip install -r requirements.txt
python -m playwright install chromium

export NTFY_TOPIC=john-summit-ga-7f3k29xq     # Windows: set NTFY_TOPIC=...
python -m tracker --test-notify               # check that notifications work
python -m tracker --loop 15                   # check every ~15 min until you stop it
```

Other options: `--no-notify` (print only), `--sites stubhub,gametime` (check a
few sites), `--headed` (watch the browser click through).

---

## How it works

For each site, `tracker/` opens the event page in a real (headless) Chrome
browser, scrolls through the listings, and pulls out the GA tickets in two
ways:

1. **Visible listings.** It finds each listing on the page that mentions "GA" or
   "General Admission" along with a `$` price. This is what you'd see yourself.
2. **Background data.** It reads the listing data the page loads behind the
   scenes, as a backup.

It keeps the cheapest GA price per site in `data/state.json` and compares it
with the previous check. It alerts when the price drops by at least
`min_drop_dollars` (default $1).

What counts as GA is set by `ga_pattern` / `exclude_pattern` in
`config.yaml`. VIP, parking, and package listings are excluded by default.

## Good to know

- **Prices are per ticket and usually include fees.** Since 2025 US sites
  have to show the all-in price, but each site rounds and shows fees a bit
  differently. Check the final checkout price before you buy.
- **Ticketmaster, Gametime and TickPick** don't have a fixed link in the config.
  The tracker finds the Boston show from John Summit's page on each site the
  first time and remembers it. If it picks the wrong link, put the correct one
  as `url:` under that site in `config.yaml` and delete `data/state.json`.
- **Ticket sites change their pages and fight bots.** A site will sometimes
  come back as `blocked` or `no_ga_listings`. That's expected now and then.
  You'll get a heads-up if it keeps happening. Running locally (above) helps
  the most.
- To change how many tickets you're buying, set `quantity` in `config.yaml`.

## Tests

```bash
pip install pytest && python -m pytest
```
