"""Customer API skeleton. Routes arrive with the customer stories (tasks T029 onward).

This module must never import `crossroads.internal_api` (FR-023, FR-026): the two services share
only the engine, db and adapters packages.
"""

from fastapi import FastAPI

app = FastAPI(
    title="Crossroads customer API",
    openapi_url="/api/openapi.json",
    docs_url="/api/docs",
)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
