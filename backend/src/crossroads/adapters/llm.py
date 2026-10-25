"""The LLM behind an interface (constitution, principle IV): a real Gemini client and a fake.

Tests use `FakeLLM` and never need a key or a network.
"""

from __future__ import annotations

from collections import deque
from typing import Protocol

from pydantic import BaseModel

from ..config import Settings


class ExplanationDraft(BaseModel):
    headline: str
    explanation: str


class LLMClient(Protocol):
    def draft(self, prompt: str) -> ExplanationDraft: ...


class FakeLLM:
    """Returns scripted drafts in order (an Exception in the script is raised), then repeats the
    last one. Records every prompt in `prompts`."""

    def __init__(self, script: list[ExplanationDraft | Exception]):
        self._script = deque(script)
        self._last: ExplanationDraft | Exception | None = None
        self.prompts: list[str] = []

    def draft(self, prompt: str) -> ExplanationDraft:
        self.prompts.append(prompt)
        if self._script:
            self._last = self._script.popleft()
        if self._last is None:
            raise RuntimeError("FakeLLM has no scripted response")
        if isinstance(self._last, Exception):
            raise self._last
        return self._last


class GeminiClient:
    """Gemini via the google-genai SDK with structured output."""

    def __init__(self, api_key: str, model: str):
        if not api_key or not model:
            raise ValueError("GEMINI_API_KEY and GEMINI_MODEL are both required")
        from google import genai  # imported here so tests never load the SDK

        self._genai = genai
        self._client = genai.Client(api_key=api_key)
        self._model = model

    def draft(self, prompt: str) -> ExplanationDraft:
        from google.genai import types

        def ask(**extra):
            return self._client.models.generate_content(
                model=self._model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json", response_schema=ExplanationDraft, **extra
                ),
            )

        # The text is short and the engine has done the thinking, so minimal thinking cut the live
        # latency by more than half. A model that does not take the setting is asked again without it.
        try:
            response = ask(thinking_config=types.ThinkingConfig(thinking_level="minimal"))
        except Exception:  # noqa: BLE001 - the SDK's error types differ by version
            response = ask()
        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, ExplanationDraft):
            return parsed
        return ExplanationDraft.model_validate_json(response.text)


def make_llm(settings: Settings) -> LLMClient | None:
    """The real client when both the key and the model are configured, otherwise None, in which
    case explanations come from the checked template."""
    if settings.gemini_api_key and settings.gemini_model:
        return GeminiClient(settings.gemini_api_key, settings.gemini_model)
    return None
