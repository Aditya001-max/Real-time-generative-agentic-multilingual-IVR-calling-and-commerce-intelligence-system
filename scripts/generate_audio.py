"""
Generate WAV files for languages Ozonetel KooKoo's native TTS does NOT
support (ta, ml, bn, mr, gu).

Output:
  audio_cache/wav/<key>.wav   — PCM 16-bit, 8kHz, mono (KooKoo's required format)

Run once after deploy. Re-run whenever IVR text changes.

Usage:
    python scripts/generate_audio.py            # use gTTS (free, requires internet)
    python scripts/generate_audio.py --tts coqui  # offline (needs Coqui installed)

Dependencies:
  • gTTS (pip install gTTS)             — easiest, default
  • ffmpeg                               — to downsample to 8kHz mono PCM

If ffmpeg is missing, the script writes 24kHz MP3-decoded WAVs which
KooKoo *may* still play but is not guaranteed. Install ffmpeg via
  brew install ffmpeg
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

# Make app importable when running from project root
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.greetings import (
    COMPANY_NAME,
    GREETING_PARTS,
    LANGUAGE_MENU_LINES,
    MENU_TEXT_BY_LANG,
)
from app.services.regions import STATE_TO_MENU
from app.services.translations import (
    P_AGENT_TRANSFER,
    P_AFTER_HOURS_TICKET,
    P_CALLBACK_QUEUED,
    P_CANCELLED,
    P_CONFIRM_FALLBACK,
    P_CONFIRM_PROMPT,
    P_CONFIRM_WELCOME,
    P_INVALID_INPUT,
    P_NO_INPUT,
    P_ORDER_CONFIRMED,
    P_REATTEMPT,
    P_REJECT_FALLBACK,
    P_REJECT_PROMPT,
    P_REJECT_WELCOME,
    P_TEAM_WILL_CALLBACK,
    PROMPTS,
    t,
)


# Languages KooKoo's native TTS DOES support — skip generating audio for these
KOOKOO_NATIVE = {"en", "hi", "te", "kn"}

# Languages we need pre-recorded WAVs for
TARGET_LANGS = ["ta", "ml", "bn", "mr", "gu"]

# gTTS uses BCP-47 language codes
GTTS_LANG_MAP = {
    "ta": "ta",
    "ml": "ml",
    "bn": "bn",
    "mr": "mr",
    "gu": "gu",
}


def _menu_audio_keys() -> dict[str, dict[str, str]]:
    """Build a map of {lang_code: {audio_key: text}} for every menu position
    that lang could appear in across all configured states."""
    out: dict[str, dict[str, str]] = {lang: {} for lang in TARGET_LANGS}

    # Each lang's menu text for every digit position 1..N. The webhook
    # generates audio_key = f"menu_{lang}_{digit}".
    for state, allowed in STATE_TO_MENU.items():
        for new_digit, lang_code in enumerate(allowed, start=1):
            if lang_code in TARGET_LANGS:
                key = f"menu_{lang_code}_{new_digit}"
                out[lang_code][key] = MENU_TEXT_BY_LANG[lang_code].format(digit=new_digit)
    # Plus the default 9-language menu (state unknown)
    for new_digit, (_d, lang_code, _l, _m) in enumerate(LANGUAGE_MENU_LINES, start=1):
        if lang_code in TARGET_LANGS:
            key = f"menu_{lang_code}_{new_digit}"
            out[lang_code][key] = MENU_TEXT_BY_LANG[lang_code].format(digit=new_digit)
    return out


def _ivr_audio_keys() -> dict[str, dict[str, str]]:
    """Build (lang -> {audio_key: text}) for all main-IVR prompts the
    webhook references via _lang_voice / _lang_voice_in_collect."""
    out: dict[str, dict[str, str]] = {lang: {} for lang in TARGET_LANGS}

    # welcome_<call_type>_<lang> and prompt_<call_type>_<lang>
    for lang in TARGET_LANGS:
        out[lang][f"welcome_confirmation_{lang}"] = t(P_CONFIRM_WELCOME, lang)
        out[lang][f"prompt_confirmation_{lang}"] = t(P_CONFIRM_PROMPT, lang)
        out[lang][f"welcome_rejection_{lang}"] = t(P_REJECT_WELCOME, lang)
        out[lang][f"prompt_rejection_{lang}"] = t(P_REJECT_PROMPT, lang)
        out[lang][f"no_input_{lang}"] = t(P_NO_INPUT, lang)

        # Action-message keys: action_msg_<lang>_<digit>
        out[lang][f"action_msg_{lang}_1_confirm"] = t(P_ORDER_CONFIRMED, lang)  # alias
        out[lang][f"action_msg_{lang}_1"] = t(P_REATTEMPT, lang)        # rejection press 1
        out[lang][f"action_msg_{lang}_2"] = t(P_CANCELLED, lang)        # rejection press 2

        # Agent-transfer messages: agent_msg_<lang>_<mode>
        out[lang][f"agent_msg_{lang}_live_transfer"] = t(P_AGENT_TRANSFER, lang)
        out[lang][f"agent_msg_{lang}_queued"] = t(P_CALLBACK_QUEUED, lang)

    return out


def _all_keys() -> dict[str, dict[str, str]]:
    out = _menu_audio_keys()
    ivr = _ivr_audio_keys()
    for lang in TARGET_LANGS:
        out[lang].update(ivr[lang])
    return out


# ---------- TTS backends ----------

def _gtts_synth(text: str, lang_code: str, out_mp3: Path) -> None:
    from gtts import gTTS

    g = gTTS(text=text, lang=GTTS_LANG_MAP[lang_code])
    g.save(str(out_mp3))


def _ffmpeg_to_kookoo_wav(in_path: Path, out_wav: Path) -> None:
    """Convert any audio to PCM 16-bit, 8kHz, mono WAV (KooKoo format)."""
    if not shutil.which("ffmpeg"):
        raise RuntimeError(
            "ffmpeg not on PATH. Install: brew install ffmpeg (macOS)"
        )
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(in_path),
            "-acodec", "pcm_s16le",
            "-ar", "8000",
            "-ac", "1",
            str(out_wav),
        ],
        check=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tts", choices=["gtts"], default="gtts",
                        help="TTS backend (only gTTS supported in this script)")
    parser.add_argument("--out", default="./audio_cache/wav",
                        help="Output directory for KooKoo-format WAVs")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite existing files")
    args = parser.parse_args()

    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = out_dir.parent / "_tmp_mp3"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    plan = _all_keys()

    total = sum(len(v) for v in plan.values())
    print(f"Generating {total} audio files into {out_dir} ...")

    done = 0
    skipped = 0
    failed: list[str] = []

    for lang_code in TARGET_LANGS:
        for key, text in plan[lang_code].items():
            wav_path = out_dir / f"{key}.wav"
            if wav_path.exists() and not args.force:
                print(f"  [skip] {key}.wav (exists)")
                skipped += 1
                continue
            try:
                mp3_path = tmp_dir / f"{key}.mp3"
                print(f"  [{lang_code}] {key}: {text[:50]}...")
                _gtts_synth(text, lang_code, mp3_path)
                _ffmpeg_to_kookoo_wav(mp3_path, wav_path)
                mp3_path.unlink(missing_ok=True)
                done += 1
            except Exception as exc:  # noqa: BLE001
                print(f"  [FAIL] {key}: {exc}")
                failed.append(key)

    # Cleanup tmp
    try:
        shutil.rmtree(tmp_dir)
    except Exception:  # noqa: BLE001
        pass

    print()
    print(f"Done. generated={done} skipped={skipped} failed={len(failed)}")
    if failed:
        print("Failed keys:")
        for k in failed:
            print(f"  - {k}")
        sys.exit(1)


if __name__ == "__main__":
    main()
