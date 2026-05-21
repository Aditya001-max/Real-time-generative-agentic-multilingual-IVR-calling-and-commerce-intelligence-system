"""Unit tests for app/services/regions.py."""
from app.services.greetings import SUPPORTED_LANGUAGES
from app.services.regions import DEFAULT_MENU, STATE_TO_MENU, menu_for_state


# ---------- 3-option states ----------

def test_gujarat_returns_three_options_ending_in_gu():
    menu = menu_for_state("GJ")
    assert menu == ("en", "hi", "gu")


def test_tamil_nadu_returns_three_options_ending_in_ta():
    assert menu_for_state("TN") == ("en", "hi", "ta")


def test_karnataka_returns_three_options_ending_in_kn():
    assert menu_for_state("KA") == ("en", "hi", "kn")


def test_kerala_returns_three_options_ending_in_ml():
    assert menu_for_state("KL") == ("en", "hi", "ml")


def test_west_bengal_returns_three_options_ending_in_bn():
    assert menu_for_state("WB") == ("en", "hi", "bn")


def test_maharashtra_returns_three_options_ending_in_mr():
    assert menu_for_state("MH") == ("en", "hi", "mr")


def test_andhra_and_telangana_both_telugu():
    assert menu_for_state("AP") == ("en", "hi", "te")
    assert menu_for_state("TS") == ("en", "hi", "te")


# ---------- 2-option Hindi-belt states ----------

def test_uttar_pradesh_returns_two_options_only():
    menu = menu_for_state("UP")
    assert menu == ("en", "hi")
    assert "gu" not in menu and "ta" not in menu


def test_bihar_returns_two_options_only():
    assert menu_for_state("BR") == ("en", "hi")


def test_delhi_returns_two_options_only():
    assert menu_for_state("DL") == ("en", "hi")


def test_punjab_returns_two_options_only():
    """Punjabi isn't one of our 9 supported langs → 2-option fallback."""
    assert menu_for_state("PB") == ("en", "hi")


# ---------- normalization ----------

def test_lowercase_state_is_normalized_to_uppercase():
    assert menu_for_state("tn") == ("en", "hi", "ta")
    assert menu_for_state("gj") == ("en", "hi", "gu")
    assert menu_for_state("up") == ("en", "hi")


def test_state_with_whitespace_is_trimmed():
    assert menu_for_state(" GJ ") == ("en", "hi", "gu")


# ---------- fallbacks ----------

def test_unknown_state_returns_default_two_option_menu():
    """Unknown state codes fall back to (en, hi). The earlier behaviour
    was to play all 9 languages, but that turned the picker into a 30-second
    wait that real callers hung up on. We narrow to English + Hindi by
    default and let circle/state lookup widen it when we have a hit."""
    assert menu_for_state("ZZ") == DEFAULT_MENU
    assert menu_for_state("ZZ") == ("en", "hi")


def test_none_state_returns_default_two_option_menu():
    assert menu_for_state(None) == DEFAULT_MENU


def test_empty_string_state_returns_default_two_option_menu():
    assert menu_for_state("") == DEFAULT_MENU


def test_default_menu_is_english_and_hindi_only():
    """Every other supported language is reachable only by an explicit
    state/circle hit — never via the default fallback."""
    assert DEFAULT_MENU == ("en", "hi")
    assert set(DEFAULT_MENU).issubset(set(SUPPORTED_LANGUAGES))


# ---------- coverage sanity ----------

def test_every_three_option_state_uses_a_supported_language():
    for code, menu in STATE_TO_MENU.items():
        if len(menu) == 3:
            assert menu[0] == "en", code
            assert menu[1] == "hi", code
            assert menu[2] in SUPPORTED_LANGUAGES, code


def test_every_two_option_state_is_english_hindi_only():
    for code, menu in STATE_TO_MENU.items():
        if len(menu) == 2:
            assert menu == ("en", "hi"), code
