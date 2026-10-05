"""Expiry alerts by email (Gmail SMTP). Standard library only."""
from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage

import pandas as pd


def when(days_left: int) -> str:
    if days_left < 0:
        n = -days_left
        return f"EXPIRED {n} day{'s' if n != 1 else ''} ago - check before eating"
    if days_left == 0:
        return "expires TODAY"
    if days_left == 1:
        return "expires tomorrow"
    return f"expires in {days_left} days"


def build_alert(active: pd.DataFrame, within_days: int = 2, recipes: list | None = None):
    """Return (subject, body) for items due within `within_days` (expired included), or None."""
    if active.empty:
        return None
    due = active[active["days_left"] <= within_days].sort_values("days_left")
    if due.empty:
        return None
    lines = [f"PantryPulse alert: {len(due)} item(s) need attention", ""]
    for r in due.itertuples():
        lines.append(f"- {r.name} ({r.quantity:g} {r.unit}): {when(int(r.days_left))}")
    rescue = [x["name"] for x in (recipes or []) if x.get("rescues")][:3]
    if rescue:
        lines += ["", "Cook this to rescue them: " + ", ".join(rescue)]
    lines += ["", "Use them first. Waste less, save money."]
    return f"PantryPulse: {len(due)} item(s) need attention", "\n".join(lines)


def send_email(subject: str, body: str, sender: str, app_password: str, recipient: str,
               host: str = "smtp.gmail.com", port: int = 465) -> None:
    if not sender or not app_password:
        raise ValueError("Email is not configured. Add EMAIL_SENDER and EMAIL_APP_PASSWORD to your secrets.")
    recipient = (recipient or "").strip()
    if "@" not in recipient or "." not in recipient.split("@")[-1]:
        raise ValueError("Please enter a valid recipient email address.")
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, sender, recipient
    msg.set_content(body)
    with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=20) as server:
        server.login(sender, app_password)
        server.send_message(msg)

