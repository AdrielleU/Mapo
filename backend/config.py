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

    @classmethod
    def from_dict(cls, d: dict) -> "WebhookConfig":
        return cls(
            enabled=d.get("enabled", False),
            urls=d.get("urls", []),
            retry_count=d.get("retry_count", 3),
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
    provider: str = "anthropic"  # anthropic, openai
    api_key: str = ""
    model: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "AIConfig":
        return cls(
            enabled=d.get("enabled", False),
            provider=d.get("provider", "anthropic"),
            api_key=d.get("api_key", ""),
            model=d.get("model", ""),
        )


@dataclass
class MapoConfig:
    proxy: ProxyConfig = field(default_factory=ProxyConfig)
    enrichment: EnrichmentConfig = field(default_factory=EnrichmentConfig)
    webhooks: WebhookConfig = field(default_factory=WebhookConfig)
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)
    outputs: OutputConfig = field(default_factory=OutputConfig)
    ai: AIConfig = field(default_factory=AIConfig)


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

    return cfg


def load_config() -> MapoConfig:
    """Load config from YAML file with env var overrides."""
    raw = _load_yaml()
    cfg = MapoConfig(
        proxy=ProxyConfig.from_dict(raw.get("proxy", {})),
        enrichment=EnrichmentConfig.from_dict(raw.get("enrichment", {})),
        webhooks=WebhookConfig.from_dict(raw.get("webhooks", {})),
        scheduler=SchedulerConfig.from_dict(raw.get("scheduler", {})),
        outputs=OutputConfig.from_dict(raw.get("outputs", {})),
        ai=AIConfig.from_dict(raw.get("ai", {})),
    )
    return _apply_env_overrides(cfg)


# Singleton — imported by all modules
config = load_config()
