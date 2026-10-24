"""Explanations: model text through the number check, with the checked template as fallback."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Literal

from ..adapters.llm import LLMClient
from . import numcheck, template

log = logging.getLogger(__name__)

_RULES = (
    "You write a short, plain-language explanation of a car-finance recommendation for the "
    "customer. Reference every figure ONLY through the placeholders listed below, written with "
    "curly braces, for example {cost_5yr}. Never write a digit or a spelled-out number (one, two, "
    "twenty, hundred ...). Each placeholder value already includes its unit, so never write unit "
    "words next to a placeholder. Use only the placeholders listed."
)


@dataclass(frozen=True)
class Explanation:
    headline: str
    text: str
    source: Literal["gemini", "template"]
    verified: bool


def build_prompt(facts: dict[str, str], variant: str) -> str:
    lines = "\n".join(f"- {{{k}}} = {v}" for k, v in sorted(facts.items()))
    shape = {
        "normal": (
            "Say which path is best and why it beats the comparison, and mention the monthly payment, "
            "what is due up front and the room left in the budget."
        ),
        "only": (
            "Say that this is the only path that fits, and mention its cost, monthly payment and "
            "what is due up front."
        ),
        "none": (
            "Say that no path fits the budget and cash right now, which one comes closest, and by "
            "how much it falls short."
        ),
    }[variant]
    return (
        f"{_RULES}\n\nPlaceholders and their current values (for your understanding only):\n"
        f"{lines}\n\n{shape} Return a headline of at most eight words and an explanation of two "
        f"or three sentences."
    )


class ExplainService:
    def __init__(self, llm: LLMClient | None = None, retries: int = 1):
        self._llm = llm
        self._retries = retries
        self._cache: dict[str, Explanation] = {}

    def explain(self, facts: dict[str, str], variant: str) -> Explanation:
        key = hashlib.sha256(json.dumps([facts, variant], sort_keys=True).encode()).hexdigest()
        if key not in self._cache:
            self._cache[key] = self._explain(facts, variant)
        return self._cache[key]

    def template_explanation(self, facts: dict[str, str], variant: str) -> Explanation:
        """The deterministic, checked template. If it ever fails the check (a defect that tests
        guard against) it degrades to a message that contains no figures."""
        headline = template.render_checked(template.HEADLINES[variant], facts)
        text = template.render_checked(template.BODIES[variant], facts)
        if headline is None or text is None:
            log.error("template explanation failed the number check")
            return Explanation("Your recommendation", "See the figures shown for each path.", "template", False)
        return Explanation(headline, text, "template", True)

    def _explain(self, facts: dict[str, str], variant: str) -> Explanation:
        if self._llm is not None:
            prompt = build_prompt(facts, variant)
            for _ in range(1 + self._retries):
                try:
                    draft = self._llm.draft(prompt)
                except Exception:  # network and SDK failures all mean "use the template"
                    log.exception("LLM call failed")
                    break
                headline = numcheck.verify_and_render(draft.headline, facts)
                text = numcheck.verify_and_render(draft.explanation, facts)
                if headline is not None and text is not None:
                    return Explanation(headline, text, "gemini", True)
        return self.template_explanation(facts, variant)
