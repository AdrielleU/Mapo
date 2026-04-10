"""
Webhook delivery system for Mapo.

Sends HTTP POST notifications when scraping tasks complete or fail.
Supports generic JSON webhooks and Slack-formatted payloads.  Delivery
happens in background threads to avoid blocking the main process.
"""
import json
import logging
import threading
import time
from datetime import datetime, timezone

try:
    import httpx
    _HAS_HTTPX = True
except ImportError:
    _HAS_HTTPX = False

from backend.config import config as _app_config

logger = logging.getLogger(__name__)

# Retry schedule: attempt 1 immediately, then 1 s, 4 s, 16 s (exponential).
_DEFAULT_RETRY_COUNT = 3
_BACKOFF_BASE = 4  # delay = base ** attempt  (0→1 s, 1→4 s, 2→16 s)


def _is_slack_url(url: str) -> bool:
    return "hooks.slack.com" in url


def _build_slack_payload(event_type: str, payload: dict) -> dict:
    """Format *payload* as a Slack Block Kit message."""
    job_id = payload.get("job_id", "unknown")
    query = payload.get("query", "N/A")
    result_count = payload.get("result_count", 0)
    duration = payload.get("duration_seconds", 0)
    ts = payload.get("timestamp", "")

    if event_type == "task.completed":
        title = "Scrape Completed"
        emoji = ":white_check_mark:"
    else:
        title = "Scrape Failed"
        emoji = ":x:"

    return {
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} {title}",
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Job ID:*\n`{job_id}`"},
                    {"type": "mrkdwn", "text": f"*Query:*\n{query}"},
                    {"type": "mrkdwn", "text": f"*Results:*\n{result_count}"},
                    {"type": "mrkdwn", "text": f"*Duration:*\n{duration:.1f}s"},
                    {"type": "mrkdwn", "text": f"*Timestamp:*\n{ts}"},
                ],
            },
        ],
    }


def _build_generic_payload(event_type: str, payload: dict) -> dict:
    """Wrap *payload* with event metadata for a generic webhook receiver."""
    return {
        "event": event_type,
        "data": payload,
    }


class WebhookManager:
    """
    Manages webhook delivery for task lifecycle events.

    Thread-safe.  All HTTP requests are fired in daemon threads so they
    never block the caller.
    """

    def __init__(self):
        webhook_cfg = _app_config.webhooks
        self.enabled: bool = webhook_cfg.enabled
        self.urls: list[str] = list(webhook_cfg.urls)
        self.retry_count: int = webhook_cfg.retry_count or _DEFAULT_RETRY_COUNT
        self._lock = threading.Lock()

        # Attempt to reuse proxy settings for outbound webhook calls
        self._proxy_dict: dict | None = None
        try:
            from backend.proxy import proxy_manager
            self._proxy_dict = proxy_manager.get_proxy_dict()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def send_webhook(self, event_type: str, payload: dict) -> None:
        """
        Deliver a webhook for *event_type* to every configured URL.

        Parameters
        ----------
        event_type : str
            ``"task.completed"`` or ``"task.failed"``.
        payload : dict
            Must include ``job_id``, ``query``, ``result_count``,
            ``timestamp``, and ``duration_seconds``.
        """
        if not self.enabled or not self.urls:
            return

        # Ensure a timestamp is present
        if "timestamp" not in payload:
            payload["timestamp"] = datetime.now(timezone.utc).isoformat()

        for url in self.urls:
            t = threading.Thread(
                target=self._deliver,
                args=(url, event_type, payload),
                daemon=True,
            )
            t.start()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _deliver(self, url: str, event_type: str, payload: dict) -> None:
        """POST to *url* with retries and exponential backoff."""
        if _is_slack_url(url):
            body = _build_slack_payload(event_type, payload)
        else:
            body = _build_generic_payload(event_type, payload)

        headers = {"Content-Type": "application/json"}

        for attempt in range(self.retry_count):
            try:
                if _HAS_HTTPX:
                    self._send_httpx(url, body, headers)
                else:
                    self._send_urllib(url, body, headers)
                logger.info(
                    "Webhook delivered to %s (attempt %d)", url, attempt + 1
                )
                return
            except Exception as exc:
                logger.warning(
                    "Webhook delivery to %s failed (attempt %d/%d): %s",
                    url,
                    attempt + 1,
                    self.retry_count,
                    exc,
                )
                if attempt < self.retry_count - 1:
                    backoff = _BACKOFF_BASE ** attempt  # 1, 4, 16 …
                    time.sleep(backoff)

        logger.error(
            "Webhook delivery to %s failed after %d attempts.", url, self.retry_count
        )

    def _send_httpx(self, url: str, body: dict, headers: dict) -> None:
        """Send via httpx (preferred — supports proxies natively)."""
        kwargs: dict = {
            "headers": headers,
            "content": json.dumps(body),
            "timeout": 10.0,
        }
        if self._proxy_dict:
            kwargs["proxy"] = next(iter(self._proxy_dict.values()), None)

        with httpx.Client() as client:
            resp = client.post(url, **kwargs)
            resp.raise_for_status()

    @staticmethod
    def _send_urllib(url: str, body: dict, headers: dict) -> None:
        """Fallback sender using only the stdlib."""
        import urllib.request

        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode(),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status >= 400:
                raise RuntimeError(f"HTTP {resp.status}")


# Module-level singleton
webhook_manager = WebhookManager()
