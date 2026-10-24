"""Internal API skeleton. Auth and the portfolio routes arrive with tasks T064 to T066.

Only `/healthz` exists so far, and it returns no data. Every future route except login will
depend on a session check (FR-025).
"""

from fastapi import FastAPI

app = FastAPI(
    title="Crossroads internal API",
    openapi_url="/api/internal/openapi.json",
    docs_url=None,
)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
