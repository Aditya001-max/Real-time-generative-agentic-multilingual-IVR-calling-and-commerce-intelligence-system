"""Base interface every TTS backend implements."""
from __future__ import annotations

from abc import ABC, abstractmethod


class TTSBackend(ABC):
    """A TTS backend converts text to MP3/WAV audio bytes."""

    name: str = "base"

    @property
    @abstractmethod
    def available(self) -> bool:
        """True if this backend can be used right now (configured + reachable)."""

    @abstractmethod
    def synthesize(self, text: str, lang: str = "en") -> bytes:
        """Return audio bytes (MP3). Raises on failure.

        `lang` is an ISO 639-1 code (en, hi, ta, te, kn, ml, bn, mr, gu).
        Backends that ignore language (e.g. ElevenLabs auto-detects) may
        ignore the argument.
        """

    @abstractmethod
    def cache_signature(self) -> str:
        """A short string included in the cache key so different backends/voices
        produce different cache files."""

    def supports_lang(self, lang: str) -> bool:
        """Whether this backend can synthesize the given language. Default: yes."""
        return True
