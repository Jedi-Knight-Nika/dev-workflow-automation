import pytest

from app.coordinator.domain.protocol import Checkpoint, Decision, Directive


@pytest.mark.parametrize("action", list(Directive))
@pytest.mark.parametrize("message", ["", "An update"])
def test_decision_effects_preserve_message_delivery_and_review_semantics(action, message):
    decision = Decision(
        1, action, message, "Implement the request", "Reason", (), (), Checkpoint("Goal", (), ())
    )
    assert decision.outbound_message == ("" if action == Directive.WAIT else message)
    assert decision.message_kind == ("QUESTION" if action == Directive.ASK_HUMAN else "UPDATE")
    expected_delivery = action == Directive.REQUEST_REVIEW or (
        bool(message) and action != Directive.WAIT
    )
    assert decision.delivery_status == ("DELIVERY_PENDING" if expected_delivery else "EXECUTED")
    dispositions = {
        Directive.REPAIR: "FEEDBACK_APPLIED",
        Directive.REPLY: "IGNORED",
        Directive.WAIT: "IGNORED",
    }
    assert decision.review_disposition == dispositions.get(action, "NEEDS_CLASSIFICATION")
