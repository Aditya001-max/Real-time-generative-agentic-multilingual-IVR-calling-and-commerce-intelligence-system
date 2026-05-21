"""
gTTS backend — Google Translate TTS.

Free, no API key required. Supports all 9 languages we offer in the
language picker (en, hi, ta, te, kn, ml, bn, mr, gu) and many more.

Latency is ~300-800ms per call (HTTP round-trip to Google), so cache
hits are critical — the TTSChain caches MP3s by SHA-256(text|backend|lang).

Failure modes we handle gracefully:
  • Network down — synthesize raises, chain falls through to next backend
  • Google rate-limits the unauthenticated endpoint — same fallback path
  • Unsupported language — we explicitly check supports_lang() first
"""
from __future__ import annotations

import io

from app.core.logging import get_logger
from app.services.tts.base import TTSBackend

log = get_logger(__name__)


# ISO 639-1 codes that gTTS supports for the languages we care about.
# (gTTS supports many more — we only enumerate ours so cache_signature stays stable.)
_GTTS_SUPPORTED: dict[str, str] = {
    "en": "en",       # English (default to en-com, but we'll use IN tld)
    "hi": "hi",
    "ta": "ta",
    "te": "te",
    "kn": "kn",
    "ml": "ml",
    "bn": "bn",
    "mr": "mr",
    "gu": "gu",
}


class GTTSBackend(TTSBackend):
    name = "gtts"

    @property
    def available(self) -> bool:
        try:
            import gtts  # noqa: F401
            return True
        except ImportError:
            return False

    def cache_signature(self) -> str:
        # tld=co.in gives an Indian-accented voice for English; bumps if we change.
        return "gtts|v1|tld=co.in"

    def supports_lang(self, lang: str) -> bool:
        return lang in _GTTS_SUPPORTED

    def synthesize(self, text: str, lang: str = "en") -> bytes:
        from gtts import gTTS

        gtts_lang = _GTTS_SUPPORTED.get(lang, "en")
        # tld="co.in" picks the Indian Google domain → Indian-accented English
        # and slightly more natural-sounding Indic voices on the same endpoint.
        tts_obj = gTTS(text=text, lang=gtts_lang, tld="co.in", slow=False)

        buf = io.BytesIO()
        tts_obj.write_to_fp(buf)
        return buf.getvalue()
