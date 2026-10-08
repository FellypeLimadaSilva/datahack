import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from datahack_ingest.alerting import Alert, configured_channels, send_alert


class _Sink(BaseHTTPRequestHandler):
    received: list = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        _Sink.received.append((self.path, json.loads(self.rfile.read(length))))
        code = 500 if self.path == "/quebrado" else 200
        self.send_response(code)
        self.end_headers()

    def log_message(self, *args):
        return


@pytest.fixture
def base(monkeypatch):
    for var in (
        "DH_ALERT_SLACK_WEBHOOK_URL",
        "DH_ALERT_TEAMS_WEBHOOK_URL",
        "DH_ALERT_WEBHOOK_URL",
        "DH_SMTP_HOST",
        "DH_ALERT_EMAIL_TO",
        "DH_ALERT_MIN_SEVERITY",
    ):
        monkeypatch.delenv(var, raising=False)
    _Sink.received = []
    srv = HTTPServer(("127.0.0.1", 0), _Sink)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_no_channels_configured(base):
    assert configured_channels() == []
    assert send_alert(Alert("t", "m")) == []


def test_slack_teams_webhook_payloads(base, monkeypatch):
    monkeypatch.setenv("DH_ALERT_SLACK_WEBHOOK_URL", f"{base}/slack")
    monkeypatch.setenv("DH_ALERT_TEAMS_WEBHOOK_URL", f"{base}/teams")
    monkeypatch.setenv("DH_ALERT_WEBHOOK_URL", f"{base}/hook")
    delivered = send_alert(Alert("Falha", "erro x", "error", {"run_id": "r1"}))
    assert delivered == ["slack", "teams", "webhook"]
    payloads = dict(_Sink.received)
    assert "Falha" in payloads["/slack"]["text"] and "run_id: r1" in payloads["/slack"]["text"]
    card = payloads["/teams"]["attachments"][0]["content"]
    assert card["type"] == "AdaptiveCard" and card["body"][2]["facts"][0]["value"] == "r1"
    assert payloads["/hook"]["severity"] == "error"


def test_min_severity_filters_warnings(base, monkeypatch):
    monkeypatch.setenv("DH_ALERT_WEBHOOK_URL", f"{base}/hook")
    monkeypatch.setenv("DH_ALERT_MIN_SEVERITY", "error")
    assert send_alert(Alert("t", "m", "warning")) == []
    assert send_alert(Alert("t", "m", "error")) == ["webhook"]


def test_broken_channel_never_raises(base, monkeypatch):
    monkeypatch.setenv("DH_ALERT_WEBHOOK_URL", f"{base}/quebrado")
    monkeypatch.setenv("DH_ALERT_SLACK_WEBHOOK_URL", f"{base}/slack")
    assert send_alert(Alert("t", "m")) == ["slack"]
