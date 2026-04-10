"""
Central configuration loader for Mapo.

Loads settings from mapo.yaml (if present) with environment variable overrides.
All modules import Config from here.
"""
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


CONFIG_PATH = Path(__file__).parent.parent / "mapo.yaml"


@dataclass
class ProxyConfig:
    enabled: bool = False
    urls: list[str] = field(default_factory=list)
    rotation: str = "round_robin"  # round_robin, random, geo_match
    geo_match: bool = False

    @classmethod
    def from_dict(cls, d: dict) -> "ProxyConfig":
        return cls(
            enabled=d.get("enabled", False),
            urls=d.get("urls", []),
            rotation=d.get("rotation", "round_robin"),
            geo_match=d.get("geo_match", False),
        )


@dataclass
class EnrichmentConfig:
    provider: str = "rapidapi"  # rapidapi, hunter, apollo
    api_key: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "EnrichmentConfig":
        return cls(
            provider=d.get("provider", "rapidapi"),
            api_key=d.get("api_key", ""),
        )


@dataclass
class WebhookConfig:
    enabled: bool = False
    urls: list[str] = field(default_factory=list)
    retry_count: int = 3
    heartbeat_url: str = ""        # POST every heartbeat_interval to confirm alive
    heartbeat_interval: int = 300  # seconds (default 5 minutes)

    @classmethod
    def from_dict(cls, d: dict) -> "WebhookConfig":
        return cls(
            enabled=d.get("enabled", False),
            urls=d.get("urls", []),
            retry_count=d.get("retry_count", 3),
            heartbeat_url=d.get("heartbeat_url", ""),
            heartbeat_interval=d.get("heartbeat_interval", 300),
        )


@dataclass
class SchedulerConfig:
    enabled: bool = False
    jobs: list[dict] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "SchedulerConfig":
        return cls(
            enabled=d.get("enabled", False),
            jobs=d.get("jobs", []),
        )


@dataclass
class OutputConfig:
    targets: list[dict] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "OutputConfig":
        return cls(targets=d.get("targets", []))


@dataclass
class AIConfig:
    enabled: bool = False
    provider: str = "anthropic"  # anthropic, openai, gemini, vllm
    api_key: str = ""
    model: str = ""
    base_url: str = ""  # For vLLM: http://localhost:8001/v1
    icp: str = ""  # Ideal Customer Profile definition
    product_description: str = ""  # What you're selling

    @classmethod
    def from_dict(cls, d: dict) -> "AIConfig":
        return cls(
            enabled=d.get("enabled", False),
            provider=d.get("provider", "anthropic"),
            api_key=d.get("api_key", ""),
            model=d.get("model", ""),
            base_url=d.get("base_url", ""),
            icp=d.get("icp", ""),
            product_description=d.get("product_description", ""),
        )


@dataclass
class ScrapingConfig:
    browser: str = "camoufox"    # camoufox (CloverLabs Firefox) or patchright (Chromium)
    concurrency: int = 5        # parallel HTTP requests for place pages
    min_delay: float = 0.5      # minimum human-like delay (seconds)
    max_delay: float = 2.0      # maximum human-like delay (seconds)
    scroll_timeout: int = 40    # seconds before declaring scroll stuck
    headless: bool = True       # false to show browser window (debug)
    default_zoom: float = 14    # default map zoom level (1-21)

    @classmethod
    def from_dict(cls, d: dict) -> "ScrapingConfig":
        return cls(
            browser=d.get("browser", "camoufox"),
            concurrency=d.get("concurrency", 5),
            min_delay=d.get("min_delay", 0.5),
            max_delay=d.get("max_delay", 2.0),
            scroll_timeout=d.get("scroll_timeout", 40),
            headless=d.get("headless", True),
            default_zoom=d.get("default_zoom", 14),
        )


@dataclass
class LimitsConfig:
    max_results_per_query: int = 5000     # cap on max_results param
    max_cities_per_job: int = 200         # cap on city expansion
    max_total_places: int = 10000         # absolute ceiling per job
    max_concurrent_jobs: int = 3          # how many jobs can run at once
    max_runtime_minutes: int = 120        # auto-cancel after N minutes
    warn_threshold: int = 1000            # UI warning above this estimated total

    @classmethod
    def from_dict(cls, d: dict) -> "LimitsConfig":
        return cls(
            max_results_per_query=d.get("max_results_per_query", 5000),
            max_cities_per_job=d.get("max_cities_per_job", 200),
            max_total_places=d.get("max_total_places", 10000),
            max_concurrent_jobs=d.get("max_concurrent_jobs", 3),
            max_runtime_minutes=d.get("max_runtime_minutes", 120),
            warn_threshold=d.get("warn_threshold", 1000),
        )


@dataclass
class MapoConfig:
    proxy: ProxyConfig = field(default_factory=ProxyConfig)
    enrichment: EnrichmentConfig = field(default_factory=EnrichmentConfig)
    webhooks: WebhookConfig = field(default_factory=WebhookConfig)
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)
    outputs: OutputConfig = field(default_factory=OutputConfig)
    ai: AIConfig = field(default_factory=AIConfig)
    scraping: ScrapingConfig = field(default_factory=ScrapingConfig)
    limits: LimitsConfig = field(default_factory=LimitsConfig)


def _load_yaml() -> dict:
    """Load mapo.yaml if it exists."""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f) or {}
    return {}


def _apply_env_overrides(cfg: MapoConfig) -> MapoConfig:
    """Override config values from environment variables."""
    # Proxy
    proxy_urls = os.environ.get("MAPO_PROXY_URLS")
    if proxy_urls:
        cfg.proxy.enabled = True
        cfg.proxy.urls = [u.strip() for u in proxy_urls.split(",") if u.strip()]
    if os.environ.get("MAPO_PROXY_ROTATION"):
        cfg.proxy.rotation = os.environ["MAPO_PROXY_ROTATION"]

    # Enrichment
    if os.environ.get("MAPO_ENRICHMENT_PROVIDER"):
        cfg.enrichment.provider = os.environ["MAPO_ENRICHMENT_PROVIDER"]
    if os.environ.get("MAPO_ENRICHMENT_API_KEY"):
        cfg.enrichment.api_key = os.environ["MAPO_ENRICHMENT_API_KEY"]

    # Webhooks
    webhook_urls = os.environ.get("MAPO_WEBHOOK_URLS")
    if webhook_urls:
        cfg.webhooks.enabled = True
        cfg.webhooks.urls = [u.strip() for u in webhook_urls.split(",") if u.strip()]

    # AI
    if os.environ.get("MAPO_AI_PROVIDER"):
        cfg.ai.provider = os.environ["MAPO_AI_PROVIDER"]
    if os.environ.get("MAPO_AI_API_KEY"):
        cfg.ai.enabled = True
        cfg.ai.api_key = os.environ["MAPO_AI_API_KEY"]
    if os.environ.get("MAPO_AI_MODEL"):
        cfg.ai.model = os.environ["MAPO_AI_MODEL"]
    if os.environ.get("MAPO_AI_BASE_URL"):
        cfg.ai.base_url = os.environ["MAPO_AI_BASE_URL"]
    if os.environ.get("MAPO_AI_ICP"):
        cfg.ai.icp = os.environ["MAPO_AI_ICP"]
    if os.environ.get("MAPO_AI_PRODUCT"):
        cfg.ai.product_description = os.environ["MAPO_AI_PRODUCT"]

    # Scraping
    if os.environ.get("MAPO_SCRAPING_CONCURRENCY"):
        cfg.scraping.concurrency = int(os.environ["MAPO_SCRAPING_CONCURRENCY"])
    if os.environ.get("MAPO_SCRAPING_MIN_DELAY"):
        cfg.scraping.min_delay = float(os.environ["MAPO_SCRAPING_MIN_DELAY"])
    if os.environ.get("MAPO_SCRAPING_MAX_DELAY"):
        cfg.scraping.max_delay = float(os.environ["MAPO_SCRAPING_MAX_DELAY"])
    if os.environ.get("MAPO_SCRAPING_SCROLL_TIMEOUT"):
        cfg.scraping.scroll_timeout = int(os.environ["MAPO_SCRAPING_SCROLL_TIMEOUT"])
    if os.environ.get("MAPO_SCRAPING_HEADLESS") in ("false", "0", "no"):
        cfg.scraping.headless = False

    # Limits
    if os.environ.get("MAPO_LIMITS_MAX_RESULTS_PER_QUERY"):
        cfg.limits.max_results_per_query = int(os.environ["MAPO_LIMITS_MAX_RESULTS_PER_QUERY"])
    if os.environ.get("MAPO_LIMITS_MAX_CITIES_PER_JOB"):
        cfg.limits.max_cities_per_job = int(os.environ["MAPO_LIMITS_MAX_CITIES_PER_JOB"])
    if os.environ.get("MAPO_LIMITS_MAX_TOTAL_PLACES"):
        cfg.limits.max_total_places = int(os.environ["MAPO_LIMITS_MAX_TOTAL_PLACES"])
    if os.environ.get("MAPO_LIMITS_MAX_CONCURRENT_JOBS"):
        cfg.limits.max_concurrent_jobs = int(os.environ["MAPO_LIMITS_MAX_CONCURRENT_JOBS"])
    if os.environ.get("MAPO_LIMITS_MAX_RUNTIME_MINUTES"):
        cfg.limits.max_runtime_minutes = int(os.environ["MAPO_LIMITS_MAX_RUNTIME_MINUTES"])
    if os.environ.get("MAPO_LIMITS_WARN_THRESHOLD"):
        cfg.limits.warn_threshold = int(os.environ["MAPO_LIMITS_WARN_THRESHOLD"])

    return cfg


# ---------------------------------------------------------------------------
# UI settings persistence (data/settings.json)
# ---------------------------------------------------------------------------

SETTINGS_PATH = Path(__file__).parent.parent / "data" / "settings.json"


def _load_ui_settings() -> dict:
    """Load saved UI settings if they exist."""
    if SETTINGS_PATH.exists():
        try:
            import json
            with open(SETTINGS_PATH) as f:
                return json.loads(f.read()) or {}
        except Exception:
            pass
    return {}


def _save_ui_settings(settings: dict) -> None:
    """Write UI settings to disk."""
    import json
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_PATH, "w") as f:
        json.dump(settings, f, indent=2)


def _apply_ui_settings(cfg: MapoConfig, ui: dict) -> MapoConfig:
    """Apply UI settings on top of existing config (highest priority)."""
    # Proxy
    p = ui.get("proxy", {})
    if p.get("urls"):
        cfg.proxy.enabled = True
        cfg.proxy.urls = [u.strip() for u in p["urls"] if u.strip()]
    if p.get("rotation"):
        cfg.proxy.rotation = p["rotation"]

    # Enrichment
    e = ui.get("enrichment", {})
    if e.get("provider"):
        cfg.enrichment.provider = e["provider"]
    if e.get("api_key"):
        cfg.enrichment.api_key = e["api_key"]

    # AI
    a = ui.get("ai", {})
    if a.get("provider"):
        cfg.ai.provider = a["provider"]
    if a.get("api_key"):
        cfg.ai.enabled = True
        cfg.ai.api_key = a["api_key"]
    if a.get("model"):
        cfg.ai.model = a["model"]
    if a.get("base_url"):
        cfg.ai.base_url = a["base_url"]
    if "icp" in a:
        cfg.ai.icp = a["icp"]
    if "product_description" in a:
        cfg.ai.product_description = a["product_description"]
    if a.get("enabled") is False:
        cfg.ai.enabled = False

    # Scraping
    s = ui.get("scraping", {})
    if s.get("browser"):
        cfg.scraping.browser = s["browser"]
    if "concurrency" in s:
        cfg.scraping.concurrency = int(s["concurrency"])
    if "min_delay" in s:
        cfg.scraping.min_delay = float(s["min_delay"])
    if "max_delay" in s:
        cfg.scraping.max_delay = float(s["max_delay"])
    if "scroll_timeout" in s:
        cfg.scraping.scroll_timeout = int(s["scroll_timeout"])
    if "headless" in s:
        cfg.scraping.headless = bool(s["headless"])

    # Webhooks
    w = ui.get("webhooks", {})
    if w.get("urls"):
        cfg.webhooks.enabled = True
        cfg.webhooks.urls = [u.strip() for u in w["urls"] if u.strip()]
    if w.get("heartbeat_url"):
        cfg.webhooks.heartbeat_url = w["heartbeat_url"]
    if w.get("heartbeat_interval"):
        cfg.webhooks.heartbeat_interval = int(w["heartbeat_interval"])

    # Limits
    lim = ui.get("limits", {})
    if "max_results_per_query" in lim:
        cfg.limits.max_results_per_query = int(lim["max_results_per_query"])
    if "max_cities_per_job" in lim:
        cfg.limits.max_cities_per_job = int(lim["max_cities_per_job"])
    if "max_total_places" in lim:
        cfg.limits.max_total_places = int(lim["max_total_places"])
    if "max_concurrent_jobs" in lim:
        cfg.limits.max_concurrent_jobs = int(lim["max_concurrent_jobs"])
    if "max_runtime_minutes" in lim:
        cfg.limits.max_runtime_minutes = int(lim["max_runtime_minutes"])
    if "warn_threshold" in lim:
        cfg.limits.warn_threshold = int(lim["warn_threshold"])

    return cfg


def load_config() -> MapoConfig:
    """Load config: mapo.yaml → env vars → UI settings (highest priority)."""
    raw = _load_yaml()
    cfg = MapoConfig(
        proxy=ProxyConfig.from_dict(raw.get("proxy", {})),
        enrichment=EnrichmentConfig.from_dict(raw.get("enrichment", {})),
        webhooks=WebhookConfig.from_dict(raw.get("webhooks", {})),
        scheduler=SchedulerConfig.from_dict(raw.get("scheduler", {})),
        outputs=OutputConfig.from_dict(raw.get("outputs", {})),
        ai=AIConfig.from_dict(raw.get("ai", {})),
        scraping=ScrapingConfig.from_dict(raw.get("scraping", {})),
        limits=LimitsConfig.from_dict(raw.get("limits", {})),
    )
    cfg = _apply_env_overrides(cfg)
    cfg = _apply_ui_settings(cfg, _load_ui_settings())
    return cfg


def reload_config() -> None:
    """Reload the config singleton in-place (called after UI settings change).

    Updates all fields on the existing object so modules that imported
    ``from backend.config import config`` see the new values.
    """
    new = load_config()
    for field_name in ("proxy", "enrichment", "webhooks", "scheduler",
                       "outputs", "ai", "scraping", "limits"):
        setattr(config, field_name, getattr(new, field_name))


# Singleton — imported by all modules
config = load_config()
