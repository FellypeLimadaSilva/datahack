from __future__ import annotations

import json
import logging
import os
import smtplib
import socket
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Any

import requests

log = logging.getLogger(__name__)
_SEVERITY_ORDER = {"warning": 1, "error": 2}
_TIMEOUT = 10


@dataclass
class Alert:
    title: str
    message: str
    severity: str = "error"
    context: dict[str, Any] = field(default_factory=dict)

    def text(self) -> str:
        lines = [f"[{self.severity.upper()}] {self.title}", self.message]
        lines += [f"{k}: {v}" for k, v in self.context.items() if v not in (None, "")]
        return "\n".join(lines)


def _env(name: str) -> str | None:
    value = os.environ.get(name)
    return value.strip() if value and value.strip() else None


def _slack(url: str, alert: Alert) -> None:
    requests.post(url, json={"text": alert.text()}, timeout=_TIMEOUT).raise_for_status()


def _teams(url: str, alert: Alert) -> None:
    facts = [{"title": k, "value": str(v)} for k, v in alert.context.items() if v not in (None, "")]
    card = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": [
                        {
                            "type": "TextBlock",
                            "text": f"[{alert.severity.upper()}] {alert.title}",
                            "weight": "Bolder",
                            "wrap": True,
                        },
                        {"type": "TextBlock", "text": alert.message, "wrap": True},
                        {"type": "FactSet", "facts": facts},
                    ],
                },
            }
        ],
    }
    requests.post(url, json=card, timeout=_TIMEOUT).raise_for_status()


def _webhook(url: str, alert: Alert) -> None:
    payload = {
        "title": alert.title,
        "message": alert.message,
        "severity": alert.severity,
        "context": alert.context,
        "host": socket.gethostname(),
    }
    requests.post(
        url,
        data=json.dumps(payload, default=str),
        timeout=_TIMEOUT,
        headers={"Content-Type": "application/json"},
    ).raise_for_status()


def _email(alert: Alert) -> None:
    host, to = _env("DH_SMTP_HOST"), _env("DH_ALERT_EMAIL_TO")
    msg = EmailMessage()
    msg["Subject"] = f"[DataHack][{alert.severity.upper()}] {alert.title}"
    msg["From"] = _env("DH_SMTP_FROM") or _env("DH_SMTP_USER") or "datahack@localhost"
    msg["To"] = to
    msg.set_content(alert.text())
    port = int(_env("DH_SMTP_PORT") or 587)
    with smtplib.SMTP(host, port, timeout=_TIMEOUT) as smtp:
        if (_env("DH_SMTP_STARTTLS") or "true").lower() == "true":
            smtp.starttls()
        user, password = _env("DH_SMTP_USER"), _env("DH_SMTP_PASSWORD")
        if user and password:
            smtp.login(user, password)
        smtp.send_message(msg)


def configured_channels() -> list[str]:
    channels = []
    if _env("DH_ALERT_SLACK_WEBHOOK_URL"):
        channels.append("slack")
    if _env("DH_ALERT_TEAMS_WEBHOOK_URL"):
        channels.append("teams")
    if _env("DH_ALERT_WEBHOOK_URL"):
        channels.append("webhook")
    if _env("DH_SMTP_HOST") and _env("DH_ALERT_EMAIL_TO"):
        channels.append("email")
    return channels


def send_alert(alert: Alert) -> list[str]:
    minimum = _env("DH_ALERT_MIN_SEVERITY") or "warning"
    if _SEVERITY_ORDER.get(alert.severity, 2) < _SEVERITY_ORDER.get(minimum, 1):
        return []
    senders = {
        "slack": lambda: _slack(_env("DH_ALERT_SLACK_WEBHOOK_URL"), alert),
        "teams": lambda: _teams(_env("DH_ALERT_TEAMS_WEBHOOK_URL"), alert),
        "webhook": lambda: _webhook(_env("DH_ALERT_WEBHOOK_URL"), alert),
        "email": lambda: _email(alert),
    }
    delivered = []
    for channel in configured_channels():
        try:
            senders[channel]()
            delivered.append(channel)
        except Exception:
            log.exception("falha ao enviar alerta", extra={"channel": channel})
    return delivered
