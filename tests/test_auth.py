"""Tests for backend.auth — TOTP + session management"""
import time

from backend.auth import _hotp, verify_totp, get_totp_uri


def test_hotp_generates_6_digit_code():
    code = _hotp("JBSWY3DPEHPK3PXP", 0)
    assert len(code) == 6
    assert code.isdigit()


def test_hotp_known_test_vector():
    # RFC 4226 test vectors use secret '12345678901234567890' (ASCII)
    # which is base32 'GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ'
    # First HOTP value at counter=0 is '755224'
    code = _hotp("GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ", 0)
    assert code == "755224"


def test_verify_totp_current_code_passes():
    secret = "JBSWY3DPEHPK3PXP"
    current_step = int(time.time()) // 30
    code = _hotp(secret, current_step)
    assert verify_totp(secret, code) is True


def test_verify_totp_wrong_code_fails():
    secret = "JBSWY3DPEHPK3PXP"
    assert verify_totp(secret, "000000") is False


def test_verify_totp_empty_inputs_fail():
    assert verify_totp("", "123456") is False
    assert verify_totp("JBSWY3DPEHPK3PXP", "") is False


def test_get_totp_uri_format():
    uri = get_totp_uri("ABCDEF", "alice")
    assert uri.startswith("otpauth://totp/Mapo:alice")
    assert "secret=ABCDEF" in uri
    assert "issuer=Mapo" in uri
