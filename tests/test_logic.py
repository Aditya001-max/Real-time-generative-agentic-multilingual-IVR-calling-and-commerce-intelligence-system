"""Pure-logic tests that don't need Ozonetel or Redis."""
from app.services.decision_engine import decide
from app.services.ivr_scripts import normalize_input, script_for
from app.workers.retry_tasks import MAX_ATTEMPTS, RETRY_DELAYS_SEC


def test_decide_order_placed():
    d = decide("ORDER_PLACED")
    assert d.proceed is True
    assert d.call_type == "CONFIRMATION"


def test_decide_order_rejected():
    d = decide("ORDER_REJECTED")
    assert d.proceed is True
    assert d.call_type == "REJECTION"


def test_decide_unknown_event():
    d = decide("RANDOM_EVENT")
    assert d.proceed is False


def test_confirmation_script_has_two_options():
    s = script_for("CONFIRMATION")
    assert s.valid_digits == ("1", "2")


def test_rejection_script_has_three_options():
    s = script_for("REJECTION")
    assert s.valid_digits == ("1", "2", "3")


def test_normalize_input_dtmf_takes_precedence():
    assert normalize_input("CONFIRMATION", "1", "help") == "1"


def test_normalize_input_speech_confirm():
    assert normalize_input("CONFIRMATION", None, "confirm") == "1"


def test_normalize_input_speech_cancel():
    assert normalize_input("REJECTION", None, "cancel please") == "2"


def test_normalize_input_speech_help_rejection():
    assert normalize_input("REJECTION", None, "help") == "3"


def test_normalize_input_unknown():
    assert normalize_input("CONFIRMATION", None, "blahblah") is None


# ---------------------------------------------------------------------------
# Retry engine — same schedule applies to BOTH CONFIRMATION and REJECTION
# ---------------------------------------------------------------------------

def test_retry_schedule_is_three_attempts_at_two_hour_intervals():
    """Spec: at most 3 calls per (order, call_type), spaced by 2 hours.
    Attempt 1 fires immediately, attempt 2 after 2h, attempt 3 after 2 more."""
    assert MAX_ATTEMPTS == 3
    assert RETRY_DELAYS_SEC == {1: 0, 2: 7200, 3: 7200}


def test_retry_schedule_does_not_distinguish_call_type():
    """The retry engine treats CONFIRMATION and REJECTION identically — the
    `call_type` argument is passed through to the call manager but never
    consulted when picking delays. Verifies regression: a future change
    that special-cases call_type for delays would force this test to be
    rewritten intentionally."""
    import inspect
    from app.workers import retry_tasks
    src = inspect.getsource(retry_tasks)
    # No conditional on call_type when picking the delay.
    assert "RETRY_DELAYS_SEC[call_type]" not in src
    assert 'if call_type ==' not in src
