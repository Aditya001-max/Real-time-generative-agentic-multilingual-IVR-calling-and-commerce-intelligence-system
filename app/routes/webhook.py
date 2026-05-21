"""
Block 6 — Webhook Handler (Ozonetel KooKoo).

Ozonetel calls these endpoints during the call:

  GET/POST /webhook/voice-start    — Entry point. Handles BOTH
                                     event=NewCall (play picker) and
                                     event=GotDTMF (language picked).
  GET/POST /webhook/no-input       — Default to English on no DTMF.
  GET/POST /webhook/voice          — Main IVR. Handles event=NewCall
                                     (play prompt) and event=GotDTMF
                                     (run action engine).
  GET/POST /webhook/status         — Lifecycle/status callbacks.

KooKoo flow vs Twilio:
  • Twilio uses a different action URL per Gather. KooKoo re-invokes
    THE SAME URL with `event=GotDTMF&data=<digit>` after a collectdtmf
    block resolves. So our handlers branch on the `event` query/form
    parameter rather than living at separate paths.
  • Twilio's <Say>/<Gather> become KooKoo's <playtext>/<collectdtmf> —
    handled by the KooKooResponse helper in app/services/kookoo_xml.py.

Language coverage: KooKoo native TTS only speaks EN/HI/TE/KA. The other
5 languages in our menu (ta, ml, bn, mr, gu) are served as pre-recorded
WAV files via <playaudio> from /audio/<key>.wav. See scripts/generate_audio.py.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import get_db
from app.models import AuditLog, CallLog, User
from app.services import action_engine
from app.services.greetings import (
    COMPANY_NAME,
    DEFAULT_LANGUAGE,
    GREETING_PARTS,
    LANGUAGE_MENU_LINES,
    MENU_TEXT_BY_LANG,
    SUPPORTED_LANGUAGES,
)
from app.services.help_router import route_help_request
from app.services.ivr_scripts import normalize_input, script_for
from app.services.kookoo_xml import (
    KooKooResponse,
    google_tts_locale_for,
    google_tts_voice_for,
    kookoo_lang_for,
    kookoo_supports,
)
from app.services.regions import menu_for_state, state_from_circle
from app.services.translations import P_NO_INPUT, t
from app.services.tts import tts

log = get_logger(__name__)

router = APIRouter(prefix="/webhook", tags=["webhook"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _xml(response: KooKooResponse) -> Response:
    return Response(content=response.to_xml(), media_type="application/xml")


def _safe_lang(value: str | None) -> str:
    if value and value in SUPPORTED_LANGUAGES:
        return value
    return DEFAULT_LANGUAGE


def _audio_base() -> str:
    """Public base URL for pre-recorded audio (lang-specific menu lines)."""
    return (settings.AUDIO_PUBLIC_BASE or f"{settings.BASE_URL}/audio").rstrip("/")


def _audio_url(key: str) -> str:
    return f"{_audio_base()}/{key}.wav"


def _lang_voice(response: KooKooResponse, text: str, lang: str, audio_key: str) -> None:
    """Emit speech for `text` in `lang` through KooKoo Google TTS using a
    premium Wavenet/Neural2 voice (Ozonetel Pro feature).

    Provider priority (first match wins):
      1. Self-hosted TTS chain (USE_AI_VOICE=true) — synth_url() returns
         a public MP3 we host; KooKoo plays via <playaudio>.
      2. KooKoo Google TTS with a premium voice — <playtext type="ggl"
         lang="xx-IN" voice="xx-IN-Wavenet-D">. Default path. Covers all
         9 languages with a natural-sounding voice on Pro accounts.
      3. Last-resort English <playtext> — only reached if our lang isn't
         in the Google locale map (which would be a code-side bug).
    `audio_key` is kept for back-compat with old call sites."""
    del audio_key
    audio_url = tts.synth_url(text, lang)
    if audio_url:
        response.playaudio(audio_url)
        return
    locale = google_tts_locale_for(lang)
    if locale:
        voice = google_tts_voice_for(lang) if settings.KOOKOO_USE_WAVENET else ""
        response.playtext_google(text, locale=locale, voice=voice)
        return
    response.playtext(text, lang="EN")


def _lang_voice_in_collect(
    response: KooKooResponse, text: str, lang: str, audio_key: str
) -> None:
    del audio_key
    audio_url = tts.synth_url(text, lang)
    if audio_url:
        response.playaudio_in_collect(audio_url)
        return
    locale = google_tts_locale_for(lang)
    if locale:
        voice = google_tts_voice_for(lang) if settings.KOOKOO_USE_WAVENET else ""
        response.playtext_google_in_collect(text, locale=locale, voice=voice)
        return
    response.playtext_in_collect(text, lang="EN")


async def _read_event(request: Request) -> tuple[str, str]:
    """Pull KooKoo's (event, data) from query OR form params."""
    qp = dict(request.query_params)
    event = qp.get("event") or ""
    data = qp.get("data") or ""
    if not event or not data:
        try:
            form = await request.form()
            event = event or (form.get("event") or "")
            data = data or (form.get("data") or "")
        except Exception:  # noqa: BLE001
            pass
    # Default: first contact = NewCall (Ozonetel does send event= for NewCall too)
    if not event:
        event = "NewCall"
    return event, data


def _resolve_state(request: Request, call: CallLog | None) -> str | None:
    """Best-effort 2-letter state code for the current caller.

    Priority:
      1. call.delivery_state — set by /event/ payload when the order
         was placed (most authoritative, comes from CRM/OMS).
      2. KooKoo's `circle` query parameter — telecom circle of the
         calling SIM (e.g. "UTTAR PRADESH (E)" → "UP").

    The resolved value is persisted onto CallLog.delivery_state so the
    follow-up GotDTMF callback sees the same state without re-parsing.
    """
    if call and call.delivery_state:
        return call.delivery_state
    circle = request.query_params.get("circle") or ""
    state = state_from_circle(circle)
    if state and call and not call.delivery_state:
        call.delivery_state = state
    return state


# ---------------------------------------------------------------------------
# /voice-start — language picker + first DTMF
# ---------------------------------------------------------------------------

@router.api_route("/voice-start", methods=["GET", "POST"])
async def voice_start(request: Request, db: Session = Depends(get_db)) -> Response:
    params = dict(request.query_params)
    call_id = int(params.get("call_id", 0))
    call_type = params.get("call_type", "CONFIRMATION")
    event, data = await _read_event(request)

    log.info(
        "voice-start: call_id=%s call_type=%s event=%s data=%r",
        call_id, call_type, event, data,
    )

    response = KooKooResponse()
    call = db.get(CallLog, call_id)
    user = (
        db.query(User).filter(User.phone_number == call.user_phone).first()
        if call else None
    )

    # ----- Branch A: GotDTMF — user pressed a digit on the language picker -----
    if event == "GotDTMF":
        state = _resolve_state(request, call)
        allowed_langs = menu_for_state(state)
        visible = [
            lang_code
            for _digit, lang_code, _locale, _menu_text in LANGUAGE_MENU_LINES
            if lang_code in allowed_langs
        ]
        try:
            idx = int(data.strip()) - 1
            if idx < 0 or idx >= len(visible):
                raise IndexError
            chosen_lang = visible[idx]
        except (TypeError, ValueError, IndexError):
            chosen_lang = DEFAULT_LANGUAGE

        log.info(
            "language-select: call_id=%s state=%s digit=%r visible=%s -> lang=%s",
            call_id, state, data, visible, chosen_lang,
        )

        if call:
            call.language = chosen_lang
            if user:
                user.preferred_language = chosen_lang
        db.add(AuditLog(
            event_type="LANGUAGE_SELECTED",
            description=f"call_id={call_id} digit={data} lang={chosen_lang}",
            source="webhook",
        ))
        db.commit()

        response.gotourl(
            f"{settings.BASE_URL}/webhook/voice"
            f"?call_id={call_id}&call_type={call_type}&lang={chosen_lang}"
        )
        return _xml(response)

    # ----- Branch B: returning caller with saved language — skip picker -----
    if (
        not settings.FORCE_LANGUAGE_PICKER
        and user
        and user.preferred_language
        and user.preferred_language in SUPPORTED_LANGUAGES
    ):
        if call:
            call.language = user.preferred_language
            db.commit()
        log.info(
            "voice-start: skipping picker, user has lang=%s",
            user.preferred_language,
        )
        response.gotourl(
            f"{settings.BASE_URL}/webhook/voice?call_id={call_id}"
            f"&call_type={call_type}&lang={user.preferred_language}"
        )
        return _xml(response)

    # ----- Branch C: NewCall — first time caller, play picker -----
    parts = GREETING_PARTS.get(call_type, GREETING_PARTS["CONFIRMATION"])
    full_greeting = parts["prefix"] + COMPANY_NAME + parts["trailing"]
    # Route the greeting through the TTS chain so it is also served as a
    # <playaudio> URL when AI voice is enabled — keeps the entire call
    # consistent (no half-TTS-half-playaudio mix that would change accent
    # mid-sentence) and works on KooKoo accounts where <playtext> is off.
    _lang_voice(response, full_greeting, "en", audio_key="brand_greeting_en")

    state = _resolve_state(request, call)
    allowed_langs = menu_for_state(state)
    log.info(
        "voice-start picker: call_id=%s state=%s langs=%s",
        call_id, state, allowed_langs,
    )

    response.start_collect_dtmf(length=1, timeout_ms=8000)
    visible_lines = [
        (lang_code, locale)
        for _digit, lang_code, locale, _menu_text in LANGUAGE_MENU_LINES
        if lang_code in allowed_langs
    ]
    for new_digit, (lang_code, _locale) in enumerate(visible_lines, start=1):
        text = MENU_TEXT_BY_LANG[lang_code].format(digit=new_digit)
        _lang_voice_in_collect(
            response, text, lang_code, audio_key=f"menu_{lang_code}_{new_digit}",
        )
    response.end_collect_dtmf()

    # No-input fallback
    response.gotourl(
        f"{settings.BASE_URL}/webhook/no-input?call_id={call_id}&call_type={call_type}"
    )

    db.add(AuditLog(
        event_type="LANGUAGE_PICKER_PLAYED",
        description=f"call_id={call_id} call_type={call_type}",
        source="webhook",
    ))
    db.commit()
    return _xml(response)


# ---------------------------------------------------------------------------
# /no-input — fallback when language picker times out
# ---------------------------------------------------------------------------

@router.api_route("/no-input", methods=["GET", "POST"])
async def no_input(request: Request, db: Session = Depends(get_db)) -> Response:
    """KooKoo invokes this URL after the <collectdtmf> block ends.

    Despite the name, it fires in BOTH cases: timeout (no digit pressed)
    AND digit-pressed. KooKoo passes the pressed digit as `data=N` on the
    query string. If `data` is present we treat it as a language choice
    and route through the same logic as voice-start's Branch A. If `data`
    is empty / missing, we fall back to English.
    """
    params = dict(request.query_params)
    call_id = int(params.get("call_id", 0))
    call_type = params.get("call_type", "CONFIRMATION")
    _event, data = await _read_event(request)

    call = db.get(CallLog, call_id)

    # Branch A: user actually pressed a digit on the picker.
    if data and data.strip():
        state = _resolve_state(request, call)
        allowed_langs = menu_for_state(state)
        visible = [
            lang_code
            for _digit, lang_code, _locale, _menu_text in LANGUAGE_MENU_LINES
            if lang_code in allowed_langs
        ]
        try:
            idx = int(data.strip()) - 1
            if idx < 0 or idx >= len(visible):
                raise IndexError
            chosen_lang = visible[idx]
        except (TypeError, ValueError, IndexError):
            chosen_lang = DEFAULT_LANGUAGE

        log.info(
            "no-input(digit): call_id=%s state=%s digit=%r visible=%s -> lang=%s",
            call_id, state, data, visible, chosen_lang,
        )

        if call:
            call.language = chosen_lang
            user = (
                db.query(User).filter(User.phone_number == call.user_phone).first()
            )
            if user:
                user.preferred_language = chosen_lang
        db.add(AuditLog(
            event_type="LANGUAGE_SELECTED",
            description=f"call_id={call_id} digit={data} lang={chosen_lang}",
            source="webhook",
        ))
        db.commit()

        response = KooKooResponse()
        response.gotourl(
            f"{settings.BASE_URL}/webhook/voice"
            f"?call_id={call_id}&call_type={call_type}&lang={chosen_lang}"
        )
        return _xml(response)

    # Branch B: real no-input — caller stayed silent on the picker.
    log.info("no-input(silent): call_id=%s -> defaulting to en", call_id)
    if call:
        call.language = DEFAULT_LANGUAGE
        db.commit()

    response = KooKooResponse()
    response.gotourl(
        f"{settings.BASE_URL}/webhook/voice"
        f"?call_id={call_id}&call_type={call_type}&lang={DEFAULT_LANGUAGE}"
    )
    return _xml(response)


# ---------------------------------------------------------------------------
# /voice — main IVR. NewCall plays prompt, GotDTMF runs action engine.
# ---------------------------------------------------------------------------

@router.api_route("/voice", methods=["GET", "POST"])
async def voice(request: Request, db: Session = Depends(get_db)) -> Response:
    params = dict(request.query_params)
    call_id = int(params.get("call_id", 0))
    call_type = params.get("call_type", "CONFIRMATION")
    lang = _safe_lang(params.get("lang"))
    event, data = await _read_event(request)

    log.info(
        "voice: call_id=%s call_type=%s lang=%s event=%s data=%r",
        call_id, call_type, lang, event, data,
    )

    # Post-DTMF callback fires when KooKoo calls our gotourl after the
    # collectdtmf block resolves (either with a digit press or a timeout).
    # `after_dtmf=1` is our own marker so we never confuse this with the
    # initial NewCall — KooKoo may or may not include event=GotDTMF.
    if event == "GotDTMF" or params.get("after_dtmf") == "1":
        return await _handle_main_ivr_input(db, call_id, call_type, lang, data)

    # NewCall — play welcome + prompt and gather a digit
    script = script_for(call_type, lang)
    response = KooKooResponse()

    _lang_voice(response, script.welcome_message, lang, audio_key=f"welcome_{call_type.lower()}_{lang}")

    response.start_collect_dtmf(length=1, timeout_ms=6000)
    _lang_voice_in_collect(
        response, script.prompt, lang, audio_key=f"prompt_{call_type.lower()}_{lang}"
    )
    response.end_collect_dtmf()

    # Route the pressed digit (or no-input timeout) back to this same handler
    # so the post-DTMF branch above can dispatch into the action engine.
    # KooKoo appends `&event=GotDTMF&data=<digit>` to this URL on a press,
    # and may omit them on a timeout — `after_dtmf=1` ensures we route
    # correctly in both cases.
    response.gotourl(
        f"{settings.BASE_URL}/webhook/voice"
        f"?call_id={call_id}&call_type={call_type}&lang={lang}&after_dtmf=1"
    )

    db.add(AuditLog(
        event_type="IVR_PROMPT_PLAYED",
        description=f"call_id={call_id} call_type={call_type} lang={lang}",
        source="webhook",
    ))
    db.commit()
    return _xml(response)


async def _handle_main_ivr_input(
    db: Session, call_id: int, call_type: str, lang: str, data: str
) -> Response:
    """Action-engine path. KooKoo gives us the pressed digit in `data`."""
    # KooKoo only does DTMF here (not speech). Pass speech_raw=None.
    digit = normalize_input(call_type, data, None, lang)

    log.info(
        "main-ivr input: call_id=%s call_type=%s lang=%s data=%r -> digit=%r",
        call_id, call_type, lang, data, digit,
    )

    response = KooKooResponse()
    call = db.get(CallLog, call_id)

    # Guard: synthetic / unknown call IDs (e.g. smoke-test curls) — speak a
    # generic message and hang up rather than 500-ing while the action
    # engine tries to upsert tickets/orders that don't exist.
    if call is None:
        log.warning("main-ivr: unknown call_id=%s — returning fallback", call_id)
        _lang_voice(response, t(P_NO_INPUT, lang), lang, audio_key=f"no_input_{lang}")
        response.hangup()
        return _xml(response)

    if digit is None:
        _lang_voice(response, t(P_NO_INPUT, lang), lang, audio_key=f"no_input_{lang}")
        response.hangup()
        call.status = "NO_INPUT"
        db.commit()
        return _xml(response)

    if call:
        call.response = digit
        call.status = "ANSWERED"
        if not call.language:
            call.language = lang
        db.commit()

    user_phone = call.user_phone if call else ""
    if call_type == "CONFIRMATION":
        message, ticket_id = action_engine.handle_confirmation_response(
            db,
            order_id=call.order_id if call else 0,
            digit=digit,
            user_phone=user_phone,
            lang=lang,
        )
        is_help = digit == "2"
    else:
        message, ticket_id = action_engine.handle_rejection_response(
            db,
            order_id=call.order_id if call else 0,
            digit=digit,
            user_phone=user_phone,
            lang=lang,
        )
        is_help = digit == "3"

    # Help path → live transfer or queued callback (decision in help_router)
    if is_help and ticket_id:
        routed = route_help_request(
            db,
            ticket_id=ticket_id,
            call_id=call.call_id if call else 0,
            order_id=call.order_id if call else 0,
            user_phone=user_phone,
            lang=lang,
        )
        _lang_voice(response, routed["spoken_message"], lang, audio_key=f"agent_msg_{lang}_{routed['mode']}")
        if routed["mode"] == "live_transfer" and routed["dial_number"]:
            response.dial(routed["dial_number"], caller_id=settings.OZONETEL_DID)
    else:
        _lang_voice(response, message, lang, audio_key=f"action_msg_{lang}_{digit}")

    response.hangup()

    db.add(AuditLog(
        event_type="IVR_RESPONSE_HANDLED",
        description=(
            f"call_id={call_id} lang={lang} digit={digit} "
            f"reply={message[:80]}"
        ),
        source="webhook",
    ))
    db.commit()
    return _xml(response)


# ---------------------------------------------------------------------------
# /test-minimal — diagnostic endpoint that returns the simplest possible
# valid KooKoo XML. Use this to verify your account can play ANY audio.
# Configure it as a temporary outbound URL in KooKoo's dashboard, or hit
# it via curl to inspect the TwiML.
# ---------------------------------------------------------------------------

@router.api_route("/test-minimal", methods=["GET", "POST"])
async def test_minimal() -> Response:
    response = KooKooResponse()
    response.playtext("Hello, this is a test from Divine Hindu. Goodbye.", lang="EN")
    response.hangup()
    return _xml(response)


@router.api_route("/test-google", methods=["GET", "POST"])
async def test_google() -> Response:
    """Diagnostic: KooKoo Google TTS. Same content as /test-minimal but
    via the Google TTS bridge (type='ggl')."""
    response = KooKooResponse()
    response.playtext_google(
        "Hello, this is a Google TTS test from Divine Hindu. Goodbye.",
        locale="en-IN",
    )
    response.hangup()
    return _xml(response)


@router.api_route("/test-audio", methods=["GET", "POST"])
async def test_audio(request: Request) -> Response:
    """Diagnostic: plays a hosted MP3/WAV via <playaudio>. Use this when
    BOTH playtext and playtext-google return silence — it proves whether
    pre-recorded audio is our only path forward."""
    url = request.query_params.get("url") or f"{_audio_base()}/test_en.wav"
    response = KooKooResponse()
    response.playaudio(url)
    response.hangup()
    return _xml(response)


# ---------------------------------------------------------------------------
# /status — Ozonetel call lifecycle callbacks
# ---------------------------------------------------------------------------

@router.api_route("/status", methods=["GET", "POST"])
async def status_callback(request: Request, db: Session = Depends(get_db)) -> dict:
    params = dict(request.query_params)
    form_data: dict = {}
    if request.method == "POST":
        try:
            form_data = dict(await request.form())
        except Exception:  # noqa: BLE001
            form_data = {}
    merged = {**params, **form_data}

    call_id = int(merged.get("call_id", 0))
    raw_status = (merged.get("status") or merged.get("CallStatus") or "").lower()
    log.info("status callback: call_id=%s raw=%s", call_id, raw_status)

    # Map Ozonetel/KooKoo statuses to our internal vocabulary.
    # KooKoo emits things like: queued, ringing, answered, busy, completed,
    # missed, rejected, failed.
    mapping = {
        "queued": "INITIATED",
        "initiated": "INITIATED",
        "ringing": "RINGING",
        "answered": "ANSWERED",
        "in-progress": "ANSWERED",
        "completed": "COMPLETED",
        # KooKoo CPaaS emits these for normal call termination — they
        # mean the call ended without an explicit failure code, not that
        # the call failed.
        "normal": "COMPLETED",
        "normalclearing": "COMPLETED",
        "normalunspecified": "COMPLETED",
        "disconnect": "COMPLETED",
        "busy": "NO_ANSWER",
        "no-answer": "NO_ANSWER",
        "missed": "NO_ANSWER",
        "failed": "FAILED",
        "rejected": "FAILED",
        "canceled": "FAILED",
        "cancelled": "FAILED",
    }

    call = db.get(CallLog, call_id)
    if call and raw_status:
        call.status = mapping.get(raw_status, call.status)
        db.commit()

    return {"ok": True}
