"""ElevenLabs TTS backend (paid fallback / premium voice)."""
from __future__ import annotations

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.services.tts.base import TTSBackend

log = get_logger(__name__)

ELEVENLABS_BASE_URL = "https://api.elevenlabs.io/v1"


class ElevenLabsBackend(TTSBackend):
    name = "elevenlabs"

    @property
    def available(self) -> bool:
        return bool(settings.ELEVENLABS_API_KEY)

    def cache_signature(self) -> str:
        return (
            f"el|{settings.ELEVENLABS_VOICE_ID}|{settings.ELEVENLABS_MODEL_ID}|"
            f"{settings.ELEVENLABS_STABILITY}|{settings.ELEVENLABS_SIMILARITY_BOOST}|"
            f"{settings.ELEVENLABS_STYLE}|{settings.ELEVENLABS_USE_SPEAKER_BOOST}"
        )

    def synthesize(self, text: str, lang: str = "en") -> bytes:  # noqa: ARG002
        url = (
            f"{ELEVENLABS_BASE_URL}/text-to-speech/{settings.ELEVENLABS_VOICE_ID}"
            f"?output_format={settings.ELEVENLABS_OUTPUT_FORMAT}"
        )
        body = {
            "text": text,
            "model_id": settings.ELEVENLABS_MODEL_ID,
            "voice_settings": {
                "stability": settings.ELEVENLABS_STABILITY,
                "similarity_boost": settings.ELEVENLABS_SIMILARITY_BOOST,
                "style": settings.ELEVENLABS_STYLE,
                "use_speaker_boost": settings.ELEVENLABS_USE_SPEAKER_BOOST,
            },
        }
        headers = {
            "xi-api-key": settings.ELEVENLABS_API_KEY,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        with httpx.Client(timeout=httpx.Timeout(30.0, connect=5.0)) as client:
            r = client.post(url, json=body, headers=headers)
            r.raise_for_status()
            return r.content
