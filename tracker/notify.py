"""Sends alerts. Configure any of these with environment variables / GitHub secrets:

- NTFY_TOPIC            phone push notifications via the free ntfy app (easiest)
- DISCORD_WEBHOOK_URL   a Discord channel webhook
- SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, EMAIL_TO   email (e.g. Gmail app password)
"""

from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage

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
    host, to = os.environ.get("SMTP_HOST"), os.environ.get("EMAIL_TO")
    if not (host and to):
        return False
    msg = EmailMessage()
    msg["Subject"] = title
    msg["From"] = os.environ.get("SMTP_USER", to)
    msg["To"] = to
    msg.set_content(body + (f"\n\n{click_url}" if click_url else ""))
    with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT", "587")), timeout=30) as smtp:
        smtp.starttls()
        if os.environ.get("SMTP_USER"):
            smtp.login(os.environ["SMTP_USER"], os.environ.get("SMTP_PASSWORD", ""))
        smtp.send_message(msg)
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
