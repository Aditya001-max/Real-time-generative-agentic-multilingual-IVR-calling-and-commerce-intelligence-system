"""
Greetings & language picker — played BEFORE the user picks a language.

Flow:
  1. English-only context greeting ("Namaste, I am Kavya, calling you
     from Divine Hindu...") so the user knows why they're being called.
     Rendered via Ozonetel KooKoo's <playtext lang="EN"> in the IVR XML.
  2. Up to nine language menu lines, each spoken in its own language.
     For languages KooKoo native TTS supports (EN/HI/TE/KA), <playtext>
     is used directly. For ta/ml/bn/mr/gu, pre-recorded WAVs served from
     /audio/<key>.wav are played via <playaudio>. DTMF only at this
     stage — speech recognition before language is known is unreliable.

This module is intentionally separate from `ivr_scripts.py` because:
  • These strings are inherently multilingual (no PROMPTS[id][lang] lookup —
    each line is already in its own language).
  • They run only during the language-picker phase, before
    `User.preferred_language` is set.

NOTE on Tamil: Earlier we hit "Say: Invalid text" with a standalone vowel
sign `ை` (invalid orthography — vowel signs must attach to a consonant).
Now using the independent vowel `ஐ`. All other languages have been
verified to use only well-formed Unicode sequences.
"""

COMPANY_NAME = "Divine Hindu"
# IPA hint kept for the AI-voice TTS cache (Coqui / ElevenLabs may consume
# it). Reads roughly "div-EYEN HIN-doo". Ozonetel KooKoo's <playtext> does
# not consume it \u2014 KooKoo speaks "Divine Hindu" with its default voice.
COMPANY_NAME_IPA = "d\u026a\u02c8va\u026an \u02c8h\u026andu\u02d0"

# Greeting parts. The webhook emits these as two <Say> blocks:
#   <Say>{prefix} <phoneme>{COMPANY_NAME}</phoneme></Say>
#   <Say>{trailing}</Say>
GREETING_PARTS: dict[str, dict[str, str]] = {
    "CONFIRMATION": {
        "prefix": "Namaste, I am Kavya, calling you from ",
        "trailing": ". This call is regarding your recent order. "
                    "Please choose your preferred language to continue.",
    },
    "REJECTION": {
        "prefix": "Namaste, I am Kavya, calling you from ",
        "trailing": ". This call is regarding your recent order delivery. "
                    "Please choose your preferred language to continue.",
    },
}


# 9 languages, in menu order. Tuple = (digit, lang_code, locale, menu_text)
# `locale` is the BCP-47 locale tag (e.g. 'hi-IN'). Currently used as a hint
# for the AI voice cache key; Ozonetel KooKoo's <playtext> uses uppercase
# 2-letter codes (EN/HI/TE/KA), mapped in app/services/kookoo_xml.py.
#
# All menu_text strings are kept SHORT and grammatically simple — Twilio Polly's
# Indian-language voices handle short, clear commands more reliably than
# longer sentences.
LANGUAGE_MENU_LINES: list[tuple[str, str, str, str]] = [
    # The leading digit string is the "default" / fallback ordering when the
    # full 9-language menu is shown (no state). When app/services/regions.py
    # filters the menu down to a region-specific subset, the digit is
    # re-derived from MENU_TEXT_BY_LANG with the correct {digit} placeholder.
    ("1", "en", "en-IN", "For English, press 1."),
    ("2", "hi", "hi-IN", "हिंदी के लिए 2 दबाएं।"),
    # Tamil — uses independent vowel ஐ (NOT standalone vowel sign ை)
    ("3", "ta", "ta-IN", "தமிழுக்கு 3 ஐ அழுத்தவும்."),
    ("4", "te", "te-IN", "తెలుగు కోసం 4 నొక్కండి."),
    ("5", "kn", "kn-IN", "ಕನ್ನಡಕ್ಕಾಗಿ 5 ಒತ್ತಿರಿ."),
    ("6", "ml", "ml-IN", "മലയാളത്തിന് 6 അമർത്തുക."),
    ("7", "bn", "bn-IN", "বাংলার জন্য 7 চাপুন।"),
    ("8", "mr", "mr-IN", "मराठीसाठी 8 दाबा."),
    ("9", "gu", "gu-IN", "ગુજરાતી માટે 9 દબાવો."),
]


# Templated menu text per language with a {digit} placeholder.
# Used when the picker is renumbered by region (e.g. Tamil Nadu hears
# Tamil at digit 3 even though Tamil is index 2 in the full list).
MENU_TEXT_BY_LANG: dict[str, str] = {
    "en": "For English, press {digit}.",
    "hi": "हिंदी के लिए {digit} दबाएं।",
    "ta": "தமிழுக்கு {digit} ஐ அழுத்தவும்.",
    "te": "తెలుగు కోసం {digit} నొక్కండి.",
    "kn": "ಕನ್ನಡಕ್ಕಾಗಿ {digit} ಒತ್ತಿರಿ.",
    "ml": "മലയാളത്തിന് {digit} അമർത്തുക.",
    "bn": "বাংলার জন্য {digit} চাপুন।",
    "mr": "मराठीसाठी {digit} दाबा.",
    "gu": "ગુજરાતી માટે {digit} દબાવો.",
}

SUPPORTED_LANGUAGES: tuple[str, ...] = tuple(lang for _, lang, _, _ in LANGUAGE_MENU_LINES)
DEFAULT_LANGUAGE = "en"
DIGIT_TO_LANG: dict[str, str] = {digit: lang for digit, lang, _, _ in LANGUAGE_MENU_LINES}
# BCP-47 locale tags (e.g. 'hi-IN') — used as cache keys and TTS hints.
LANG_TO_BCP47_LOCALE: dict[str, str] = {
    lang: locale for _, lang, locale, _ in LANGUAGE_MENU_LINES
}


def lang_for_digit(digit: str | None) -> str:
    """Map a DTMF digit to a language code, defaulting to English on invalid input."""
    if not digit:
        return DEFAULT_LANGUAGE
    return DIGIT_TO_LANG.get(digit.strip(), DEFAULT_LANGUAGE)


def bcp47_locale_for(lang: str) -> str:
    """Return the BCP-47 locale (e.g. 'hi-IN') for a language code."""
    return LANG_TO_BCP47_LOCALE.get(lang, "en-IN")