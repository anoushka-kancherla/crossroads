"""Read-only checks against the real services. Skipped unless RUN_LIVE=1 and the keys are in the
environment, so the normal suite stays offline. They create nothing in anyone's account.

    RUN_LIVE=1 NESSIE_API_KEY=... GEMINI_API_KEY=... GEMINI_MODEL=... pytest tests/adapters/test_live_services.py
"""

import os

import pytest

from crossroads.adapters.llm import ExplanationDraft, GeminiClient
from crossroads.adapters.nessie import BASE_URL, HttpNessie

LIVE = os.environ.get("RUN_LIVE") == "1"
pytestmark = pytest.mark.skipif(not LIVE, reason="set RUN_LIVE=1 and the service keys to run")


@pytest.mark.skipif(not os.environ.get("NESSIE_API_KEY"), reason="NESSIE_API_KEY is not set")
def test_nessie_answers_over_https_and_its_account_rows_parse():
    client = HttpNessie(os.environ["NESSIE_API_KEY"])
    assert BASE_URL.startswith("https://")
    customers = client._get("/customers")
    assert isinstance(customers, list) and customers, "the sandbox has at least one customer to read"
    for customer in customers[:5]:
        for account in client.get_accounts(customer["_id"]):
            assert account.kind in ("checking", "savings") and account.balance >= 0
            client.get_bills(account.id)
            client.get_deposits(account.id)


@pytest.mark.skipif(
    not (os.environ.get("GEMINI_API_KEY") and os.environ.get("GEMINI_MODEL")), reason="Gemini is not configured"
)
def test_gemini_returns_the_structured_draft_the_app_expects():
    client = GeminiClient(os.environ["GEMINI_API_KEY"], os.environ["GEMINI_MODEL"])
    draft = client.draft(
        "Write a short headline and a two-sentence explanation that {path_label} saves {saving} over keeping "
        "the current plan. Use the placeholders exactly as written, and no other numbers."
    )
    assert isinstance(draft, ExplanationDraft) and draft.headline and draft.explanation
    assert "{saving}" in draft.explanation or "{saving}" in draft.headline
