"""Explanation service: model text through the check, template as the fallback."""

import pytest

from crossroads.adapters.llm import ExplanationDraft, FakeLLM, GeminiClient, make_llm
from crossroads.config import Settings
from crossroads.engine.recommend import evaluate
from crossroads.explain import template
from crossroads.explain.facts import build_facts
from crossroads.explain.service import ExplainService, build_prompt

GOOD = ExplanationDraft(
    headline="{path_label} saves money",
    explanation="{path_label} costs {cost_5yr} over {horizon_years}, which is {savings_5yr} less than {compare_label}.",
)
BAD_DIGITS = ExplanationDraft(headline="Save 5000 dollars", explanation="It costs 31,200 over 5 years.")
BAD_PLACEHOLDER = ExplanationDraft(headline="{path_label}", explanation="Your {mystery} is {cost_5yr}.")


@pytest.fixture
def facts_variant(make_lease, cfg):
    inp = make_lease()
    return build_facts(inp, evaluate(inp, cfg), cfg)


def test_good_model_text_is_rendered_with_the_engines_values(facts_variant):
    facts, variant = facts_variant
    llm = FakeLLM([GOOD])
    e = ExplainService(llm).explain(facts, variant)
    assert (e.source, e.verified) == ("gemini", True)
    assert facts["cost_5yr"] in e.text and facts["savings_5yr"] in e.text
    assert "{" not in e.text and "{" not in e.headline


def test_rejected_text_is_retried_once_then_accepted(facts_variant):
    facts, variant = facts_variant
    llm = FakeLLM([BAD_DIGITS, GOOD])
    e = ExplainService(llm).explain(facts, variant)
    assert e.source == "gemini" and len(llm.prompts) == 2


def test_text_rejected_twice_falls_back_to_the_template(facts_variant):
    facts, variant = facts_variant
    llm = FakeLLM([BAD_DIGITS, BAD_PLACEHOLDER])
    e = ExplainService(llm).explain(facts, variant)
    assert (e.source, e.verified) == ("template", True)
    assert len(llm.prompts) == 2


def test_an_unknown_placeholder_is_rejected(facts_variant):
    facts, variant = facts_variant
    assert ExplainService(FakeLLM([BAD_PLACEHOLDER, BAD_PLACEHOLDER])).explain(facts, variant).source == "template"


def test_a_failing_model_falls_back_to_the_template(facts_variant):
    facts, variant = facts_variant
    llm = FakeLLM([RuntimeError("network down")])
    e = ExplainService(llm).explain(facts, variant)
    assert (e.source, e.verified) == ("template", True)
    assert len(llm.prompts) == 1


def test_no_llm_means_the_template(facts_variant):
    facts, variant = facts_variant
    e = ExplainService(None).explain(facts, variant)
    assert (e.source, e.verified) == ("template", True)
    assert facts["path_label"] in e.text


def test_the_same_facts_call_the_model_once(facts_variant):
    facts, variant = facts_variant
    llm = FakeLLM([GOOD])
    svc = ExplainService(llm)
    svc.explain(facts, variant)
    svc.explain(facts, variant)
    assert len(llm.prompts) == 1


def test_the_prompt_lists_the_placeholders_and_forbids_numbers(facts_variant):
    facts, variant = facts_variant
    prompt = build_prompt(facts, variant)
    assert "{cost_5yr}" in prompt and "{path_label}" in prompt
    assert "Never write a digit" in prompt


def test_a_broken_template_degrades_to_a_message_with_no_figures(facts_variant, monkeypatch):
    facts, variant = facts_variant
    monkeypatch.setitem(template.BODIES, variant, "It costs 5 dollars.")
    e = ExplainService(None).explain(facts, variant)
    assert e.verified is False
    assert not any(ch.isdigit() for ch in e.text + e.headline)


def test_gemini_needs_both_a_key_and_a_model():
    with pytest.raises(ValueError):
        GeminiClient("", "")
    with pytest.raises(ValueError):
        GeminiClient("key", "")


def test_make_llm_is_none_without_configuration():
    s = Settings("", "", "", "", "", "", "", "")
    assert make_llm(s) is None
