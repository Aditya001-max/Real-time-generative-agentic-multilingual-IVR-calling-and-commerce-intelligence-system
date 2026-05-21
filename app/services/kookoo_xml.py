"""
KooKoo XML response builder — Ozonetel's TwiML equivalent.

KooKoo XML differs from TwiML in:
  • Root element is lowercase <response> (not <Response>)
  • Speech tags are <playtext> / <playaudio> (not <Say> / <Play>)
  • DTMF gather is <collectdtmf l="N" o="MS"> (length, timeout in ms)
  • Redirect is <gotourl> (not <Redirect>)
  • Lang codes are uppercase 2-letter (EN, HI, TE, KA) for native TTS

This module emits well-formed KooKoo XML safely (escapes user input).
Webhook handler (app/routes/webhook.py) is the only caller.

TTS provider chain:
  1. KooKoo native TTS — <playtext lang="EN|HI|TE|KA"> — fastest, only 4 langs
  2. KooKoo Google TTS — <playtext type="ggl" lang="ta-IN|..."> — all 9 langs
  3. <playaudio>{url}</playaudio> — pre-recorded WAVs, last resort
"""
from xml.sax.saxutils import escape


# Map our internal lang codes (lowercase) to KooKoo's native TTS code.
# None means KooKoo native does NOT speak this language → use Google TTS.
_KOOKOO_NATIVE_LANG_MAP: dict[str, str] = {
    "en": "EN",
    "hi": "HI",
    "te": "TE",
    "kn": "KA",   # KooKoo writes Kannada as KA
}

# Google TTS BCP-47 locales — KooKoo passes these straight through to
# Google when type="ggl". Covers all 9 languages in our menu.
_KOOKOO_GOOGLE_LANG_MAP: dict[str, str] = {
    "en": "en-IN",
    "hi": "hi-IN",
    "ta": "ta-IN",
    "te": "te-IN",
    "kn": "kn-IN",
    "ml": "ml-IN",
    "bn": "bn-IN",
    "mr": "mr-IN",
    "gu": "gu-IN",
}

# Premium Google Wavenet voices per language. Wavenet voices are much
# less robotic than the default Standard voices. Requires Ozonetel Pro
# (which exposes Google TTS via <playtext type="ggl">). All -D voices
# are female; swap to -B/-C for male if needed.
_KOOKOO_GOOGLE_VOICE_MAP: dict[str, str] = {
    "en": "en-IN-Wavenet-D",
    "hi": "hi-IN-Wavenet-D",
    "ta": "ta-IN-Wavenet-D",
    "te": "te-IN-Standard-A",   # Telugu has no Wavenet yet — Standard-A is best available
    "kn": "kn-IN-Wavenet-D",
    "ml": "ml-IN-Wavenet-D",
    "bn": "bn-IN-Wavenet-D",
    "mr": "mr-IN-Wavenet-D",
    "gu": "gu-IN-Wavenet-D",
}


def google_tts_voice_for(lang_code: str) -> str:
    """Return the preferred premium Google voice for a language, or ''
    to let KooKoo pick the default (robotic) voice."""
    return _KOOKOO_GOOGLE_VOICE_MAP.get(lang_code, "")


def kookoo_lang_for(lang_code: str) -> str | None:
    """Return KooKoo's native lang attribute for our internal code, or None
    if the language isn't covered by KooKoo's native TTS (use Google TTS)."""
    return _KOOKOO_NATIVE_LANG_MAP.get(lang_code)


def kookoo_supports(lang_code: str) -> bool:
    """True if KooKoo native TTS can speak this language."""
    return lang_code in _KOOKOO_NATIVE_LANG_MAP


def google_tts_locale_for(lang_code: str) -> str | None:
    """Return the Google-TTS BCP-47 locale (e.g. 'ta-IN') KooKoo expects
    for type='ggl' playtext, or None if we don't know it."""
    return _KOOKOO_GOOGLE_LANG_MAP.get(lang_code)


# Used by KooKooResponse.playtext() to auto-promote a non-English `lang=`
# call (e.g. lang="HI", lang="hi") into a Google TTS tag. Keys cover both
# the legacy uppercase 2-letter codes and our normal lowercase codes.
_NATIVE_TO_GOOGLE_LOCALE: dict[str, str] = {
    "en": "en-IN",
    "hi": "hi-IN",
    "ta": "ta-IN",
    "te": "te-IN",
    "kn": "kn-IN",
    "ka": "kn-IN",   # KooKoo's legacy code for Kannada
    "ml": "ml-IN",
    "bn": "bn-IN",
    "mr": "mr-IN",
    "gu": "gu-IN",
}


class KooKooResponse:
    """Builds KooKoo XML responses with a fluent API.

    Usage:
        r = KooKooResponse()
        r.playtext("Hello", lang="EN")
        r.start_collect_dtmf(length=1, timeout_ms=8000)
        r.playtext_in_collect("Press 1", lang="EN")
        r.end_collect_dtmf()
        r.hangup()
        xml = r.to_xml()
    """

    def __init__(self) -> None:
        self._parts: list[str] = []
        self._in_collect = False
        self._collect_buffer: list[str] = []
        self._collect_attrs = ""

    # ----- speech -----

    def playtext(self, text: str, lang: str = "EN") -> "KooKooResponse":
        """Top-level <playtext>.

        KooKoo's native <playtext> only speaks plain English with no `lang`
        attribute. The `lang` parameter is preserved here for API
        compatibility but is now used to AUTO-PROMOTE non-English calls
        to Google TTS — KooKoo silently rejects any TwiML that combines
        `<playtext>` with a `lang` attribute (no `type="ggl"`), which
        manifests as a connected call playing zero audio before being
        cut by the carrier.
        """
        if not text:
            return self
        # Map our internal codes (EN/HI/TE/KA upper, en/hi/.. lower) to
        # something we can compare. Anything other than English routes
        # through Google TTS.
        norm = (lang or "").lower()
        if norm in ("en", ""):
            tag = f"<playtext>{escape(text)}</playtext>"
        else:
            locale = _NATIVE_TO_GOOGLE_LOCALE.get(norm, "en-IN")
            tag = f'<playtext type="ggl" lang="{locale}">{escape(text)}</playtext>'
        self._append(tag)
        return self

    def playtext_google(
        self,
        text: str,
        locale: str = "en-IN",
        voice: str = "",
    ) -> "KooKooResponse":
        """Top-level <playtext type="ggl">. KooKoo passes the text to Google
        TTS, which speaks all 9 Indian languages natively. `locale` is a
        BCP-47 tag like 'ta-IN', 'ml-IN', 'bn-IN'. `voice` is a Google
        voice name like 'en-IN-Wavenet-D' — Wavenet/Neural2 voices are
        much less robotic than the default. Requires Ozonetel Pro."""
        if not text:
            return self
        voice_attr = f' voice="{escape(voice)}"' if voice else ""
        tag = (
            f'<playtext type="ggl" lang="{locale}"{voice_attr}>'
            f"{escape(text)}</playtext>"
        )
        self._append(tag)
        return self

    def playaudio(self, url: str) -> "KooKooResponse":
        """Top-level <playaudio> — for pre-recorded WAV files."""
        if not url:
            return self
        tag = f"<playaudio>{escape(url)}</playaudio>"
        self._append(tag)
        return self

    # ----- DTMF gather -----

    def start_collect_dtmf(
        self,
        length: int = 1,
        timeout_ms: int = 6000,
        terminator: str = "#",
    ) -> "KooKooResponse":
        """Open a <collectdtmf> block. Add playtext/playaudio inside, then call end_collect_dtmf()."""
        if self._in_collect:
            raise ValueError("Already inside a collectdtmf block")
        self._in_collect = True
        self._collect_buffer = []
        self._collect_attrs = f'l="{length}" o="{timeout_ms}" t="{terminator}"'
        return self

    def end_collect_dtmf(self) -> "KooKooResponse":
        if not self._in_collect:
            raise ValueError("Not inside a collectdtmf block")
        inner = "".join(self._collect_buffer)
        self._parts.append(f"<collectdtmf {self._collect_attrs}>{inner}</collectdtmf>")
        self._in_collect = False
        self._collect_buffer = []
        return self

    def playtext_in_collect(self, text: str, lang: str = "EN") -> "KooKooResponse":
        if not self._in_collect:
            raise ValueError("Must be inside start_collect_dtmf/end_collect_dtmf")
        return self.playtext(text, lang)

    def playtext_google_in_collect(
        self,
        text: str,
        locale: str = "en-IN",
        voice: str = "",
    ) -> "KooKooResponse":
        if not self._in_collect:
            raise ValueError("Must be inside start_collect_dtmf/end_collect_dtmf")
        return self.playtext_google(text, locale, voice)

    def playaudio_in_collect(self, url: str) -> "KooKooResponse":
        if not self._in_collect:
            raise ValueError("Must be inside start_collect_dtmf/end_collect_dtmf")
        return self.playaudio(url)

    # ----- flow -----

    def gotourl(self, url: str) -> "KooKooResponse":
        self._parts.append(f"<gotourl>{escape(url)}</gotourl>")
        return self

    def dial(self, phone: str, caller_id: str = "", record: bool = False) -> "KooKooResponse":
        attrs: list[str] = []
        if caller_id:
            attrs.append(f'callerid="{escape(caller_id)}"')
        if record:
            attrs.append('record="true"')
        attr_str = (" " + " ".join(attrs)) if attrs else ""
        self._parts.append(f"<dial{attr_str}>{escape(phone)}</dial>")
        return self

    def hangup(self) -> "KooKooResponse":
        self._parts.append("<hangup/>")
        return self

    # ----- internal -----

    def _append(self, tag: str) -> None:
        if self._in_collect:
            self._collect_buffer.append(tag)
        else:
            self._parts.append(tag)

    def to_xml(self) -> str:
        if self._in_collect:
            raise ValueError("Unclosed collectdtmf block — call end_collect_dtmf()")
        body = "".join(self._parts)
        return f'<?xml version="1.0" encoding="UTF-8"?><response>{body}</response>'

    def __str__(self) -> str:
        return self.to_xml()
