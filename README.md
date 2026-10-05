# John Summit GA ticket price tracker 🎟️

Checks the resale sites for **John Summit – CTRL ESCAPE Arena Tour, TD Garden
(Boston), Thu Oct 29, 2026** and sends a notification to your phone when the
cheapest **GA (general admission)** ticket gets cheaper.

Sites checked: **StubHub, Vivid Seats, SeatGeek, Ticketmaster (incl. resale),
Gametime, TickPick**. You can add more in `config.yaml`.

## What you'll get

- **An email the moment the cheapest GA ticket hits $500 or less** (per
  ticket, fees included), with a link straight to the listing.
- **After that, an email every time the price changes:** "dropped to $480 (was
  $499)", "went up to $510 (was $480)", and so on, even if it goes back above
  $500.

Nothing is sent before it first reaches $500. Change the price with
`target_price` in `config.yaml`. If the emails get too frequent, raise
`min_drop_dollars` (e.g. to 5) so tiny $1–2 wiggles are ignored.

It checks every ~30 minutes and stops by itself after the concert. Every check
is saved in `data/history.csv`, which you can open in Google Sheets to see how
prices moved.

---

## Setup: email alerts (about 5 minutes)

The tracker sends the email **from a Gmail account using an "app password"**.
This is a special password Google gives you just for this. It is not your
normal password. The best setup is to send from the same Gmail account that
receives the alerts, because Gmail never puts mail you sent to yourself in spam.

### 1. Make a Gmail app password

1. Sign in to the Gmail account that should **send** the alerts (ideally the
   same one that receives them).
2. Go to <https://myaccount.google.com/apppasswords>. If Google says app
   passwords aren't available, first turn on **2-Step Verification** at
   <https://myaccount.google.com/signinoptions/twosv>, then try again.
3. Type a name like `ticket tracker` and click **Create**.
4. Copy the 16-letter password it shows (e.g. `abcd efgh ijkl mnop`).

### 2. Add three secrets to GitHub

In this repo go to **Settings → Secrets and variables → Actions → New
repository secret** and add these three:

| Name            | Secret (value)                                |
|-----------------|-----------------------------------------------|
| `SMTP_USER`     | the Gmail address that sends (from step 1)    |
| `SMTP_PASSWORD` | the 16-letter app password                    |
| `EMAIL_TO`      | the address that should get the alerts        |

These are stored privately. Even though the repo is public, nobody can see
them, and they never show up in the code or the logs.

### 3. Send yourself a test email

**Actions** tab → **Track John Summit GA prices** (left side) → **Run
workflow** → tick **"Just send a test email"** → **Run workflow**.

Within ~1 minute you should get an email titled *"John Summit ticket tracker:
test email"*. **If it's in spam, open it and click "Report not spam".**
Gmail then remembers that this sender is OK. To be extra safe, open the email,
click the ⋮ menu → **Filter messages like this** → **Create filter** →
tick **Never send it to Spam**.

That's it. The tracker is already running every 30 minutes.

### Optional: phone push notifications

Install the free **ntfy** app, subscribe to a long random topic name, and add
it as a secret named `NTFY_TOPIC`. Alerts then also pop up on your phone.

---

## Running it on your own computer instead (often works better)

From GitHub's servers, **Gametime works** and Vivid Seats loads. **StubHub, SeatGeek,
Ticketmaster and TickPick block GitHub's servers** (they return "403 blocked").
Those sites usually allow normal home internet, so running the tracker on your
own computer while it's on lets it check them too. You need [Python 3.10+](https://www.python.org/downloads/).

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
