"""Print an API's OpenAPI description, built offline (no server, and no sign-in for the internal API).

    .venv/bin/python scripts/dump_openapi.py internal > openapi.json    (the default)
    .venv/bin/python scripts/dump_openapi.py customer > openapi.json

The live internal description is behind staff sign-in, so each app's `npm run gen:api` uses this instead
of fetching it.
"""

import json
import sys

from crossroads.config import Settings
from crossroads.seed.memory import InMemoryStore
from crossroads.seed.profiles import generate_profiles

store = InMemoryStore(generate_profiles())
if (sys.argv[1] if len(sys.argv) > 1 else "internal") == "customer":
    from crossroads.customer_api.main import create_app

    app = create_app(store=store)
else:
    from crossroads.internal_api.main import create_app

    app = create_app(Settings("", "", "", "", "", "", "", ""), store=store)
print(json.dumps(app.openapi()))
