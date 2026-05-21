"""Tests for the multi-language IVR feature (Ozonetel KooKoo edition).

Covers:
  • greetings module — digit/lang/locale mappings
  • translations table — every prompt has all 9 languages
  • ivr_scripts.script_for — returns translated content
  • normalize_input — accepts both English and per-language speech
  • webhook — language picker (NewCall + GotDTMF), no-input, returning
    caller skip, region-aware menu shape
  • action_engine — handlers return translated messages

The webhook tests assert KooKoo XML output (<playtext>, <playaudio>,
<collectdtmf>, <gotourl>) — NOT TwiML. The /webhook/language-select
route no longer exists; language selection is handled inline by
/webhook/voice-start with event=GotDTMF.
"""
from __future__ import annotations

import time

from fastapi.testclient import TestClient

from app.services.greetings import (
    COMPANY_NAME,
    DEFAULT_LANGUAGE,
    DIGIT_TO_LANG,
    GREETING_PARTS,
    LANGUAGE_MENU_LINES,
    SUPPORTED_LANGUAGES,
    bcp47_locale_for,
    lang_for_digit,
)
from app.services.ivr_scripts import normalize_input, script_for
from app.services.translations import PROMPTS, all_prompt_strings_for, t


# ---------------------------------------------------------------------------
# greetings module
# ---------------------------------------------------------------------------

def test_supports_exactly_nine_languages():
    assert len(SUPPORTED_LANGUAGES) == 9
    assert "en" in SUPPORTED_LANGUAGES
    assert "hi" in SUPPORTED_LANGUAGES


def test_menu_has_one_entry_per_supported_language():
    assert len(LANGUAGE_MENU_LINES) == len(SUPPORTED_LANGUAGES)
    digits = [d for d, _, _, _ in LANGUAGE_MENU_LINES]
    assert digits == ["1", "2", "3", "4", "5", "6", "7", "8", "9"]


def test_lang_for_digit_known():
    assert lang_for_digit("1") == "en"
    assert lang_for_digit("2") == "hi"
    assert lang_for_digit("3") == "ta"
    assert lang_for_digit("9") == "gu"


def test_lang_for_digit_invalid_defaults_to_english():
    assert lang_for_digit("0") == "en"
    assert lang_for_digit("*") == "en"
    assert lang_for_digit(None) == "en"
    assert lang_for_digit("") == "en"


def test_bcp47_locale_mapping():
    assert bcp47_locale_for("en") == "en-IN"
    assert bcp47_locale_for("hi") == "hi-IN"
    assert bcp47_locale_for("ta") == "ta-IN"
    # Unknown lang falls back to English locale
    assert bcp47_locale_for("xx") == "en-IN"


def test_greeting_parts_have_brand_and_trailing():
    for call_type in ("CONFIRMATION", "REJECTION"):
        parts = GREETING_PARTS[call_type]
        assert "prefix" in parts
        assert "trailing" in parts
        assert parts["prefix"]
        assert parts["trailing"]


def test_company_name_present():
    assert COMPANY_NAME == "Divine Hindu"


# ---------------------------------------------------------------------------
# translations table
# ---------------------------------------------------------------------------

def test_every_prompt_has_all_nine_languages():
    """No translation gaps allowed — the whole point of the feature."""
    for prompt_id, table in PROMPTS.items():
        missing = set(SUPPORTED_LANGUAGES) - set(table.keys())
        assert not missing, f"prompt {prompt_id!r} missing languages: {missing}"


def test_translation_lookup_falls_back_to_english_on_missing():
    assert t("nonexistent_prompt", "hi") == ""
    fake_lang = "zz"
    eng = t("order_confirmed", "en")
    assert t("order_confirmed", fake_lang) == eng


def test_prompt_strings_helper_returns_one_per_prompt():
    strings_en = all_prompt_strings_for("en")
    strings_hi = all_prompt_strings_for("hi")
    assert len(strings_en) == len(PROMPTS)
    assert len(strings_hi) == len(PROMPTS)
    assert strings_en != strings_hi


# ---------------------------------------------------------------------------
# ivr_scripts — language-aware
# ---------------------------------------------------------------------------

def test_script_for_default_is_english_backward_compat():
    s = script_for("CONFIRMATION")
    assert "your recent order" in s.welcome_message.lower()
    assert s.valid_digits == ("1", "2")


def test_script_for_hindi_returns_hindi_strings():
    s = script_for("CONFIRMATION", "hi")
    assert s.welcome_message != script_for("CONFIRMATION", "en").welcome_message
    assert any("ऀ" <= ch <= "ॿ" for ch in s.welcome_message)


def test_script_for_tamil_returns_tamil_strings():
    s = script_for("REJECTION", "ta")
    assert any("஀" <= ch <= "௿" for ch in s.welcome_message)
    assert s.valid_digits == ("1", "2", "3")


def test_speech_hints_include_english_in_every_language():
    """Hindi caller saying 'cancel' (code-mixed Hinglish) must still work."""
    s_hi = script_for("REJECTION", "hi")
    assert "cancel" in s_hi.speech_hints
    assert "radd" in s_hi.speech_hints
    s_en = script_for("REJECTION", "en")
    assert "cancel" in s_en.speech_hints


# ---------------------------------------------------------------------------
# normalize_input — language-aware
# ---------------------------------------------------------------------------

def test_normalize_input_english_unchanged():
    assert normalize_input("CONFIRMATION", None, "confirm") == "1"
    assert normalize_input("REJECTION", None, "cancel please") == "2"
    assert normalize_input("CONFIRMATION", "1", "help") == "1"  # DTMF wins


def test_normalize_input_hindi_native_word():
    assert normalize_input("CONFIRMATION", None, "haan", lang="hi") == "1"
    assert normalize_input("REJECTION", None, "radd", lang="hi") == "2"


def test_normalize_input_tamil_native_word():
    assert normalize_input("CONFIRMATION", None, "aam", lang="ta") == "1"
    assert normalize_input("REJECTION", None, "raddu", lang="ta") == "2"


def test_normalize_input_english_works_in_any_language():
    assert normalize_input("REJECTION", None, "cancel", lang="hi") == "2"
    assert normalize_input("REJECTION", None, "cancel", lang="ta") == "2"
    assert normalize_input("CONFIRMATION", None, "yes", lang="bn") == "1"


def test_normalize_input_unknown_returns_none():
    assert normalize_input("CONFIRMATION", None, "blahblah", lang="hi") is None
    assert normalize_input("REJECTION", None, "", lang="ta") is None


# ---------------------------------------------------------------------------
# Webhook integration tests (Ozonetel KooKoo XML)
#
# Helpers that seed an Order (FK requirement on Postgres) and a CallLog,
# then exercise voice-start/voice with the appropriate event= parameter.
# ---------------------------------------------------------------------------

def _client():
    from app.main import app
    return TestClient(app)


def _seed(state: str | None = None, call_type: str = "CONFIRMATION", lang: str | None = None) -> int:
    """Insert Order + User + CallLog and return the call_id.

    Order/User get committed first so the CallLog FK check passes on Postgres.
    """
    from app.db.session import SessionLocal
    from app.models import CallLog, Order, User
    db = SessionLocal()
    try:
        oid = int(time.time() * 1000) % 10**8
        phone = f"+9199990{int(time.time()*1000)%100000:05d}"
        if not db.query(Order).filter(Order.order_id == oid).first():
            db.add(Order(order_id=oid, user_phone=phone, state=state or None))
        if not db.query(User).filter(User.phone_number == phone).first():
            user = User(phone_number=phone)
            if lang:
                user.preferred_language = lang
            db.add(user)
        db.commit()  # commit parent rows so the CallLog FK passes
        cl = CallLog(
            order_id=oid,
            user_phone=phone,
            call_type=call_type,
            attempt_no=1,
            status="INITIATED",
            delivery_state=state,
        )
        db.add(cl)
        db.commit()
        return cl.call_id
    finally:
        db.close()


def _count_menu_items(body: str) -> int:
    """Count <playtext>/<playaudio> entries inside the <collectdtmf> block."""
    start = body.find("<collectdtmf")
    end = body.find("</collectdtmf>")
    if start == -1 or end == -1:
        return 0
    inner = body[start:end]
    return inner.count("<playtext") + inner.count("<playaudio")


def test_voice_start_first_time_caller_plays_picker():
    """First-time caller: voice-start returns the language menu in KooKoo XML."""
    with _client() as client:
        cid = _seed()
        r = client.post(f"/webhook/voice-start?call_id={cid}&call_type=CONFIRMATION&event=NewCall")
        assert r.status_code == 200
        body = r.text
        # KooKoo response root
        assert "<response>" in body
        # Voice payload present — either inline TTS (<playtext ...> path,
        # used when AI voice is off) or pre-rendered audio (<playaudio>
        # against /audio/<hash>.mp3, used when USE_AI_VOICE=true).
        assert ("<playtext" in body) or ("<playaudio>" in body)
        # Default (no state, no circle hint) trims to (English, Hindi).
        # All 9 was abandoned because real callers hung up before the
        # picker finished announcing.
        assert _count_menu_items(body) == 2
        # No-input fallback redirect
        assert "/webhook/no-input" in body


def test_voice_start_returning_caller_skips_picker(monkeypatch):
    """Returning caller with preferred_language set: redirects to /voice."""
    from app.core.config import settings as _settings
    monkeypatch.setattr(_settings, "FORCE_LANGUAGE_PICKER", False)
    with _client() as client:
        cid = _seed(lang="ta")
        r = client.post(f"/webhook/voice-start?call_id={cid}&call_type=CONFIRMATION&event=NewCall")
        assert r.status_code == 200
        body = r.text
        # Should NOT play the menu — should redirect straight to /voice
        assert "<gotourl>" in body
        assert "/webhook/voice?" in body
        assert "lang=ta" in body
        # Menu lines should NOT appear
        assert "For English, press 1" not in body


def test_voice_start_gotdtmf_saves_preference():
    """voice-start with event=GotDTMF persists chosen language and redirects to /voice."""
    with _client() as client:
        cid = _seed(state="TN")  # TN gets {en, hi, ta} — pressing 3 selects ta
        r = client.post(
            f"/webhook/voice-start?call_id={cid}&call_type=REJECTION"
            f"&event=GotDTMF&data=3"
        )
        assert r.status_code == 200
        assert "<gotourl>" in r.text
        assert "lang=ta" in r.text
        assert "/webhook/voice?" in r.text

        # And the User row should have preferred_language updated
        from app.db.session import SessionLocal
        from app.models import CallLog, User
        db = SessionLocal()
        try:
            cl = db.get(CallLog, cid)
            user = db.query(User).filter(User.phone_number == cl.user_phone).first()
            assert user.preferred_language == "ta"
            assert cl.language == "ta"
        finally:
            db.close()


def test_voice_start_gotdtmf_invalid_digit_defaults_to_english():
    with _client() as client:
        cid = _seed(state="TN")
        r = client.post(
            f"/webhook/voice-start?call_id={cid}&call_type=CONFIRMATION"
            f"&event=GotDTMF&data=0"
        )
        assert r.status_code == 200
        assert "lang=en" in r.text


def test_no_input_defaults_to_english():
    with _client() as client:
        cid = _seed()
        r = client.post(f"/webhook/no-input?call_id={cid}&call_type=CONFIRMATION")
        assert r.status_code == 200
        assert "lang=en" in r.text
        assert "<gotourl>" in r.text


def test_voice_endpoint_renders_in_chosen_language():
    """The main IVR endpoint speaks Hindi when lang=hi — either via the
    self-hosted TTS chain (<playaudio>https://.../audio/<hash>.mp3</playaudio>)
    or, if AI voice is off, via KooKoo Google TTS (<playtext type="ggl">)."""
    with _client() as client:
        cid = _seed()
        r = client.post(
            f"/webhook/voice?call_id={cid}&call_type=CONFIRMATION&lang=hi&event=NewCall"
        )
        assert r.status_code == 200
        body = r.text
        used_self_hosted = "<playaudio>" in body and "/audio/" in body
        used_google_tts = '<playtext type="ggl" lang="hi-IN">' in body
        assert used_self_hosted or used_google_tts
        # collectdtmf block present
        assert "<collectdtmf" in body


def test_voice_endpoint_unsupported_lang_speaks_via_audio_or_google_tts():
    """Tamil isn't covered by KooKoo's native TTS, so we either pre-render
    it ourselves (<playaudio> from /audio/<hash>.mp3, when USE_AI_VOICE=true)
    or fall back to KooKoo's Google TTS (<playtext type="ggl" lang="ta-IN">).
    Either path is acceptable — what matters is the caller hears Tamil."""
    with _client() as client:
        cid = _seed()
        r = client.post(
            f"/webhook/voice?call_id={cid}&call_type=REJECTION&lang=ta&event=NewCall"
        )
        assert r.status_code == 200
        body = r.text
        used_self_hosted = "<playaudio>" in body and "/audio/" in body
        used_google_tts = '<playtext type="ggl" lang="ta-IN">' in body
        assert used_self_hosted or used_google_tts
        # No legacy native <playtext lang="EN"> fallback for Tamil prompts.
        assert '<playtext lang="EN">' not in body


# ---------------------------------------------------------------------------
# Region-aware picker (state → menu shape)
# ---------------------------------------------------------------------------

def test_voice_start_gujarat_shows_three_options():
    with _client() as client:
        cid = _seed(state="GJ")
        r = client.post(f"/webhook/voice-start?call_id={cid}&call_type=CONFIRMATION&event=NewCall")
        assert _count_menu_items(r.text) == 3


def test_voice_start_tamil_nadu_shows_three_options():
    with _client() as client:
        cid = _seed(state="TN")
        r = client.post(f"/webhook/voice-start?call_id={cid}&call_type=CONFIRMATION&event=NewCall")
        assert _count_menu_items(r.text) == 3


def test_voice_start_uttar_pradesh_shows_two_options():
    with _client() as client:
        cid = _seed(state="UP")
        r = client.post(f"/webhook/voice-start?call_id={cid}&call_type=CONFIRMATION&event=NewCall")
        assert _count_menu_items(r.text) == 2


def test_voice_start_bihar_shows_two_options():
    with _client() as client:
        cid = _seed(state="BR")
        r = client.post(f"/webhook/voice-start?call_id={cid}&call_type=CONFIRMATION&event=NewCall")
        assert _count_menu_items(r.text) == 2


def test_voice_start_unknown_state_shows_default_two_options():
    """Unknown state code → (en, hi) default. We never spray all 9
    languages at the caller; that turned the picker into a 30-second wait."""
    with _client() as client:
        cid = _seed(state="ZZ")
        r = client.post(f"/webhook/voice-start?call_id={cid}&call_type=CONFIRMATION&event=NewCall")
        assert _count_menu_items(r.text) == 2


def test_voice_start_no_state_shows_default_two_options():
    with _client() as client:
        cid = _seed(state=None)
        r = client.post(f"/webhook/voice-start?call_id={cid}&call_type=CONFIRMATION&event=NewCall")
        assert _count_menu_items(r.text) == 2


def test_voice_start_kookoo_circle_param_widens_menu():
    """When the event payload didn't carry a state, we pull KooKoo's
    `circle=` query string off the inbound webhook and use it to resolve
    a regional 3rd language. UTTAR PRADESH (E) → UP → still (en, hi),
    GUJARAT → GJ → (en, hi, gu)."""
    with _client() as client:
        cid = _seed(state=None)
        # Tamil Nadu circle should widen the menu to 3 options.
        r = client.post(
            f"/webhook/voice-start?call_id={cid}&call_type=CONFIRMATION&event=NewCall&circle=TAMIL+NADU"
        )
        assert _count_menu_items(r.text) == 3
        # Gujarat circle should also widen to 3 options.
        cid2 = _seed(state=None)
        r2 = client.post(
            f"/webhook/voice-start?call_id={cid2}&call_type=CONFIRMATION&event=NewCall&circle=GUJARAT"
        )
        assert _count_menu_items(r2.text) == 3
        # UP-East stays at 2 options (Hindi-belt, no native 3rd lang).
        cid3 = _seed(state=None)
        r3 = client.post(
            f"/webhook/voice-start?call_id={cid3}&call_type=CONFIRMATION&event=NewCall&circle=UTTAR+PRADESH+(E)"
        )
        assert _count_menu_items(r3.text) == 2


# ---------------------------------------------------------------------------
# Action engine — translated responses
# ---------------------------------------------------------------------------

def test_action_engine_returns_translated_confirmation():
    with _client():
        from app.db.session import SessionLocal
        from app.services.action_engine import handle_confirmation_response
        db = SessionLocal()
        try:
            msg_en, _ = handle_confirmation_response(db, order_id=99001, digit="1", lang="en")
            msg_hi, _ = handle_confirmation_response(db, order_id=99002, digit="1", lang="hi")
            assert msg_en != msg_hi
            assert any("ऀ" <= ch <= "ॿ" for ch in msg_hi)
        finally:
            db.close()


def test_action_engine_returns_translated_cancel():
    with _client():
        from app.db.session import SessionLocal
        from app.services.action_engine import handle_rejection_response
        db = SessionLocal()
        try:
            msg_ta, _ = handle_rejection_response(db, order_id=99003, digit="2", lang="ta")
            assert any("஀" <= ch <= "௿" for ch in msg_ta)
        finally:
            db.close()
