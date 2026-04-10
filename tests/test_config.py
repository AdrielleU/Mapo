"""Tests for backend.config — config loading + UI settings + reload"""
import os

import pytest

from backend.config import (
    config,
    reload_config,
    _save_ui_settings,
    _load_ui_settings,
    LimitsConfig,
    ScrapingConfig,
)


@pytest.fixture(autouse=True)
def cleanup_settings():
    """Remove settings.json before and after each test."""
    path = os.path.join("data", "settings.json")
    if os.path.exists(path):
        os.remove(path)
    yield
    if os.path.exists(path):
        os.remove(path)
    reload_config()


def test_default_config_loads():
    reload_config()
    assert config.scraping.concurrency == 5
    assert config.scraping.headless is True
    assert config.limits.max_results_per_query == 5000


def test_ui_settings_save_and_load():
    settings = {
        "scraping": {"concurrency": 10, "headless": False},
        "limits": {"max_results_per_query": 1000},
    }
    _save_ui_settings(settings)
    loaded = _load_ui_settings()
    assert loaded["scraping"]["concurrency"] == 10
    assert loaded["limits"]["max_results_per_query"] == 1000


def test_reload_config_picks_up_ui_settings():
    _save_ui_settings({
        "scraping": {"concurrency": 10, "browser": "patchright"},
    })
    reload_config()
    assert config.scraping.concurrency == 10
    assert config.scraping.browser == "patchright"


def test_reload_config_resets_after_cleanup():
    _save_ui_settings({"scraping": {"concurrency": 10}})
    reload_config()
    assert config.scraping.concurrency == 10

    os.remove(os.path.join("data", "settings.json"))
    reload_config()
    assert config.scraping.concurrency == 5  # back to default


def test_limits_config_from_dict():
    cfg = LimitsConfig.from_dict({"max_results_per_query": 999, "warn_threshold": 50})
    assert cfg.max_results_per_query == 999
    assert cfg.warn_threshold == 50
    assert cfg.max_concurrent_jobs == 3  # default


def test_scraping_config_from_dict():
    cfg = ScrapingConfig.from_dict({"browser": "patchright", "concurrency": 8})
    assert cfg.browser == "patchright"
    assert cfg.concurrency == 8
    assert cfg.headless is True  # default
