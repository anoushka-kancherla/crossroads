"""Print the internal API's OpenAPI description, built offline (no server, no sign-in needed).

The live description is behind staff sign-in, so the internal app's `npm run gen:api` uses this.
Run with the backend's Python: `.venv/bin/python scripts/dump_openapi.py > openapi.json`.
"""

import json

from crossroads.config import Settings
from crossroads.internal_api.main import create_app
from crossroads.seed.memory import InMemoryStore
from crossroads.seed.profiles import generate_profiles

app = create_app(Settings("", "", "", "", "", "", "", ""), store=InMemoryStore(generate_profiles()))
print(json.dumps(app.openapi()))
