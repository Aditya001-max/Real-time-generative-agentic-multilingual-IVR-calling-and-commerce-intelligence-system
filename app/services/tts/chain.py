"""
TTSChain — picks a backend by priority, caches MP3s on disk, falls back
on failure.

Priority is set via TTS_PROVIDERS in .env, e.g.:
  TTS_PROVIDERS=coqui,elevenlabs    # try Coqui first, ElevenLabs as fallback
  TTS_PROVIDERS=elevenlabs          # ElevenLabs only
  TTS_PROVIDERS=                    # disabled — KooKoo Google TTS will be used

The cache key includes the active backend's signature, so switching
providers does not serve stale audio.
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path
from typing import Iterable

from app.core.config import settings
from app.core.logging import get_logger
from app.services.tts.base import TTSBackend
from app.services.tts.coqui_backend import CoquiBackend
from app.services.tts.edge_tts_backend import EdgeTTSBackend
from app.services.tts.elevenlabs_backend import ElevenLabsBackend
from app.services.tts.gtts_backend import GTTSBackend

log = get_logger(__name__)


_REGISTRY: dict[str, type[TTSBackend]] = {
    "edge_tts": EdgeTTSBackend,
    "gtts": GTTSBackend,
    "coqui": CoquiBackend,
    "elevenlabs": ElevenLabsBackend,
}


class TTSChain:
    """A prioritized list of backends with on-disk MP3 caching."""

    def __init__(self) -> None:
        self.cache_dir = Path(settings.AUDIO_CACHE_DIR)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._backends: list[TTSBackend] = self._build_chain()

    # ---------- public API ----------

    @property
    def enabled(self) -> bool:
        return settings.USE_AI_VOICE and any(b.available for b in self._backends)

    @property
    def active_backends(self) -> list[str]:
        return [b.name for b in self._backends if b.available]

    def synth_url(self, text: str, lang: str = "en") -> str | None:
        """Return a public URL the IVR carrier can <playaudio>, or None if
        all backends failed. The returned URL points to a WAV file when
        ffmpeg is available — telephony carriers (Ozonetel KooKoo
        specifically) require PCM 16-bit, 8 kHz, mono WAV via <playaudio>
        and silently ignore MP3 URLs. We fall back to the original MP3 URL
        if ffmpeg is missing so the helper still works in dev environments."""
        if not settings.USE_AI_VOICE:
            return None

        for backend in self._backends:
            if not backend.available:
                continue
            if not backend.supports_lang(lang):
                continue

            key = self._cache_key(text, backend, lang)
            mp3_path = self.cache_dir / f"{key}.mp3"
            wav_path = self._wav_dir() / f"{key}.wav"

            # Cache hits — return immediately if either format is on disk.
            if wav_path.exists():
                return self._public_wav_url(key)
            if mp3_path.exists():
                converted = self._mp3_to_wav(mp3_path, wav_path)
                if converted:
                    return self._public_wav_url(key)
                return self._public_mp3_url(key)

            try:
                audio = backend.synthesize(text, lang)
                mp3_path.write_bytes(audio)
                log.info(
                    "tts: synthesized %d bytes via %s lang=%s key=%s",
                    len(audio),
                    backend.name,
                    lang,
                    key,
                )
                converted = self._mp3_to_wav(mp3_path, wav_path)
                if converted:
                    return self._public_wav_url(key)
                return self._public_mp3_url(key)
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "tts: backend=%s lang=%s failed for text=%r — trying next. err=%s",
                    backend.name,
                    lang,
                    text[:50],
                    exc,
                )
                continue

        log.error("tts: all backends failed for lang=%s text=%r", lang, text[:50])
        return None

    def prewarm(self, items: Iterable) -> dict:
        """Pre-synthesize a batch. Each item is either `text` (English) or `(text, lang)`."""
        out: dict = {}
        for item in items:
            if isinstance(item, tuple):
                text, lang = item
            else:
                text, lang = item, "en"
            out[(text, lang)] = self.synth_url(text, lang)
        return out

    def get_cached_path(self, key: str) -> Path | None:
        """Resolve an MP3 cache key to its on-disk path. Used by the
        /audio/<key>.mp3 route. Path-traversal hardened — only 32-hex-char
        keys allowed."""
        if not key.isalnum() or len(key) != 32:
            return None
        path = self.cache_dir / f"{key}.mp3"
        return path if path.exists() else None

    def get_cached_wav_path(self, key: str) -> Path | None:
        """Resolve a WAV cache key to its on-disk path. Used by the
        /audio/<key>.wav route. The WAV variant is what KooKoo's
        <playaudio> actually plays — see synth_url() for the rationale."""
        if not key.isalnum() or len(key) != 32:
            return None
        path = self._wav_dir() / f"{key}.wav"
        return path if path.exists() else None

    # ---------- internals ----------

    def _build_chain(self) -> list[TTSBackend]:
        names = [n.strip().lower() for n in settings.TTS_PROVIDERS.split(",") if n.strip()]
        chain: list[TTSBackend] = []
        for name in names:
            cls = _REGISTRY.get(name)
            if cls is None:
                log.warning("tts: unknown backend %r in TTS_PROVIDERS — skipping", name)
                continue
            chain.append(cls())
        return chain

    def _cache_key(self, text: str, backend: TTSBackend, lang: str = "en") -> str:
        material = f"{text}|{lang}|{backend.name}|{backend.cache_signature()}"
        return hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]

    def _public_url(self, key: str) -> str:
        # Legacy alias retained for any caller that still wants the MP3.
        return self._public_mp3_url(key)

    def _public_mp3_url(self, key: str) -> str:
        base = (settings.AUDIO_PUBLIC_BASE or f"{settings.BASE_URL}/audio").rstrip("/")
        return f"{base}/{key}.mp3"

    def _public_wav_url(self, key: str) -> str:
        base = (settings.AUDIO_PUBLIC_BASE or f"{settings.BASE_URL}/audio").rstrip("/")
        return f"{base}/{key}.wav"

    def _wav_dir(self) -> Path:
        # KooKoo's <playaudio> requires a specific PCM/8kHz/mono format.
        # Keep WAVs in a sibling directory so the audio.py route can serve
        # them without touching the MP3 cache used by browser playback.
        path = self.cache_dir / "wav"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _mp3_to_wav(self, mp3_path: Path, wav_path: Path) -> bool:
        """Convert MP3 → 8 kHz mono PCM 16-bit WAV via ffmpeg.

        This is exactly the format Ozonetel KooKoo expects on <playaudio>.
        Returns True on success, False if ffmpeg is missing or the
        conversion fails — caller falls back to serving the MP3 URL."""
        if not shutil.which("ffmpeg"):
            log.warning(
                "tts: ffmpeg not on PATH — serving MP3 URL instead of WAV. "
                "KooKoo <playaudio> only plays WAV; install ffmpeg with "
                "`brew install ffmpeg` to fix audio playback."
            )
            return False
        try:
            subprocess.run(
                [
                    "ffmpeg", "-y", "-loglevel", "error",
                    "-i", str(mp3_path),
                    "-ac", "1",       # mono
                    "-ar", "8000",    # 8 kHz sample rate
                    "-acodec", "pcm_s16le",  # 16-bit signed little-endian PCM
                    str(wav_path),
                ],
                check=True,
                capture_output=True,
                timeout=20,
            )
            return wav_path.exists() and wav_path.stat().st_size > 0
        except Exception as exc:  # noqa: BLE001
            log.warning("tts: ffmpeg conversion failed for %s: %s", mp3_path.name, exc)
            return False


tts = TTSChain()
