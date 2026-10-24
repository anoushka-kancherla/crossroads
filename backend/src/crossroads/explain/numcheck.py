"""Number check for explanation text (FR-010, constitution principle III).

Text may reference figures only through `{placeholders}` naming keys in the engine's facts object.
Raw text containing a digit or a spelled-out number outside a placeholder, or a placeholder whose
key is not in the facts, is rejected. Accepted text is rendered by substituting the engine's own
formatted values, so no figure in it can differ from the engine's.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping

PLACEHOLDER = re.compile(r"\{([^{}]*)\}")
_NUMBER_WORDS = re.compile(
    r"\b(zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|"
    r"fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|"
    r"ninety|hundred|thousand|million)\b",
    re.IGNORECASE,
)


def check(text: str, allowed_keys: Collection[str]) -> list[str]:
    """Problems found in `text`; an empty list means it passes."""
    problems: list[str] = []
    for key in PLACEHOLDER.findall(text):
        if key not in allowed_keys:
            problems.append(f"unknown placeholder {{{key}}}")
    outside = PLACEHOLDER.sub(" ", text)
    if "{" in outside or "}" in outside:
        problems.append("malformed placeholder")
    if re.search(r"\d", outside):
        problems.append("digit outside a placeholder")
    problems.extend(f"number word '{w}' outside a placeholder" for w in _NUMBER_WORDS.findall(outside))
    return problems


def render(text: str, facts: Mapping[str, str]) -> str:
    return PLACEHOLDER.sub(lambda m: facts[m.group(1)], text)


def verify_and_render(text: str, facts: Mapping[str, str]) -> str | None:
    """The rendered text, or None if the raw text fails the check."""
    return None if check(text, facts.keys()) else render(text, facts)
