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


class AnswerDraft(BaseModel):
    """The model's reply to a customer's question: text that refers to figures only through placeholders."""

    answer: str


class LLMClient(Protocol):
    def draft(self, prompt: str) -> ExplanationDraft: ...

    def answer(self, prompt: str) -> AnswerDraft: ...


class FakeLLM:
    """Returns scripted drafts in order (an Exception in the script is raised), then repeats the last one.
    Question answers have their own script (`answers`). Records every prompt in `prompts` and every
    question prompt in `ask_prompts`."""

    def __init__(
        self,
        script: list[ExplanationDraft | Exception],
        answers: list[AnswerDraft | Exception] | None = None,
    ):
        self._script = deque(script)
        self._last: ExplanationDraft | Exception | None = None
        self._answers = deque(answers or [])
        self._last_answer: AnswerDraft | Exception | None = None
        self.prompts: list[str] = []
        self.ask_prompts: list[str] = []

    def draft(self, prompt: str) -> ExplanationDraft:
        self.prompts.append(prompt)
        if self._script:
            self._last = self._script.popleft()
        if self._last is None:
            raise RuntimeError("FakeLLM has no scripted response")
        if isinstance(self._last, Exception):
            raise self._last
        return self._last

    def answer(self, prompt: str) -> AnswerDraft:
        self.ask_prompts.append(prompt)
        if self._answers:
            self._last_answer = self._answers.popleft()
        if self._last_answer is None:
            raise RuntimeError("FakeLLM has no scripted answer")
        if isinstance(self._last_answer, Exception):
            raise self._last_answer
        return self._last_answer


class GeminiClient:
    """Gemini via the google-genai SDK with structured output."""

    def __init__(self, api_key: str, model: str):
        if not api_key or not model:
            raise ValueError("GEMINI_API_KEY and GEMINI_MODEL are both required")
        from google import genai  # imported here so tests never load the SDK

        self._genai = genai
        self._client = genai.Client(api_key=api_key)
        self._model = model

    def _generate(self, prompt: str, schema):
        from google.genai import types

        def ask(**extra):
            return self._client.models.generate_content(
                model=self._model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json", response_schema=schema, **extra
                ),
            )

        # The text is short and the engine has done the thinking, so minimal thinking cut the live
        # latency by more than half. A model that does not take the setting is asked again without it.
        try:
            response = ask(thinking_config=types.ThinkingConfig(thinking_level="minimal"))
        except Exception:  # noqa: BLE001 - the SDK's error types differ by version
            response = ask()
        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, schema):
            return parsed
        return schema.model_validate_json(response.text)

    def draft(self, prompt: str) -> ExplanationDraft:
        return self._generate(prompt, ExplanationDraft)

    def answer(self, prompt: str) -> AnswerDraft:
        return self._generate(prompt, AnswerDraft)


def make_llm(settings: Settings) -> LLMClient | None:
    """The real client when both the key and the model are configured, otherwise None, in which
    case explanations come from the checked template."""
    if settings.gemini_api_key and settings.gemini_model:
        return GeminiClient(settings.gemini_api_key, settings.gemini_model)
    return None
