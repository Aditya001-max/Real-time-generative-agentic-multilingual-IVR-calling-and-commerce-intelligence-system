"""
Tests for the TTS provider chain.

These are pure unit tests — no real ElevenLabs or Coqui calls. We mock
the backends to verify the chain logic itself: priority ordering,
fallback on failure, caching, and path-traversal hardening.
"""
from __future__ import annotations

from pathlib import Path

from app.core.config import settings
from app.services.tts.base import TTSBackend
from app.services.tts.chain import TTSChain


class _FakeBackend(TTSBackend):
    """Configurable fake backend for tests."""

    def __init__(self, name: str, *, available: bool = True, fail: bool = False) -> None:
        self.name = name
        self._available = available
        self._fail = fail
        self.call_count = 0

    @property
    def available(self) -> bool:
        return self._available

    def cache_signature(self) -> str:
        return f"fake-{self.name}"

    def synthesize(self, text: str, lang: str = "en") -> bytes:  # noqa: ARG002
        self.call_count += 1
        if self._fail:
            raise RuntimeError(f"{self.name} backend boom")
        return f"audio-from-{self.name}".encode()


def _make_chain(tmp_path: Path, monkeypatch, backends: list[TTSBackend], use_voice: bool = True):
    monkeypatch.setattr(settings, "AUDIO_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "BASE_URL", "https://test.example.com")
    monkeypatch.setattr(settings, "USE_AI_VOICE", use_voice)
    chain = TTSChain.__new__(TTSChain)
    chain.cache_dir = tmp_path
    chain._backends = backends
    return chain


def test_disabled_returns_none(tmp_path, monkeypatch):
    chain = _make_chain(tmp_path, monkeypatch, [_FakeBackend("a")], use_voice=False)
    assert chain.synth_url("hi") is None


def test_first_available_backend_wins(tmp_path, monkeypatch):
    a = _FakeBackend("primary")
    b = _FakeBackend("fallback")
    chain = _make_chain(tmp_path, monkeypatch, [a, b])

    url = chain.synth_url("hello")
    assert url is not None
    assert a.call_count == 1
    assert b.call_count == 0  # primary worked, fallback never called


def test_unavailable_first_backend_skipped(tmp_path, monkeypatch):
    a = _FakeBackend("primary", available=False)
    b = _FakeBackend("fallback")
    chain = _make_chain(tmp_path, monkeypatch, [a, b])

    chain.synth_url("hello")
    assert a.call_count == 0
    assert b.call_count == 1


def test_failed_backend_falls_through_to_next(tmp_path, monkeypatch):
    a = _FakeBackend("primary", fail=True)
    b = _FakeBackend("fallback")
    chain = _make_chain(tmp_path, monkeypatch, [a, b])

    url = chain.synth_url("hello")
    assert url is not None
    assert a.call_count == 1
    assert b.call_count == 1


def test_all_backends_failed_returns_none(tmp_path, monkeypatch):
    a = _FakeBackend("primary", fail=True)
    b = _FakeBackend("fallback", fail=True)
    chain = _make_chain(tmp_path, monkeypatch, [a, b])

    assert chain.synth_url("hello") is None


def test_cache_hit_skips_synthesis(tmp_path, monkeypatch):
    a = _FakeBackend("primary")
    chain = _make_chain(tmp_path, monkeypatch, [a])

    url1 = chain.synth_url("same text")
    url2 = chain.synth_url("same text")
    assert url1 == url2
    assert a.call_count == 1  # second call hit cache


def test_cache_key_changes_with_backend_signature(tmp_path, monkeypatch):
    a = _FakeBackend("primary")
    chain = _make_chain(tmp_path, monkeypatch, [a])

    text = "same text"
    url_a = chain.synth_url(text)

    # Switch backend to one with a different signature → new cache key.
    a._available = False
    b = _FakeBackend("alt")
    chain._backends = [a, b]
    url_b = chain.synth_url(text)

    assert url_a != url_b


def test_path_traversal_rejected(tmp_path, monkeypatch):
    chain = _make_chain(tmp_path, monkeypatch, [_FakeBackend("a")])
    assert chain.get_cached_path("../etc/passwd") is None
    assert chain.get_cached_path("../../bad") is None
    assert chain.get_cached_path("not32chars") is None
    assert chain.get_cached_path("a" * 32) is None  # valid format, file missing


def test_active_backends_excludes_unavailable(tmp_path, monkeypatch):
    a = _FakeBackend("up", available=True)
    b = _FakeBackend("down", available=False)
    chain = _make_chain(tmp_path, monkeypatch, [a, b])
    assert chain.active_backends == ["up"]
