"""Tests for backend.notifications"""
from backend.notifications import detect_provider, _build_slack, _build_discord, _build_ntfy, _build_generic


def test_detect_slack():
    assert detect_provider("https://hooks.slack.com/services/T00/B00/abc") == "slack"


def test_detect_discord():
    assert detect_provider("https://discord.com/api/webhooks/123/abc") == "discord"
    assert detect_provider("https://discordapp.com/api/webhooks/123/abc") == "discord"


def test_detect_ntfy():
    assert detect_provider("https://ntfy.sh/my-topic") == "ntfy"


def test_detect_pushover():
    assert detect_provider("https://api.pushover.net/1/messages.json") == "pushover"


def test_detect_pushbullet():
    assert detect_provider("https://api.pushbullet.com/v2/pushes") == "pushbullet"


def test_detect_make():
    assert detect_provider("https://hook.eu1.make.com/abc123") == "make"


def test_detect_n8n():
    assert detect_provider("https://my-n8n.com/webhook/abc") == "n8n"


def test_detect_custom():
    assert detect_provider("https://example.com/notify") == "custom"


def test_detect_empty():
    assert detect_provider("") == "none"


def test_build_slack_payload():
    payload = _build_slack("Test", "Hello", "info", {"key": "value"})
    assert "attachments" in payload
    assert payload["attachments"][0]["color"]
    assert any("Test" in str(b) for b in payload["attachments"][0]["blocks"])


def test_build_slack_severity_colors():
    info_color = _build_slack("t", "m", "info", {})["attachments"][0]["color"]
    error_color = _build_slack("t", "m", "error", {})["attachments"][0]["color"]
    assert info_color != error_color


def test_build_discord_payload():
    payload = _build_discord("Test", "Hello", "success", {"foo": "bar"})
    assert "embeds" in payload
    assert payload["embeds"][0]["title"] == "✅ Test"
    assert payload["embeds"][0]["description"] == "Hello"
    assert any(f["name"] == "foo" for f in payload["embeds"][0]["fields"])


def test_build_ntfy_payload():
    payload = _build_ntfy("Test", "Hello", "warning", {"key": "val"})
    assert payload["title"] == "Test"
    assert "Hello" in payload["message"]
    assert "key: val" in payload["message"]
    assert payload["priority"] == 4


def test_build_generic_payload():
    payload = _build_generic("Test", "Hello", "error", {"job_id": "abc"})
    assert payload["title"] == "Test"
    assert payload["message"] == "Hello"
    assert payload["level"] == "error"
    assert payload["job_id"] == "abc"
    assert "timestamp" in payload
