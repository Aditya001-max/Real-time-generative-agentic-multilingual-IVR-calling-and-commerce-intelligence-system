"""
Static audio endpoint.

Two purposes:
  1. /audio/<hash>.mp3 — served from the AI-voice TTS cache (ElevenLabs /
     Coqui output). Used when USE_AI_VOICE=true.
  2. /audio/<key>.wav  — served from AUDIO_CACHE_DIR/wav. Used by the
     Ozonetel KooKoo IVR for languages KooKoo native TTS does not support
     (ta, ml, bn, mr, gu). KooKoo expects PCM 16-bit, 8kHz, mono WAV.
     See scripts/generate_audio.py for how these files are produced.

Strict key validation in both routes (alnum + underscore + hyphen) to
prevent path traversal.
"""
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.core.config import settings
from app.services.tts import tts

router = APIRouter(prefix="/audio", tags=["audio"])

_KEY_RE = re.compile(r"^[A-Za-z0-9_\-]+$")


@router.get("/{key}.mp3")
def get_audio_mp3(key: str) -> FileResponse:
    path = tts.get_cached_path(key)
    if path is None:
        raise HTTPException(status_code=404, detail="audio not found")
    return FileResponse(
        path,
        media_type="audio/mpeg",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@router.get("/{key}.wav")
def get_audio_wav(key: str) -> FileResponse:
    """Serve an 8 kHz mono PCM WAV. Two sources are checked:
      1. tts.get_cached_wav_path(key) — files synthesized by our TTS chain
         and downconverted via ffmpeg (32-hex-char SHA keys). This is the
         path KooKoo <playaudio> hits for everything we generate at runtime.
      2. audio_cache/wav/<key>.wav — hand-recorded files dropped here by
         scripts/generate_audio.py (free-form keys like menu_ta_3)."""
    if not _KEY_RE.match(key):
        raise HTTPException(status_code=400, detail="invalid key")

    # Source 1: TTS-synthesized cache (32-hex-char keys).
    tts_wav = tts.get_cached_wav_path(key)
    if tts_wav is not None:
        return FileResponse(
            tts_wav,
            media_type="audio/wav",
            headers={"Cache-Control": "public, max-age=31536000, immutable"},
        )

    # Source 2: hand-recorded WAVs (free-form keys).
    wav_dir = Path(settings.AUDIO_CACHE_DIR) / "wav"
    candidate = wav_dir / f"{key}.wav"
    try:
        resolved = candidate.resolve()
        wav_dir_resolved = wav_dir.resolve()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="audio not found")

    if not str(resolved).startswith(str(wav_dir_resolved)):
        raise HTTPException(status_code=400, detail="invalid path")

    if not resolved.is_file():
        raise HTTPException(status_code=404, detail="audio not found")

    return FileResponse(
        resolved,
        media_type="audio/wav",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )
