"""Staff sign-in for the internal dashboard (FR-025, FR-027).

The credentials come from configuration: STAFF_USER and STAFF_PASSWORD_HASH, an argon2 hash and never
the password itself. A successful sign-in sets a signed, HttpOnly, SameSite=Strict cookie that expires
after 8 hours. Every internal route except sign-in depends on `require_staff`, so the API itself refuses
an unauthenticated request: hiding the screen is not the protection.

Make a hash with `python -m crossroads.internal_api.auth hash`. The password is asked for at a hidden
prompt, never taken from the command line, so it stays out of shell history and process listings.
"""

from __future__ import annotations

import base64
import getpass
import hashlib
import hmac
import ipaddress
import json
import secrets
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error
from fastapi import HTTPException, Request

COOKIE = "crossroads_staff"
COOKIE_PATH = "/api/internal"  # the browser sends it nowhere else
SESSION_SECONDS = 8 * 60 * 60

_hasher = PasswordHasher()
# Checked when the username is wrong, so a wrong username takes as long as a wrong password.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def check_credentials(configured_user: str, password_hash: str, username: str, password: str) -> bool:
    """True only when both the username and the password match. Constant-time on the username, and the
    same work is done whichever of the two is wrong."""
    user_ok = bool(configured_user) and hmac.compare_digest(username.encode(), configured_user.encode())
    try:
        _hasher.verify(password_hash if (user_ok and password_hash) else _DUMMY_HASH, password)
        password_ok = True
    except (Argon2Error, ValueError):  # a malformed hash is a ValueError in every argon2-cffi version
        password_ok = False
    return user_ok and password_ok and bool(password_hash)


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _sign(payload: str, secret: str) -> str:
    return _b64(hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest())


def make_token(user: str, secret: str, now: float, ttl: int = SESSION_SECONDS) -> str:
    body = {"sub": user, "exp": int(now) + ttl, "jti": secrets.token_urlsafe(8)}
    payload = _b64(json.dumps(body, separators=(",", ":")).encode())
    return f"{payload}.{_sign(payload, secret)}"


def read_token(token: str, secret: str, now: float) -> dict | None:
    """The token's contents, or None if it is malformed, tampered with, signed with another secret, or
    expired. The expiry is inside the signed payload, so the cookie's own lifetime cannot extend it."""
    try:
        payload, signature = token.split(".")
        if not hmac.compare_digest(signature, _sign(payload, secret)):
            return None
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        if not isinstance(data, dict) or int(data["exp"]) <= now or not data.get("jti"):
            return None
        return data
    except (ValueError, KeyError, TypeError):
        return None


FAIL_LIMIT = 5  # failed sign-ins from one address ...
FAIL_WINDOW = 15 * 60  # ... within this many seconds lock it ...
LOCK_SECONDS = 15 * 60  # ... for this many (FR-036)


def _is_proxy(address: str) -> bool:
    """True for a private or loopback peer: the proxy in front of the API, not a browser on the internet."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback


def client_ip(request: Request) -> str:
    """The address the sign-in limit is counted against. X-Forwarded-For is believed only when the
    request itself comes from the proxy, and then only its rightmost public entry (each proxy appends the
    address it saw, so anything a client wrote earlier in the list is ignored). If every entry is private,
    as on a local Docker network, the proxy's own address is used: everyone then shares one count."""
    peer = request.client.host if request.client else "unknown"
    if not _is_proxy(peer):
        return peer
    for hop in reversed([h.strip() for h in request.headers.get("x-forwarded-for", "").split(",")]):
        try:
            ip = ipaddress.ip_address(hop)
        except ValueError:
            continue
        if not (ip.is_private or ip.is_loopback):
            return str(ip)
    return peer


@dataclass
class LoginLimiter:
    """Counts failed sign-ins per address. Whether the username exists never enters into it.
    ponytail: in memory, so a restart clears every lock; shared storage (Redis) if there is ever more than
    one API process."""

    failures: dict[str, list[float]] = field(default_factory=dict)
    locked_until: dict[str, float] = field(default_factory=dict)

    def retry_after(self, ip: str, now: float) -> int:
        """Whole seconds left on the lock for this address, or 0 when it is not locked."""
        until = self.locked_until.get(ip, 0.0)
        return max(0, int(until - now + 0.999)) if until > now else 0

    def record_failure(self, ip: str, now: float) -> None:
        # Drop what has aged out everywhere, so the tables do not grow without bound.
        self.locked_until = {k: u for k, u in self.locked_until.items() if u > now}
        self.failures = {k: [t for t in ts if now - t < FAIL_WINDOW] for k, ts in self.failures.items()}
        self.failures = {k: ts for k, ts in self.failures.items() if ts}
        recent = self.failures.setdefault(ip, [])
        recent.append(now)
        if len(recent) >= FAIL_LIMIT:
            self.locked_until[ip] = now + LOCK_SECONDS
            del self.failures[ip]

    def reset(self, ip: str) -> None:
        self.failures.pop(ip, None)
        self.locked_until.pop(ip, None)


@dataclass
class AuthState:
    user: str
    password_hash: str
    secret: str
    secure: bool = False  # the Secure cookie flag: on whenever the site is served over HTTPS
    clock: Callable[[], float] = time.time
    # jti -> expiry of signed-out sessions. In memory, so it resets on a restart (a sign-out then only
    # lasts until the 8 hours are up). ponytail: shared storage if there is ever more than one process.
    revoked: dict[str, int] = field(default_factory=dict)
    limiter: LoginLimiter = field(default_factory=LoginLimiter)

    @property
    def configured(self) -> bool:
        return bool(self.user and self.password_hash and self.secret)

    def revoke(self, jti: str, exp: int) -> None:
        now = self.clock()
        self.revoked = {j: e for j, e in self.revoked.items() if e > now}
        self.revoked[jti] = exp


def require_staff(request: Request) -> dict:
    """Dependency for every internal route except sign-in: a valid, unexpired, not signed-out session."""
    auth: AuthState = request.app.state.auth
    token = request.cookies.get(COOKIE)
    data = read_token(token, auth.secret, auth.clock()) if (token and auth.secret) else None
    if data is None or data["jti"] in auth.revoked:
        raise HTTPException(status_code=401, detail="Please sign in.")
    return data


def main(argv: list[str]) -> int:
    if argv[1:] != ["hash"]:
        print("usage: python -m crossroads.internal_api.auth hash", file=sys.stderr)
        return 2
    password = getpass.getpass("Staff password (not shown): ")
    if not password or password != getpass.getpass("Again: "):
        print("The two entries did not match, or were empty.", file=sys.stderr)
        return 1
    print(hash_password(password))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
