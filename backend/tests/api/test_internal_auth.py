"""Staff sign-in and the guard on every internal route (FR-025, FR-027, SC-009).

The password here is random and made fresh for each run, so no password is written in any file.
"""

import secrets
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from crossroads.config import Settings
from crossroads.internal_api import auth
from crossroads.internal_api.auth import SESSION_SECONDS, hash_password, make_token
from crossroads.internal_api.main import create_app
from crossroads.internal_api.routes import router
from crossroads.internal_api.snapshots import InMemorySnapshots
from crossroads.seed.memory import InMemoryStore
from crossroads.seed.profiles import generate_profiles

PROFILES = generate_profiles()
URL = "/api/internal"


class Clock:
    def __init__(self, now: float = 1_700_000_000.0):
        self.now = now

    def __call__(self) -> float:
        return self.now


@pytest.fixture(scope="module")
def creds():
    password = secrets.token_urlsafe(18)
    return SimpleNamespace(
        user="staff", password=password, hash=hash_password(password), secret=secrets.token_urlsafe(32)
    )


def build(creds, *, secure=False, clock=None, peer="93.184.216.34", **override):
    f = dict(staff_user=creds.user, staff_password_hash=creds.hash, session_secret=creds.secret, cookie_secure=secure)
    f.update(override)
    settings = Settings(
        "", "", "", "", "", f["staff_user"], f["staff_password_hash"], f["session_secret"], f["cookie_secure"]
    )
    app = create_app(
        settings=settings, store=InMemoryStore(PROFILES), snapshots=InMemorySnapshots(), clock=clock or Clock()
    )
    return TestClient(app, client=(peer, 50000)), app


def sign_in(client, creds):
    r = client.post(f"{URL}/login", json={"username": creds.user, "password": creds.password})
    assert r.status_code == 204, r.text
    return r


def protected_routes():
    """Every route the internal router defines except sign-in, straight from the router itself."""
    out = [(m, r.path) for r in router.routes for m in r.methods if not r.path.endswith("/login")]
    assert out, "the router should have routes"
    return sorted(out)


def test_the_router_has_the_routes_we_expect():
    assert {p for _, p in protected_routes()} == {
        f"{URL}/logout", f"{URL}/session", f"{URL}/portfolio", f"{URL}/portfolio/refresh", f"{URL}/openapi.json"
    }


def test_every_internal_route_but_sign_in_refuses_a_request_with_no_session(creds):
    client, _ = build(creds)
    for method, path in protected_routes():
        r = client.request(method, path)
        assert r.status_code == 401, (method, path)
        assert r.json() == {"detail": "Please sign in."}, "a refusal carries no data"


def test_a_successful_sign_in_sets_a_locked_down_cookie(creds):
    client, _ = build(creds)
    cookie = sign_in(client, creds).headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert "path=/api/internal" in cookie and f"max-age={SESSION_SECONDS}" in cookie
    assert "secure" not in cookie.replace("samesite", "")  # off for plain http, on below


def test_the_secure_flag_is_on_when_the_site_is_served_over_https(creds):
    client, _ = build(creds, secure=True)
    assert "secure" in sign_in(client, creds).headers["set-cookie"].lower().replace("samesite", "")


def test_a_session_unlocks_the_routes(creds):
    client, _ = build(creds)
    sign_in(client, creds)
    assert client.get(f"{URL}/session").json() == {"user": "staff"}
    assert client.get(f"{URL}/portfolio").status_code == 200
    assert client.get(f"{URL}/openapi.json").status_code == 200


def test_the_api_description_is_not_public(creds):
    client, _ = build(creds)
    assert client.get(f"{URL}/openapi.json").status_code == 401
    assert client.get("/openapi.json").status_code == 404 and client.get("/docs").status_code == 404
    sign_in(client, creds)
    paths = client.get(f"{URL}/openapi.json").json()["paths"]
    assert all(p.startswith(URL) or p == "/healthz" for p in paths)


def test_a_wrong_username_and_a_wrong_password_look_exactly_the_same(creds):
    client, _ = build(creds)
    bad_pw = client.post(f"{URL}/login", json={"username": creds.user, "password": secrets.token_urlsafe(12)})
    bad_user = client.post(f"{URL}/login", json={"username": "nobody", "password": creds.password})
    refused = (401, {"detail": "Invalid credentials"})
    assert (bad_pw.status_code, bad_pw.json()) == (bad_user.status_code, bad_user.json()) == refused
    assert "set-cookie" not in bad_pw.headers and "set-cookie" not in bad_user.headers


def test_an_empty_password_is_refused(creds):
    client, _ = build(creds)
    assert client.post(f"{URL}/login", json={"username": creds.user, "password": ""}).status_code == 401


def test_a_malformed_sign_in_is_a_readable_422_not_a_stack_trace(creds):
    client, _ = build(creds)
    r = client.post(f"{URL}/login", json={"username": creds.user})
    assert r.status_code == 422 and r.json() == {"detail": "Please check what you entered."}


def test_with_no_staff_credentials_configured_sign_in_says_so_and_never_succeeds(creds):
    client, _ = build(creds, staff_password_hash="")
    r = client.post(f"{URL}/login", json={"username": creds.user, "password": creds.password})
    assert r.status_code == 503 and "not configured" in r.json()["detail"] and "set-cookie" not in r.headers
    client, _ = build(creds, session_secret="")
    assert client.post(f"{URL}/login", json={"username": creds.user, "password": creds.password}).status_code == 503


def _token(client) -> str:
    return client.cookies.get(auth.COOKIE)


def test_a_tampered_cookie_is_refused(creds):
    client, _ = build(creds)
    sign_in(client, creds)
    payload, signature = _token(client).split(".")
    flipped = ("A" if payload[5] != "A" else "B")
    changed_payload = f"{payload[:5]}{flipped}{payload[6:]}.{signature}"
    for forged in (changed_payload, f"{payload}.{signature[:-2]}xx", payload, "garbage", ""):
        fresh, _ = build(creds)
        fresh.cookies.set(auth.COOKIE, forged, path=URL)
        assert fresh.get(f"{URL}/session").status_code == 401, forged


def test_a_cookie_signed_with_another_secret_is_refused(creds):
    client, _ = build(creds)
    forged = make_token(creds.user, secrets.token_urlsafe(32), 1_700_000_000.0)
    client.cookies.set(auth.COOKIE, forged, path=URL)
    assert client.get(f"{URL}/session").status_code == 401


def test_a_session_ends_after_eight_hours_and_not_before(creds):
    clock = Clock()
    client, _ = build(creds, clock=clock)
    sign_in(client, creds)
    clock.now += SESSION_SECONDS - 1
    assert client.get(f"{URL}/portfolio").status_code == 200
    clock.now += 2
    r = client.get(f"{URL}/portfolio")
    assert r.status_code == 401 and r.json() == {"detail": "Please sign in."}, "an expired session returns no data"


def test_signing_out_ends_the_session_even_if_the_cookie_is_replayed(creds):
    client, _ = build(creds)
    sign_in(client, creds)
    token = _token(client)
    assert client.post(f"{URL}/logout").status_code == 204
    assert client.get(f"{URL}/session").status_code == 401
    replay, _ = build(creds)  # a fresh client holding the old token
    replay.cookies.set(auth.COOKIE, token, path=URL)
    # (a new app has no memory of the sign-out, so this also shows why the revocation is per process)
    client.cookies.set(auth.COOKIE, token, path=URL)
    assert client.get(f"{URL}/session").status_code == 401


def test_signing_out_needs_a_session(creds):
    client, _ = build(creds)
    assert client.post(f"{URL}/logout").status_code == 401


def test_no_response_ever_contains_the_password_or_its_hash(creds):
    client, _ = build(creds)
    seen = [sign_in(client, creds).text, client.get(f"{URL}/session").text, client.get(f"{URL}/portfolio").text,
            client.post(f"{URL}/login", json={"username": creds.user, "password": "wrong"}).text]
    for text in seen:
        assert creds.password not in text and creds.hash not in text


def test_health_check_is_open_and_returns_no_data(creds):
    client, _ = build(creds)
    assert client.get("/healthz").json() == {"status": "ok"}


def test_a_hash_is_argon2_salted_and_never_the_password(creds):
    other = hash_password(creds.password)
    assert creds.hash.startswith("$argon2") and creds.hash != other  # salted: the same password hashes differently
    assert creds.password not in creds.hash
    assert auth.check_credentials("staff", creds.hash, "staff", creds.password)
    assert not auth.check_credentials("staff", creds.hash, "staff", creds.password + "x")


def test_a_wrong_username_costs_the_same_work_as_a_wrong_password(creds, monkeypatch):
    calls = []
    real = auth._hasher

    class Counting:
        def verify(self, h, p):
            calls.append(1)
            return real.verify(h, p)

    monkeypatch.setattr(auth, "_hasher", Counting())
    auth.check_credentials("staff", creds.hash, "staff", "wrong")
    auth.check_credentials("staff", creds.hash, "nobody", "wrong")
    assert len(calls) == 2  # a password check ran both times, so the timing does not reveal which was wrong


def test_the_hash_command_asks_for_the_password_at_a_hidden_prompt(creds, monkeypatch, capsys):
    answers = iter([creds.password, creds.password])
    monkeypatch.setattr(auth.getpass, "getpass", lambda prompt="": next(answers))
    assert auth.main(["auth", "hash"]) == 0
    out = capsys.readouterr().out.strip()
    assert out.startswith("$argon2") and creds.password not in out
    assert auth.check_credentials("staff", out, "staff", creds.password)


def test_the_hash_command_refuses_mismatched_entries_and_bad_usage(creds, monkeypatch, capsys):
    answers = iter([creds.password, creds.password + "x"])
    monkeypatch.setattr(auth.getpass, "getpass", lambda prompt="": next(answers))
    assert auth.main(["auth", "hash"]) == 1
    assert "$argon2" not in capsys.readouterr().out
    assert auth.main(["auth", creds.password]) == 2  # a password on the command line is not accepted
    assert creds.password not in capsys.readouterr().out


# --- sign-in rate limit (FR-036) ---

BAD = {"username": "staff", "password": "definitely-wrong"}
PROXY = "10.0.0.2"  # a private address: the proxy in front of the API


def fail(client, n=1, body=BAD, headers=None):
    return [client.post(f"{URL}/login", json=body, headers=headers or {}) for _ in range(n)][-1]


def test_five_failures_lock_the_address_with_429_and_a_retry_delay(creds):
    client, _ = build(creds)
    assert [fail(client).status_code for _ in range(5)] == [401] * 5
    locked = fail(client)
    assert locked.status_code == 429 and locked.json() == {"detail": "Too many attempts. Please try again later."}
    assert locked.headers["retry-after"] == "900"


def test_a_locked_address_is_refused_even_with_the_right_password(creds):
    client, _ = build(creds)
    fail(client, 5)
    r = client.post(f"{URL}/login", json={"username": creds.user, "password": creds.password})
    assert r.status_code == 429 and "set-cookie" not in r.headers


def test_the_lock_ends_after_fifteen_minutes_and_the_retry_delay_counts_down(creds):
    clock = Clock()
    client, _ = build(creds, clock=clock)
    fail(client, 5)
    clock.now += 600
    assert fail(client).headers["retry-after"] == "300"
    clock.now += 301
    sign_in(client, creds)


def test_failures_older_than_fifteen_minutes_do_not_count(creds):
    clock = Clock()
    client, _ = build(creds, clock=clock)
    fail(client, 4)
    clock.now += 901
    assert fail(client).status_code == 401  # a fresh count of one, so no lock
    assert fail(client, 4).status_code == 401  # the fifth in the new window is still answered 401 ...
    assert fail(client).status_code == 429  # ... and locks from the next attempt


def test_a_successful_sign_in_resets_the_count(creds):
    client, _ = build(creds)
    fail(client, 4)
    sign_in(client, creds)
    assert [fail(client).status_code for _ in range(4)] == [401] * 4  # not locked: the count started over


def test_a_different_address_is_not_affected(creds):
    clock = Clock()
    _, app = build(creds, clock=clock)
    a = TestClient(app, client=("93.184.216.34", 1))
    b = TestClient(app, client=("151.101.2.9", 1))
    fail(a, 5)
    assert fail(a).status_code == 429
    r = b.post(f"{URL}/login", json={"username": creds.user, "password": creds.password})
    assert r.status_code == 204


def test_the_lock_does_not_depend_on_the_username_so_it_reveals_nothing_about_it(creds):
    client, _ = build(creds)
    for name in ("staff", "nobody", "admin", "staff", "x"):
        fail(client, body={"username": name, "password": "wrong"})
    a = fail(client, body={"username": "staff", "password": "wrong"})
    b = fail(client, body={"username": "nobody", "password": "wrong"})
    assert (a.status_code, a.json(), a.headers["retry-after"]) == (b.status_code, b.json(), b.headers["retry-after"])


def test_the_forwarded_address_is_used_only_when_the_request_comes_from_the_proxy(creds):
    _, app = build(creds)
    proxy = TestClient(app, client=(PROXY, 1))
    fail(proxy, 5, headers={"X-Forwarded-For": "151.101.2.50"})
    assert fail(proxy, headers={"X-Forwarded-For": "151.101.2.50"}).status_code == 429
    other = proxy.post(f"{URL}/login", json=BAD, headers={"X-Forwarded-For": "151.101.2.51"})
    assert other.status_code == 401, "a different client behind the same proxy is not locked"


def test_a_direct_client_cannot_dodge_the_lock_by_sending_its_own_forwarded_header(creds):
    client, _ = build(creds, peer="93.184.216.34")
    for i in range(5):
        fail(client, headers={"X-Forwarded-For": f"151.101.2.{i}"})
    assert fail(client, headers={"X-Forwarded-For": "151.101.2.99"}).status_code == 429


def test_behind_the_proxy_a_forged_leftmost_entry_does_not_help(creds):
    _, app = build(creds)
    proxy = TestClient(app, client=(PROXY, 1))
    # The proxy appends the real client last; anything the client put before it is ignored.
    for i in range(5):
        fail(proxy, headers={"X-Forwarded-For": f"9.9.9.{i}, 151.101.2.77"})
    assert fail(proxy, headers={"X-Forwarded-For": "9.9.9.200, 151.101.2.77"}).status_code == 429


def test_requests_that_are_not_sign_in_attempts_are_not_counted(creds):
    client, _ = build(creds)
    for _ in range(8):
        client.get(f"{URL}/session")
        client.post(f"{URL}/login", json={"username": creds.user})  # malformed: 422
    sign_in(client, creds)
