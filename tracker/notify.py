"""Sends alerts. Configure any of these with environment variables / GitHub secrets:

- NTFY_TOPIC            phone push notifications via the free ntfy app (easiest)
- DISCORD_WEBHOOK_URL   a Discord channel webhook
- SMTP_USER + SMTP_PASSWORD   email, sent from that account (a Gmail address + Gmail
  app password). EMAIL_TO = who receives it (defaults to SMTP_USER).
  SMTP_HOST / SMTP_PORT default to Gmail (smtp.gmail.com:587).
"""

from __future__ import annotations

import html
import os
import smtplib
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

import requests


def _ntfy(title: str, body: str, click_url: str | None, urgent: bool) -> bool:
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        return False
    server = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
    headers = {
        # HTTP headers must be latin-1; keep emoji out of the title.
        "Title": title.encode("ascii", "ignore").decode(),
        "Priority": "urgent" if urgent else "high",
        "Tags": "ticket,money_with_wings",
    }
    if click_url:
        headers["Click"] = click_url
    requests.post(f"{server}/{topic}", data=body.encode("utf-8"), headers=headers, timeout=20).raise_for_status()
    return True


def _discord(title: str, body: str, click_url: str | None, urgent: bool) -> bool:
    url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not url:
        return False
    content = f"**{title}**\n{body}"
    if click_url:
        content += f"\n{click_url}"
    if urgent:
        content = "@everyone " + content
    requests.post(url, json={"content": content[:1990]}, timeout=20).raise_for_status()
    return True


def _email(title: str, body: str, click_url: str | None, urgent: bool) -> bool:
    user, password = os.environ.get("SMTP_USER"), os.environ.get("SMTP_PASSWORD")
    if not (user and password):
        return False
    to = os.environ.get("EMAIL_TO") or user
    sender = formataddr(("John Summit Ticket Tracker", user))
    msg = EmailMessage()
    msg["Subject"] = title
    msg["From"] = sender
    msg["To"] = to
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=user.split("@")[-1])
    text = body + (f"\n\n{click_url}" if click_url and click_url not in body else "")
    msg.set_content(text)
    html_body = html.escape(text).replace("\n", "<br>")
    if click_url:
        html_body += f'<p><a href="{html.escape(click_url)}">Open the listing</a></p>'
    msg.add_alternative(f"<html><body style='font-family:sans-serif'>{html_body}</body></html>", subtype="html")

    host = os.environ.get("SMTP_HOST") or "smtp.gmail.com"
    port = int(os.environ.get("SMTP_PORT") or 587)
    with smtplib.SMTP(host, port, timeout=30) as smtp:
        smtp.starttls()
        # Gmail app passwords are shown with spaces; they work without them.
        smtp.login(user, password.replace(" ", ""))
        smtp.send_message(msg)
    print("  email sent")  # (no address: Actions logs are public)
    return True


def send(title: str, body: str, click_url: str | None = None, urgent: bool = False) -> bool:
    """Send through every configured channel. Returns True if at least one worked."""
    sent = False
    for channel in (_ntfy, _discord, _email):
        try:
            sent = channel(title, body, click_url, urgent) or sent
        except Exception as exc:  # one broken channel shouldn't stop the others
            print(f"  ! {channel.__name__[1:]} notification failed: {exc}")
    if not sent:
        print("  (no notification channel configured -- set NTFY_TOPIC etc.)")
    return sent
