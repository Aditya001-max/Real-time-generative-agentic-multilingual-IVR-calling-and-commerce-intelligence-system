"""
Pre-warm the TTS cache for every IVR prompt × every supported language.

Run this whenever you change voice settings (USE_AI_VOICE, TTS_PROVIDERS),
edit a prompt, swap a voice ID, or after a fresh deploy. After this script
finishes, the first real call no longer pays the synthesis latency — every
<playaudio> URL is already a cached MP3 served by /audio/<hash>.mp3.

    python -m scripts.prewarm_voice
"""
from __future__ import annotations

from app.services.greetings import (
    COMPANY_NAME,
    GREETING_PARTS,
    LANGUAGE_MENU_LINES,
    MENU_TEXT_BY_LANG,
    SUPPORTED_LANGUAGES,
)
from app.services.translations import PROMPTS
from app.services.tts import tts


def _greeting_strings() -> list[tuple[str, str]]:
    """English greeting variants (CONFIRMATION + REJECTION). Always 'en'."""
    out: list[tuple[str, str]] = []
    for parts in GREETING_PARTS.values():
        text = parts["prefix"] + COMPANY_NAME + parts["trailing"]
        out.append((text, "en"))
    return out


def _picker_menu_strings() -> list[tuple[str, str]]:
    """Picker menu lines — every (language, digit) combination that can
    appear once the menu is filtered by state. Digits 1..3 cover every real
    menu shape; we never show more than 3 options to a caller."""
    out: list[tuple[str, str]] = []
    for _digit_default, lang, _locale, _menu_text_default in LANGUAGE_MENU_LINES:
        for d in range(1, 4):
            out.append((MENU_TEXT_BY_LANG[lang].format(digit=d), lang))
    return out


def _ivr_strings() -> list[tuple[str, str]]:
    """All translated prompts (welcome/prompt/fallback/confirmation/etc.) ×
    every supported language."""
    out: list[tuple[str, str]] = []
    for _pid, table in PROMPTS.items():
        for lang in SUPPORTED_LANGUAGES:
            text = table.get(lang) or table.get("en", "")
            if text:
                out.append((text, lang))
    return out


def main() -> None:
    if not tts.enabled:
        print("AI voice is disabled (USE_AI_VOICE=false or no backend available).")
        return

    jobs: list[tuple[str, str]] = []
    jobs += _greeting_strings()
    jobs += _picker_menu_strings()
    jobs += _ivr_strings()

    # Dedupe (same text+lang would otherwise be re-synthesized — cheap to
    # detect here, expensive when each synth costs ~500ms).
    seen: set[tuple[str, str]] = set()
    deduped: list[tuple[str, str]] = []
    for text, lang in jobs:
        key = (text.strip(), lang)
        if key in seen:
            continue
        seen.add(key)
        deduped.append((text, lang))

    print(f"Pre-warming {len(deduped)} (text, lang) entries via {tts.active_backends}...")
    ok = 0
    failed: list[tuple[str, str]] = []
    for i, (text, lang) in enumerate(deduped, 1):
        url = tts.synth_url(text, lang)
        status = "OK" if url else "FAIL"
        print(f"  [{i:>3}/{len(deduped)}] {status:>4} {lang}  {text[:60]}")
        if url:
            ok += 1
        else:
            failed.append((text, lang))

    print()
    print(f"Done: {ok}/{len(deduped)} succeeded")
    if failed:
        print(f"FAILED ({len(failed)}):")
        for text, lang in failed[:10]:
            print(f"  - [{lang}] {text[:80]}")


if __name__ == "__main__":
    main()
