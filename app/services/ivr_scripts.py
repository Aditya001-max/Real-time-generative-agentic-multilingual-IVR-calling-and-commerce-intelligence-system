"""
Block 8 — User Interaction (IVR Flows).

Two IVR scripts, exactly as in the architecture diagram:

  A. Order Confirmation Call
     Press 1 — Confirm Order
     Press 2 — Need Help

  B. Rejection Handling Call
     Press 1 — Accept Order
     Press 2 — Cancel Order
     Press 3 — Need Help

Now language-aware: pass `lang` (one of the 9 supported codes) and the
script returns translated welcome / prompt / fallback strings from the
PROMPTS table. If `lang` is omitted, defaults to English — so all
existing call sites keep working unchanged.

Speech aliases are recognised so the Webhook Handler accepts both
DTMF and natural-language responses (AI Voice / Speech system).
"""
from dataclasses import dataclass

from app.services.greetings import DEFAULT_LANGUAGE
from app.services.translations import (
    P_CONFIRM_FALLBACK,
    P_CONFIRM_PROMPT,
    P_CONFIRM_WELCOME,
    P_REJECT_FALLBACK,
    P_REJECT_PROMPT,
    P_REJECT_WELCOME,
    t,
)


@dataclass(frozen=True)
class IVRScript:
    welcome_message: str
    prompt: str
    valid_digits: tuple[str, ...]
    speech_hints: tuple[str, ...]
    fallback_message: str = "Sorry, I didn't catch that. Goodbye."


# ---------------------------------------------------------------------------
# Speech recognition — DTMF aliases per language.
#
# We send keywords in BOTH English and the user's chosen language as
# recognition hints, and accept either when normalizing. This keeps things
# robust for code-mixed speech ("cancel kar do" / "confirm please") common
# in Indian English usage.
# ---------------------------------------------------------------------------

SPEECH_TO_DIGIT_CONFIRMATION_BASE: dict[str, dict[str, str]] = {
    "en": {
        "confirm": "1", "yes": "1", "ok": "1", "okay": "1",
        "help": "2", "agent": "2",
    },
    "hi": {
        "haan": "1", "han": "1", "haa": "1", "theek": "1",
        "madad": "2", "sahayata": "2",
    },
    "ta": {"aam": "1", "sari": "1", "uthavi": "2"},
    "te": {"avunu": "1", "sare": "1", "sahayam": "2"},
    "kn": {"howdu": "1", "sari": "1", "sahaya": "2"},
    "ml": {"athe": "1", "sari": "1", "sahayam": "2"},
    "bn": {"hyan": "1", "thik": "1", "sahajjo": "2"},
    "mr": {"hoy": "1", "barobar": "1", "madat": "2"},
    "gu": {"haa": "1", "barabar": "1", "madad": "2"},
}

SPEECH_TO_DIGIT_REJECTION_BASE: dict[str, dict[str, str]] = {
    "en": {
        "accept": "1", "redeliver": "1", "yes": "1",
        "cancel": "2", "no": "2",
        "help": "3", "agent": "3",
    },
    "hi": {
        "haan": "1", "phir": "1",
        "radd": "2", "cancel": "2",
        "madad": "3",
    },
    "ta": {"aam": "1", "raddu": "2", "uthavi": "3"},
    "te": {"avunu": "1", "raddu": "2", "sahayam": "3"},
    "kn": {"howdu": "1", "radd": "2", "sahaya": "3"},
    "ml": {"athe": "1", "radd": "2", "sahayam": "3"},
    "bn": {"hyan": "1", "batil": "2", "sahajjo": "3"},
    "mr": {"hoy": "1", "radd": "2", "madat": "3"},
    "gu": {"haa": "1", "radd": "2", "madad": "3"},
}


def _build_speech_table(call_type: str, lang: str) -> dict[str, str]:
    """Combine English aliases + chosen-language aliases into one lookup table."""
    base = (
        SPEECH_TO_DIGIT_CONFIRMATION_BASE
        if call_type == "CONFIRMATION"
        else SPEECH_TO_DIGIT_REJECTION_BASE
    )
    table = dict(base.get("en", {}))  # always include English
    if lang != "en":
        table.update(base.get(lang, {}))
    return table


def script_for(call_type: str, lang: str = DEFAULT_LANGUAGE) -> IVRScript:
    """Build an IVRScript for the given call type and language."""
    if call_type == "CONFIRMATION":
        speech_table = _build_speech_table("CONFIRMATION", lang)
        return IVRScript(
            welcome_message=t(P_CONFIRM_WELCOME, lang),
            prompt=t(P_CONFIRM_PROMPT, lang),
            fallback_message=t(P_CONFIRM_FALLBACK, lang),
            valid_digits=("1", "2"),
            speech_hints=tuple(speech_table.keys()),
        )
    if call_type == "REJECTION":
        speech_table = _build_speech_table("REJECTION", lang)
        return IVRScript(
            welcome_message=t(P_REJECT_WELCOME, lang),
            prompt=t(P_REJECT_PROMPT, lang),
            fallback_message=t(P_REJECT_FALLBACK, lang),
            valid_digits=("1", "2", "3"),
            speech_hints=tuple(speech_table.keys()),
        )
    raise ValueError(f"Unknown call_type: {call_type}")


# ---------------------------------------------------------------------------
# Backwards-compat: existing tests / callers that import the constants
# directly still get the English script.
# ---------------------------------------------------------------------------
CONFIRMATION_SCRIPT = script_for("CONFIRMATION", DEFAULT_LANGUAGE)
REJECTION_SCRIPT = script_for("REJECTION", DEFAULT_LANGUAGE)

SPEECH_TO_DIGIT_CONFIRMATION = SPEECH_TO_DIGIT_CONFIRMATION_BASE["en"]
SPEECH_TO_DIGIT_REJECTION = SPEECH_TO_DIGIT_REJECTION_BASE["en"]


def normalize_input(
    call_type: str,
    digits: str | None,
    speech: str | None,
    lang: str = DEFAULT_LANGUAGE,
) -> str | None:
    """Convert raw DTMF / speech into a canonical digit ('1','2','3') or None.

    DTMF always wins over speech. Speech is matched against the combined
    English + chosen-language alias table, on the FIRST word of the
    transcript (handles "cancel please", "confirm kar do", etc).
    """
    if digits and digits.strip():
        return digits.strip()
    if speech:
        token = speech.strip().lower().split()[0] if speech.strip() else ""
        table = _build_speech_table(call_type, lang)
        return table.get(token)
    return None
