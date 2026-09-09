from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from typing import Protocol

import httpx

from flight_deals.models.domain import DealCandidate
from flight_deals.notifications.render import render_alert


class NotificationAdapter(Protocol):
    name: str

    async def send_deal_alert(self, candidate: DealCandidate) -> str:
        """Send a deal alert and return provider message id or status."""


class ConsoleEmailAdapter:
    name = "email"

    async def send_deal_alert(self, candidate: DealCandidate) -> str:
        subject, _html, text = render_alert(candidate)
        print(f"EMAIL SUBJECT: {subject}\n{text}")
        return "console-email"


class SmtpEmailAdapter:
    name = "email"

    async def send_deal_alert(self, candidate: DealCandidate) -> str:
        subject, html, text = render_alert(candidate)
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = os.environ["SMTP_FROM"]
        msg["To"] = os.environ["ALERT_EMAIL"]
        msg.set_content(text)
        msg.add_alternative(html, subtype="html")
        with smtplib.SMTP(
            os.environ["SMTP_HOST"], int(os.getenv("SMTP_PORT", "587")), timeout=20
        ) as smtp:
            smtp.starttls()
            if os.getenv("SMTP_USERNAME"):
                smtp.login(os.environ["SMTP_USERNAME"], os.environ["SMTP_PASSWORD"])
            smtp.send_message(msg)
        return "smtp-sent"


class ResendEmailAdapter:
    name = "email"

    async def send_deal_alert(self, candidate: DealCandidate) -> str:
        subject, html, text = render_alert(candidate)
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {os.environ['RESEND_API_KEY']}"},
                json={
                    "from": os.environ["RESEND_FROM"],
                    "to": [os.environ["ALERT_EMAIL"]],
                    "subject": subject,
                    "html": html,
                    "text": text,
                },
            )
            response.raise_for_status()
            return str(response.json().get("id", "resend-sent"))


class TelegramAdapter:
    name = "telegram"

    async def send_deal_alert(self, candidate: DealCandidate) -> str:
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        if not token or not chat_id:
            return "telegram-not-configured"
        subject, _html, text = render_alert(candidate)
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": f"{subject}\n\n{text[:3500]}"},
            )
            response.raise_for_status()
            return str(response.json().get("result", {}).get("message_id", "telegram-sent"))


def build_notification_adapters() -> list[NotificationAdapter]:
    provider = os.getenv("EMAIL_PROVIDER", "console")
    if provider == "smtp" and os.getenv("SMTP_HOST"):
        email: NotificationAdapter = SmtpEmailAdapter()
    elif provider == "resend" and os.getenv("RESEND_API_KEY"):
        email = ResendEmailAdapter()
    else:
        email = ConsoleEmailAdapter()
    return [email, TelegramAdapter()]
