"""GeminiClient's call to the SDK, with a stub in place of the network (a gated live check is in
test_live_services.py)."""

from types import SimpleNamespace

from crossroads.adapters.llm import ExplanationDraft, GeminiClient

DRAFT = ExplanationDraft(headline="h", explanation="e")


class StubModels:
    def __init__(self, reject_thinking: bool = False):
        self.configs = []
        self.reject_thinking = reject_thinking

    def generate_content(self, model, contents, config):
        self.configs.append(config)
        if self.reject_thinking and getattr(config, "thinking_config", None) is not None:
            raise ValueError("thinking_level is not supported by this model")
        return SimpleNamespace(parsed=DRAFT, text=DRAFT.model_dump_json())


def client_with(models: StubModels) -> GeminiClient:
    c = object.__new__(GeminiClient)  # skip __init__: it needs a key and loads the SDK client
    c._client = SimpleNamespace(models=models)
    c._model = "gemini-test"
    return c


def test_it_asks_for_structured_output_with_minimal_thinking():
    models = StubModels()
    assert client_with(models).draft("prompt") == DRAFT
    cfg = models.configs[0]
    assert cfg.response_mime_type == "application/json" and cfg.response_schema is ExplanationDraft
    assert cfg.thinking_config is not None, "explanations are short; thinking time only adds delay"


def test_a_model_that_rejects_the_thinking_setting_is_retried_without_it():
    models = StubModels(reject_thinking=True)
    assert client_with(models).draft("prompt") == DRAFT
    assert len(models.configs) == 2 and models.configs[1].thinking_config is None
