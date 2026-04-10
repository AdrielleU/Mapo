"""
Unified notification helper for Mapo.

Auto-detects the notification provider from the URL and formats the payload
appropriately. Supports Slack, Discord, ntfy.sh, Pushover, n8n/Make/Zapier,
and any custom HTTP endpoint.

All notifications are simple alerts (title + message + level) — for full job
result delivery, use the existing webhook system in backend/webhooks.py.
"""
import json
import os
import time
from typing import Optional

import httpx


# ---------------------------------------------------------------------------
# Provider detection
# ---------------------------------------------------------------------------

def detect_provider(url: str) -> str:
    """Identify the notification provider from the URL."""
    if not url:
        return "none"
    u = url.lower()
    if "hooks.slack.com" in u:
        return "slack"
    if "discord.com/api/webhooks" in u or "discordapp.com/api/webhooks" in u:
        return "discord"
    if "ntfy.sh" in u:
        return "ntfy"
    if "api.pushover.net" in u:
        return "pushover"
    if "api.pushbullet.com" in u:
        return "pushbullet"
    if "hook.eu1.make.com" in u or "hook.us1.make.com" in u or "hook.integromat.com" in u:
        return "make"
    if "/webhook/" in u and ("n8n" in u or "automate" in u):
        return "n8n"
    return "custom"


# ---------------------------------------------------------------------------
# Payload builders (one per provider)
# ---------------------------------------------------------------------------

def _build_slack(title: str, message: str, level: str, extra: dict) -> dict:
    color = {"info": "#4a90e2", "success": "#36a64f", "warning": "#f0ad4e", "error": "#ff0000"}.get(level, "#808080")
    emoji = {"info": ":information_source:", "success": ":white_check_mark:",
             "warning": ":warning:", "error": ":x:"}.get(level, ":bell:")
    fields = []
    for k, v in extra.items():
        if v is not None:
            fields.append({"type": "mrkdwn", "text": f"*{k}:*\n{v}"})
    return {
        "attachments": [{
            "color": color,
            "blocks": [
                {"type": "header", "text": {"type": "plain_text", "text": f"{emoji} {title}"}},
                {"type": "section", "text": {"type": "mrkdwn", "text": message}},
                *([{"type": "section", "fields": fields}] if fields else []),
            ],
        }],
    }


def _build_discord(title: str, message: str, level: str, extra: dict) -> dict:
    color = {"info": 0x4a90e2, "success": 0x36a64f, "warning": 0xf0ad4e, "error": 0xff0000}.get(level, 0x808080)
    emoji = {"info": "ℹ️", "success": "✅", "warning": "⚠️", "error": "❌"}.get(level, "🔔")
    fields = [{"name": k, "value": str(v), "inline": True} for k, v in extra.items() if v is not None]
    return {
        "embeds": [{
            "title": f"{emoji} {title}",
            "description": message,
            "color": color,
            "fields": fields,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }],
    }


def _build_ntfy(title: str, message: str, level: str, extra: dict) -> dict:
    """ntfy.sh accepts JSON with title/message/priority/tags."""
    priority = {"info": 3, "success": 3, "warning": 4, "error": 5}.get(level, 3)
    tags = {"info": ["information_source"], "success": ["white_check_mark"],
            "warning": ["warning"], "error": ["x", "rotating_light"]}.get(level, [])
    body_text = message
    if extra:
        body_text += "\n\n" + "\n".join(f"{k}: {v}" for k, v in extra.items() if v is not None)
    return {
        "title": title,
        "message": body_text,
        "priority": priority,
        "tags": tags,
    }


def _build_pushover(title: str, message: str, level: str, extra: dict, token: str = "", user: str = "") -> dict:
    priority = {"info": 0, "success": 0, "warning": 1, "error": 2}.get(level, 0)
    body_text = message
    if extra:
        body_text += "\n\n" + "\n".join(f"{k}: {v}" for k, v in extra.items() if v is not None)
    return {
        "token": token or os.environ.get("PUSHOVER_TOKEN", ""),
        "user": user or os.environ.get("PUSHOVER_USER", ""),
        "title": title,
        "message": body_text,
        "priority": priority,
    }


def _build_pushbullet(title: str, message: str, level: str, extra: dict) -> dict:
    body_text = message
    if extra:
        body_text += "\n\n" + "\n".join(f"{k}: {v}" for k, v in extra.items() if v is not None)
    return {"type": "note", "title": title, "body": body_text}


def _build_generic(title: str, message: str, level: str, extra: dict) -> dict:
    """Generic JSON payload — n8n, Make, Zapier, custom endpoints."""
    return {
        "title": title,
        "message": message,
        "level": level,
        "timestamp": time.time(),
        **extra,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def send_notification(
    url: str,
    title: str,
    message: str,
    level: str = "info",
    extra: Optional[dict] = None,
    headers: Optional[dict] = None,
) -> bool:
    """Send a notification to any supported provider, auto-detected from URL.

    Args:
        url: Target URL (Slack/Discord/ntfy/Pushover/n8n/Make/custom)
        title: Short title
        message: Body text
        level: "info", "success", "warning", or "error"
        extra: Optional dict of extra fields (job_id, query, etc.)
        headers: Optional custom headers (e.g. for auth)

    Returns:
        True on success, False on failure (does not raise).
    """
    if not url:
        return False

    provider = detect_provider(url)
    extra = extra or {}

    builders = {
        "slack": _build_slack,
        "discord": _build_discord,
        "ntfy": _build_ntfy,
        "pushover": _build_pushover,
        "pushbullet": _build_pushbullet,
    }
    builder = builders.get(provider, _build_generic)
    payload = builder(title, message, level, extra)

    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    if provider == "pushbullet":
        # Pushbullet requires Access-Token header
        token = os.environ.get("PUSHBULLET_TOKEN", "")
        if token:
            req_headers["Access-Token"] = token

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.post(url, json=payload, headers=req_headers)
            resp.raise_for_status()
        return True
    except Exception as e:
        print(f"[Mapo] Notification to {provider} failed: {e}")
        return False


async def send_notification_async(
    url: str,
    title: str,
    message: str,
    level: str = "info",
    extra: Optional[dict] = None,
    headers: Optional[dict] = None,
) -> bool:
    """Async version — same as send_notification but uses httpx.AsyncClient."""
    if not url:
        return False

    provider = detect_provider(url)
    extra = extra or {}

    builders = {
        "slack": _build_slack,
        "discord": _build_discord,
        "ntfy": _build_ntfy,
        "pushover": _build_pushover,
        "pushbullet": _build_pushbullet,
    }
    builder = builders.get(provider, _build_generic)
    payload = builder(title, message, level, extra)

    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    if provider == "pushbullet":
        token = os.environ.get("PUSHBULLET_TOKEN", "")
        if token:
            req_headers["Access-Token"] = token

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload, headers=req_headers)
            resp.raise_for_status()
        return True
    except Exception as e:
        print(f"[Mapo] Notification to {provider} failed: {e}")
        return False
