"""
Simple authentication for Mapo web UI and API.

Enabled by setting MAPO_AUTH_USERNAME and MAPO_AUTH_PASSWORD env vars.
Optional TOTP (MFA) via MAPO_AUTH_TOTP_SECRET.

When auth is disabled (no env vars set), all routes are open.
"""
import hashlib
import hmac
import os
import secrets
import time

from fastapi import Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

# ---------------------------------------------------------------------------
# Config from env vars
# ---------------------------------------------------------------------------

AUTH_USERNAME = os.environ.get("MAPO_USERNAME", "")
AUTH_PASSWORD = os.environ.get("MAPO_PASSWORD", "")
TOTP_SECRET = os.environ.get("MAPO_TOTP_SECRET", "")
AUTH_ENABLED = bool(AUTH_USERNAME and AUTH_PASSWORD)

# Session tokens (in-memory, cleared on restart)
_sessions: dict[str, float] = {}  # token -> expiry timestamp
SESSION_LIFETIME = 60 * 60 * 24  # 24 hours
SESSION_COOKIE = "mapo_session"

# ---------------------------------------------------------------------------
# TOTP implementation (no external dependency)
# ---------------------------------------------------------------------------

def _hotp(secret_b32: str, counter: int) -> str:
    """Generate a 6-digit HOTP code (RFC 4226)."""
    import base64
    import struct
    key = base64.b32decode(secret_b32.upper().replace(" ", ""), casefold=True)
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(code % 1_000_000).zfill(6)


def verify_totp(secret_b32: str, code: str, window: int = 1) -> bool:
    """Verify a 6-digit TOTP code with a time window tolerance."""
    if not secret_b32 or not code:
        return False
    current_step = int(time.time()) // 30
    for offset in range(-window, window + 1):
        if _hotp(secret_b32, current_step + offset) == code.strip():
            return True
    return False


def get_totp_uri(secret_b32: str, username: str = "mapo") -> str:
    """Generate otpauth:// URI for QR code scanning."""
    return f"otpauth://totp/Mapo:{username}?secret={secret_b32}&issuer=Mapo"


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

def _create_session() -> str:
    """Create a new session token."""
    token = secrets.token_urlsafe(32)
    _sessions[token] = time.time() + SESSION_LIFETIME
    # Clean expired sessions
    now = time.time()
    expired = [k for k, v in _sessions.items() if v < now]
    for k in expired:
        del _sessions[k]
    return token


def _check_session(request: Request) -> bool:
    """Check if the request has a valid session cookie."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return False
    expiry = _sessions.get(token)
    if not expiry or expiry < time.time():
        _sessions.pop(token, None)
        return False
    return True


# ---------------------------------------------------------------------------
# Auth check (call this in route handlers)
# ---------------------------------------------------------------------------

def is_authenticated(request: Request) -> bool:
    """Return True if auth is disabled or user has a valid session."""
    if not AUTH_ENABLED:
        return True
    return _check_session(request)


# ---------------------------------------------------------------------------
# Login page HTML
# ---------------------------------------------------------------------------

LOGIN_HTML = """<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Mapo — Login</title>
<link rel="stylesheet" href="/static/style.css">
<style>
.login-card {
  max-width: 380px; margin: 15vh auto; padding: 2rem;
  background: var(--card); border: 1px solid var(--border); border-radius: var(--radius);
}
.login-card h1 { text-align: center; margin-bottom: 1.5rem; font-size: 1.4rem; }
.login-card h1 span { color: var(--primary); }
.login-card .field { margin-bottom: 1rem; }
.login-card .error { color: var(--error); font-size: 0.875rem; margin-bottom: 1rem; text-align: center; }
.login-card button { width: 100%; }
</style>
</head>
<body>
<div class="login-card">
  <h1><span>Mapo</span> Login</h1>
  {error}
  <form method="POST" action="/auth/login">
    <div class="field">
      <label for="username">Username</label>
      <input type="text" id="username" name="username" required autocomplete="username">
    </div>
    <div class="field">
      <label for="password">Password</label>
      <input type="password" id="password" name="password" required autocomplete="current-password">
    </div>
    {totp_field}
    <button type="submit" class="btn btn-primary">Sign In</button>
  </form>
</div>
<script>
(function() {
  const saved = localStorage.getItem('mapo-theme');
  if (saved) document.documentElement.setAttribute('data-theme', saved);
})();
</script>
</body>
</html>"""

TOTP_FIELD = """<div class="field">
      <label for="totp">Authenticator Code</label>
      <input type="text" id="totp" name="totp" placeholder="6-digit code" autocomplete="one-time-code"
        inputmode="numeric" maxlength="6" pattern="[0-9]{6}">
    </div>"""


def _render_login(error: str = "") -> str:
    error_html = f'<div class="error">{error}</div>' if error else ""
    totp_html = TOTP_FIELD if TOTP_SECRET else ""
    return LOGIN_HTML.replace("{error}", error_html).replace("{totp_field}", totp_html)


# ---------------------------------------------------------------------------
# Route handlers (registered on the FastAPI app by server.py)
# ---------------------------------------------------------------------------

async def login_page(request: Request):
    """GET /auth/login — render login form."""
    if not AUTH_ENABLED:
        return RedirectResponse("/", status_code=302)
    if _check_session(request):
        return RedirectResponse("/", status_code=302)
    return HTMLResponse(_render_login())


async def login_submit(request: Request):
    """POST /auth/login — validate credentials."""
    if not AUTH_ENABLED:
        return RedirectResponse("/", status_code=302)

    form = await request.form()
    username = form.get("username", "")
    password = form.get("password", "")
    totp_code = form.get("totp", "")

    # Constant-time comparison to prevent timing attacks
    user_ok = hmac.compare_digest(username, AUTH_USERNAME)
    pass_ok = hmac.compare_digest(password, AUTH_PASSWORD)

    if not (user_ok and pass_ok):
        return HTMLResponse(_render_login("Invalid username or password."), status_code=401)

    if TOTP_SECRET:
        if not verify_totp(TOTP_SECRET, totp_code):
            return HTMLResponse(_render_login("Invalid authenticator code."), status_code=401)

    token = _create_session()
    response = RedirectResponse("/", status_code=302)
    response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax",
                        max_age=SESSION_LIFETIME)
    return response


async def logout(request: Request):
    """GET /auth/logout — clear session."""
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        _sessions.pop(token, None)
    response = RedirectResponse("/auth/login", status_code=302)
    response.delete_cookie(SESSION_COOKIE)
    return response


async def check_auth_api(request: Request):
    """GET /auth/check — API endpoint to check auth status."""
    return JSONResponse({"authenticated": is_authenticated(request), "auth_enabled": AUTH_ENABLED})
