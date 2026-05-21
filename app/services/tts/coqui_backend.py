"""
Coqui XTTS-v2 backend (open source, runs locally, FREE).

Model: tts_models/multilingual/multi-dataset/xtts_v2
PyPI:  coqui-tts (the maintained fork after Coqui AI's 2025 shutdown)
License: Coqui Public Model License (commercial use allowed)

Heavy import (PyTorch + ~2GB model weights) — lazy-loaded on first call.
We synthesize at WAV, then convert to MP3 for Twilio compatibility.
"""
from __future__ import annotations

import io
import os
import threading
from pathlib import Path

from app.core.config import settings
from app.core.logging import get_logger
from app.services.tts.base import TTSBackend

log = get_logger(__name__)


class CoquiBackend(TTSBackend):
    name = "coqui"

    def __init__(self) -> None:
        self._tts = None
        self._lock = threading.Lock()
        # XTTS-v2 ships under a non-commercial-by-default license file that
        # the library prompts the user to agree to. We auto-accept since the
        # operator has explicitly opted in by setting USE_COQUI_TTS=true.
        os.environ.setdefault("COQUI_TOS_AGREED", "1")

    # ---------- availability ----------

    @property
    def available(self) -> bool:
        if not settings.USE_COQUI_TTS:
            return False
        try:
            import TTS  # noqa: F401
            return True
        except ImportError:
            return False

    def cache_signature(self) -> str:
        return f"coqui|xtts_v2|{settings.COQUI_LANGUAGE}|{settings.COQUI_SPEAKER}"

    # ---------- model loading (lazy) ----------

    def _ensure_loaded(self) -> None:
        if self._tts is not None:
            return
        with self._lock:
            if self._tts is not None:
                return

            import torch
            from TTS.api import TTS  # type: ignore

            device = "cuda" if torch.cuda.is_available() else "cpu"
            log.info("loading XTTS-v2 model on %s (first load takes ~30s)", device)
            tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)
            self._tts = tts
            log.info("XTTS-v2 ready")

    # ---------- synthesis ----------

    def synthesize(self, text: str, lang: str = "en") -> bytes:  # noqa: ARG002
        self._ensure_loaded()
        wav_bytes = self._synth_wav(text)
        # Twilio plays MP3 reliably; some accounts also play WAV. We convert
        # to MP3 so behaviour matches the ElevenLabs backend exactly.
        return _wav_bytes_to_mp3_bytes(wav_bytes)

    def _synth_wav(self, text: str) -> bytes:
        assert self._tts is not None
        kwargs = {"text": text, "language": settings.COQUI_LANGUAGE}

        speaker_wav = settings.COQUI_SPEAKER_WAV
        if speaker_wav and Path(speaker_wav).exists():
            # Voice cloning from a 6-second WAV reference file.
            kwargs["speaker_wav"] = speaker_wav
        else:
            # Use one of XTTS's built-in speakers.
            kwargs["speaker"] = settings.COQUI_SPEAKER

        # XTTS returns a list of float amplitudes. We write through soundfile.
        wav = self._tts.tts(**kwargs)
        return _floats_to_wav_bytes(wav, sample_rate=24000)


# ---------- audio helpers ----------

def _floats_to_wav_bytes(samples, sample_rate: int) -> bytes:
    """Convert a Python list / numpy array of float samples to WAV bytes."""
    import numpy as np
    import soundfile as sf

    arr = np.asarray(samples, dtype=np.float32)
    buf = io.BytesIO()
    sf.write(buf, arr, sample_rate, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def _wav_bytes_to_mp3_bytes(wav_bytes: bytes) -> bytes:
    """WAV → MP3 conversion using pydub (requires ffmpeg in the system)."""
    from pydub import AudioSegment

    seg = AudioSegment.from_file(io.BytesIO(wav_bytes), format="wav")
    out = io.BytesIO()
    # 64kbps mono is plenty for phone calls and keeps cache small.
    seg = seg.set_channels(1).set_frame_rate(22050)
    seg.export(out, format="mp3", bitrate="64k")
    return out.getvalue()
