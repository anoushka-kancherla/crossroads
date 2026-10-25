"""The customer side and the internal side stay apart (FR-023, FR-024, FR-026, SC-008, SC-009).

These checks read the source and the Compose file as well as calling the apps, so a link, a call or a
shared network added later fails here.
"""

import re
from pathlib import Path

from fastapi.testclient import TestClient

from crossroads.config import Settings
from crossroads.customer_api.main import create_app as customer_app
from crossroads.internal_api.main import create_app as internal_app
from crossroads.internal_api.routes import router as internal_router
from crossroads.seed.memory import InMemoryStore
from crossroads.seed.profiles import generate_profiles

ROOT = Path(__file__).resolve().parents[3]
PROFILES = generate_profiles()


def sources(folder: str, *suffixes: str):
    base = ROOT / folder
    return [p for p in base.rglob("*") if p.is_file() and p.suffix in suffixes and "node_modules" not in p.parts
            and "dist" not in p.parts and p.name != "types.ts"]


def test_the_customer_api_exposes_no_internal_or_aggregate_route():
    client = TestClient(customer_app(store=InMemoryStore(PROFILES)))
    for path in client.get("/api/openapi.json").json()["paths"]:
        assert not re.search(r"internal|portfolio|aggregate|retained|revenue|business|staff|login", path), path


def test_the_internal_api_exposes_no_customer_route():
    for route in internal_router.routes:
        assert route.path.startswith("/api/internal/"), route.path
    client = TestClient(internal_app(Settings("", "", "", "", "", "", "", ""), store=InMemoryStore(PROFILES)))
    assert client.get("/api/customers").status_code == 404


def test_the_customer_app_source_never_mentions_the_internal_side():
    files = sources("customer-app", ".ts", ".tsx", ".html", ".css", ".json") + [ROOT / "customer-app" / "Caddyfile"]
    assert len(files) > 10
    for f in files:
        text = f.read_text()
        needles = (
            "/api/internal", "internal-api", "internal-app", "8081",
            "staff", "portfolio", "fairness", "livepanel",
        )
        for needle in needles:
            assert needle not in text.lower(), f"{f.relative_to(ROOT)} mentions {needle!r}"


def test_the_internal_app_source_never_mentions_the_customer_side():
    files = sources("internal-app", ".ts", ".tsx", ".html", ".css", ".json") + [ROOT / "internal-app" / "Caddyfile"]
    assert len(files) > 8
    for f in files:
        text = f.read_text()
        for needle in ("/api/customers", "customer-api", "customer-app", "8080"):
            assert needle not in text, f"{f.relative_to(ROOT)} mentions {needle!r}"


def test_the_customer_api_code_never_imports_the_internal_api():
    files = list((ROOT / "backend" / "src" / "crossroads" / "customer_api").glob("*.py"))
    assert len(files) > 5
    for f in files:
        assert not re.search(r"^\s*(from|import)\s.*internal_api", f.read_text(), re.M), f.name


def _compose() -> dict[str, str]:
    """Each service's block of docker-compose.yml, by name."""
    text = (ROOT / "docker-compose.yml").read_text()
    body = text.split("\nservices:\n", 1)[1].split("\nnetworks:\n", 1)[0]
    parts = re.split(r"\n  (?=[a-z][a-z-]*:\n)", "\n" + body)
    return {p.split(":", 1)[0].strip(): p for p in parts if p.strip()}


def _networks(block: str) -> set[str]:
    m = re.search(r"networks: \[([^\]]*)\]", block)
    return {n.strip() for n in m.group(1).split(",")} if m else set()


def test_the_two_sides_are_on_separate_networks_and_only_the_database_is_on_both():
    s = _compose()
    assert _networks(s["customer-api"]) == _networks(s["customer-app"]) == {"customer-net"}
    assert _networks(s["internal-api"]) == _networks(s["internal-app"]) == {"internal-net"}
    assert _networks(s["db"]) == {"customer-net", "internal-net"}


def test_the_production_overlay_publishes_only_80_and_443_and_only_from_caddy():
    prod = (ROOT / "docker-compose.prod.yml").read_text()
    assert re.findall(r'^\s+- "(\d+:\d+)"', prod, re.M) == ["80:80", "443:443"]
    assert "ports: !reset []" in prod.split("customer-app:")[1].split("internal-app:")[0]
    assert "ports: !reset []" in prod.split("internal-app:")[1].split("customer-api:")[0]
    assert 'COOKIE_SECURE: "true"' in prod
    caddy = (ROOT / "deploy" / "Caddyfile").read_text()
    assert "customer-app:80" in caddy and "internal-app:80" in caddy
    assert "-api" not in caddy, "Caddy proxies to the apps only, never straight to an API"


def test_the_internal_api_publishes_no_port_and_the_customer_side_holds_no_staff_secret():
    s = _compose()
    assert "ports:" not in s["internal-api"] and "ports:" not in s["customer-api"]
    for secret in ("STAFF_USER", "STAFF_PASSWORD_HASH", "SESSION_SECRET"):
        assert secret not in s["customer-api"] and secret not in s["customer-app"], secret
    for key in ("SERPAPI_API_KEY", "NESSIE_API_KEY"):
        assert key not in s["internal-api"], key  # the staff side needs neither


def test_the_customer_side_has_no_fairness_route_import_or_link():
    client = TestClient(customer_app(store=InMemoryStore(PROFILES)))
    assert not [p for p in client.get("/api/openapi.json").json()["paths"] if "fairness" in p]
    assert client.get("/api/fairness").status_code in (404, 405)
    for f in (ROOT / "backend" / "src" / "crossroads" / "customer_api").glob("*.py"):
        assert "fairness" not in f.read_text().lower(), f.name
    compose = _compose()
    assert "FAIRNESS" not in compose["customer-api"] and "FAIRNESS" not in compose["customer-app"]


def test_the_fairness_package_reaches_into_neither_api_surface():
    for f in (ROOT / "backend" / "src" / "crossroads" / "fairness").glob("*.py"):
        text = f.read_text()
        assert not re.search(r"^\s*(from|import)\s.*internal_api", text, re.M), f.name
        assert not re.search(r"^\s*(from|import)\s.*customer_api\.(routes|main)", text, re.M), f.name


def test_the_customer_side_only_writes_acceptances_and_never_reads_the_live_figures():
    client = TestClient(customer_app(store=InMemoryStore(PROFILES)))
    assert not [p for p in client.get("/api/openapi.json").json()["paths"] if "live" in p]
    for f in (ROOT / "backend" / "src" / "crossroads" / "customer_api").glob("*.py"):
        text = f.read_text()
        assert "engine.live" not in text and "engine import live" not in text, f.name
        assert not re.search(r"^\s*(from|import)\s.*internal_api", text, re.M), f.name
    for f in sources("customer-app", ".ts", ".tsx"):
        assert "/api/internal/live" not in f.read_text(), f.name


def test_the_live_figures_module_is_pure():
    import ast

    from crossroads.engine import live

    tree = ast.parse(Path(live.__file__).read_text())
    names = {n.names[0].name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import)}
    names |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert not names & {"random", "datetime", "time", "os"}
