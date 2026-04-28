"""Tests for adaptive backoff helpers in backend.scrapers.places."""

from types import SimpleNamespace

from backend.scrapers.places import _backoff_seconds, _looks_blocked


def _fake_resp(status=200, url="https://www.google.com/maps/place/foo", text="<html></html>"):
    return SimpleNamespace(
        status_code=status,
        url=url,
        text=text,
        content=text.encode() if text else b"",
    )


def test_looks_blocked_429():
    assert _looks_blocked(_fake_resp(status=429)) is True


def test_looks_blocked_403():
    assert _looks_blocked(_fake_resp(status=403)) is True


def test_looks_blocked_sorry_redirect():
    assert _looks_blocked(_fake_resp(url="https://www.google.com/sorry/index?continue=...")) is True


def test_looks_blocked_captcha_in_html():
    html = "<html><body>Please complete this CAPTCHA to continue.</body></html>"
    assert _looks_blocked(_fake_resp(text=html)) is True


def test_looks_blocked_unusual_traffic():
    html = "<body>Unusual traffic from your computer network</body>"
    assert _looks_blocked(_fake_resp(text=html)) is True


def test_normal_response_not_blocked():
    assert _looks_blocked(_fake_resp(status=200, text="<html>normal place page</html>")) is False


def test_backoff_increases_with_attempt():
    # Same blocked status → later attempts wait longer
    a0 = _backoff_seconds(0, blocked=True)
    a3 = _backoff_seconds(3, blocked=True)
    assert a3 > a0


def test_backoff_capped():
    assert _backoff_seconds(20, blocked=True) <= 90.0


def test_backoff_blocked_floor_higher_than_unblocked():
    # On the same attempt, blocked backoff is at least as long as unblocked
    for attempt in range(5):
        b = _backoff_seconds(attempt, blocked=True)
        u = _backoff_seconds(attempt, blocked=False)
        assert b >= u or attempt > 4  # jitter can occasionally tie at low attempts
