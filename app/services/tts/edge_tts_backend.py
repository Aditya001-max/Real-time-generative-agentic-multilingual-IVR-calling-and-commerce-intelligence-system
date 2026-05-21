"""
Microsoft Edge TTS backend — FREE, no API key, human-sounding neural voices.

Uses Microsoft Azure's public Edge browser TTS endpoint via the `edge-tts`
Python library. Audio quality is on par with paid neural-TTS services.

Voices used (high-quality female neural voices for all 9 Indian languages —
override per language via EDGE_VOICE_<lang> env vars if you want a male
voice or a different speaker):
    en-IN-NeerjaNeural      (Indian English, female)
    hi-IN-SwaraNeural       (Hindi, female)
    ta-IN-PallaviNeural     (Tamil, female)
    te-IN-ShrutiNeural      (Telugu, female)
    kn-IN-SapnaNeural       (Kannada, female)
    ml-IN-SobhanaNeural     (Malayalam, female)
    bn-IN-TanishaaNeural    (Bengali, female)
    mr-IN-AarohiNeural      (Marathi, female)
    gu-IN-DhwaniNeural      (Gujarati, female)

Tradeoffs:
  - Latency: ~300–700ms per synth call (Microsoft endpoint round-trip)
  - Reliability: free public endpoint — Microsoft can throttle / change it
  - Caching: TTSChain caches by (text, lang, backend) so repeat plays are instant
"""
from __future__ import annotations

import asyncio
import os

from app.core.logging import get_logger
from app.services.tts.base import TTSBackend

log = get_logger(__name__)


# Default neural voices per language. Female voices chosen for IVR clarity;
# override any of these via env vars (e.g. EDGE_VOICE_HI=hi-IN-MadhurNeural for male).
_DEFAULT_VOICES: dict[str, str] = {
    "en": "en-IN-NeerjaNeural",
    "hi": "hi-IN-SwaraNeural",
    "ta": "ta-IN-PallaviNeural",
    "te": "te-IN-ShrutiNeural",
    "kn": "kn-IN-SapnaNeural",
    "ml": "ml-IN-SobhanaNeural",
    "bn": "bn-IN-TanishaaNeural",
    "mr": "mr-IN-AarohiNeural",
    "gu": "gu-IN-DhwaniNeural",
}


def _voice_for(lang: str) -> str:
    """Return the Edge TTS voice for a language (env override → default)."""
    env_key = f"EDGE_VOICE_{lang.upper()}"
    return os.environ.get(env_key) or _DEFAULT_VOICES.get(lang, _DEFAULT_VOICES["en"])


async def _gen_audio(text: str, voice: str) -> bytes:
    from edge_tts import Communicate

    comm = Communicate(text, voice)
    buf = b""
    async for chunk in comm.stream():
        if chunk["type"] == "audio":
            buf += chunk["data"]
    return buf


class EdgeTTSBackend(TTSBackend):
    name = "edge_tts"

    @property
    def available(self) -> bool:
        try:
            import edge_tts  # noqa: F401
            return True
        except ImportError:
            return False

    def cache_signature(self) -> str:
        # Bumping this string invalidates all cached MP3s (e.g. after voice change).
        return "edge|v1|neural-female"

    def supports_lang(self, lang: str) -> bool:
        return lang in _DEFAULT_VOICES or bool(os.environ.get(f"EDGE_VOICE_{lang.upper()}"))

    def synthesize(self, text: str, lang: str = "en") -> bytes:
        voice = _voice_for(lang)
        coro_factory = lambda: _gen_audio(text, voice)  # noqa: E731

        # If there's no running loop (e.g. webhook handler runs synth in a
        # threadpool), asyncio.run is fine. Inside FastAPI's lifespan or any
        # async handler, there IS a running loop and asyncio.run would crash —
        # so we hop to a fresh thread which gets its own loop.
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro_factory())

        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(lambda: asyncio.run(coro_factory())).result()
