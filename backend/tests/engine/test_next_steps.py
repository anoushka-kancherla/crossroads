"""The three kinds of next step, and how many customers' recommendations need a specialist (Toyota
"Guide" and "Value: reduce service effort"). The path-to-step mapping is an illustrative assumption."""

from crossroads.engine.next_steps import NEXT_STEP_LABELS, NEXT_STEP_ORDER, NEXT_STEP_TYPES, next_step_of
from crossroads.engine.schemas import PATH_ORDER


def test_every_path_has_exactly_one_next_step_type():
    assert set(NEXT_STEP_TYPES) == set(PATH_ORDER)
    assert set(NEXT_STEP_TYPES.values()) <= set(NEXT_STEP_ORDER)


def test_the_three_types_are_all_used_and_labelled_in_plain_words():
    assert list(NEXT_STEP_ORDER) == ["self_service", "eligible_offer", "specialist_follow_up"]
    assert set(NEXT_STEP_TYPES.values()) == set(NEXT_STEP_ORDER)
    assert NEXT_STEP_LABELS == {
        "self_service": "Self-service",
        "eligible_offer": "Eligible offer",
        "specialist_follow_up": "Specialist follow-up",
    }


def test_the_mapping_the_demo_describes():
    assert next_step_of("keep_as_is") == next_step_of("extra_principal") == "self_service"
    assert next_step_of("buy_out") == next_step_of("refinance") == "eligible_offer"
    assert next_step_of("return_lease_new") == next_step_of("trade_in_early") == next_step_of("walk_away") == (
        "specialist_follow_up"
    )
