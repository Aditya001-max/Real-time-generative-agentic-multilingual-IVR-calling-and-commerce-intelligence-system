"""
Indian state → IVR-menu language mapping.

Each state code maps to a tuple of language codes the caller will see in
the picker, in display order. English and Hindi are always first; the
third slot is the state language when one of our 9 supported languages
matches the state.

Hindi-belt states get a 2-option menu (English + Hindi). Unknown / out of
India callers also get the 2-option menu — we never play all 9 languages,
because that turns into a 30-second wait the caller will hang up on.

State input comes from one of two sources, in priority order:
  1. /event/ payload's `state` field (2-letter ISO 3166-2:IN code) — set
     by the caller's CRM / OMS when the order is created. Authoritative
     when present.
  2. KooKoo's `circle` query parameter on the inbound webhook (telecom
     circle of the SIM that's being dialed). Used as a fallback so we
     still narrow the menu when the event payload didn't carry a state.

Resolved value lands on User.delivery_state and CallLog.delivery_state.
"""
from app.services.greetings import SUPPORTED_LANGUAGES


# 2-letter codes from ISO 3166-2:IN (matches Indian Census / postal usage).
STATE_TO_MENU: dict[str, tuple[str, ...]] = {
    # ---- 3-option states (English + Hindi + native) ----
    "TN": ("en", "hi", "ta"),  # Tamil Nadu
    "PY": ("en", "hi", "ta"),  # Puducherry
    "AP": ("en", "hi", "te"),  # Andhra Pradesh
    "TS": ("en", "hi", "te"),  # Telangana
    "TG": ("en", "hi", "te"),  # Telangana (alternate code)
    "KA": ("en", "hi", "kn"),  # Karnataka
    "KL": ("en", "hi", "ml"),  # Kerala
    "LD": ("en", "hi", "ml"),  # Lakshadweep
    "WB": ("en", "hi", "bn"),  # West Bengal
    "TR": ("en", "hi", "bn"),  # Tripura
    "AN": ("en", "hi", "bn"),  # Andaman & Nicobar Islands
    "MH": ("en", "hi", "mr"),  # Maharashtra
    "GA": ("en", "hi", "mr"),  # Goa
    "DN": ("en", "hi", "mr"),  # Dadra & Nagar Haveli + Daman & Diu (merged 2020)
    "DD": ("en", "hi", "mr"),  # Daman & Diu (legacy alias)
    "GJ": ("en", "hi", "gu"),  # Gujarat
    # ---- 2-option Hindi-belt + states whose native language we don't support ----
    "UP": ("en", "hi"),  # Uttar Pradesh
    "BR": ("en", "hi"),  # Bihar
    "MP": ("en", "hi"),  # Madhya Pradesh
    "RJ": ("en", "hi"),  # Rajasthan
    "HR": ("en", "hi"),  # Haryana
    "DL": ("en", "hi"),  # Delhi (NCT)
    "PB": ("en", "hi"),  # Punjab
    "HP": ("en", "hi"),  # Himachal Pradesh
    "UK": ("en", "hi"),  # Uttarakhand
    "UT": ("en", "hi"),  # Uttarakhand (legacy alias)
    "CT": ("en", "hi"),  # Chhattisgarh
    "CG": ("en", "hi"),  # Chhattisgarh (alternate code)
    "JH": ("en", "hi"),  # Jharkhand
    "JK": ("en", "hi"),  # Jammu & Kashmir
    "LA": ("en", "hi"),  # Ladakh
    "CH": ("en", "hi"),  # Chandigarh
    "OD": ("en", "hi"),  # Odisha
    "OR": ("en", "hi"),  # Odisha (legacy code)
    "AS": ("en", "hi"),  # Assam
    "SK": ("en", "hi"),  # Sikkim
    "AR": ("en", "hi"),  # Arunachal Pradesh
    "MN": ("en", "hi"),  # Manipur
    "MZ": ("en", "hi"),  # Mizoram
    "NL": ("en", "hi"),  # Nagaland
    "ML": ("en", "hi"),  # Meghalaya
}

# Fallback when state is missing, unknown, or outside India. Two options
# (English + Hindi) — never the full 9, which turns the picker into an
# unbearable 30-second wait that real callers hang up on.
DEFAULT_MENU: tuple[str, ...] = ("en", "hi")


# ---------------------------------------------------------------------------
# Telecom-circle (KooKoo `circle` param) → ISO 3166-2:IN state code
# ---------------------------------------------------------------------------
# KooKoo passes a `circle` query string on every inbound webhook (the
# telecom circle of the calling SIM, e.g. "UTTAR PRADESH (E)"). We use
# this to auto-detect region when the event payload didn't carry a
# `state`. Circle granularity is coarser than state (one circle can span
# several states), so the mapping is best-effort.
_CIRCLE_TO_STATE: dict[str, str] = {
    "ANDHRA PRADESH": "AP",
    "TELANGANA": "TS",
    "ASSAM": "AS",
    "BIHAR": "BR",
    "BIHAR & JHARKHAND": "BR",
    "JHARKHAND": "JH",
    "CHENNAI": "TN",
    "DELHI": "DL",
    "DELHI & NCR": "DL",
    "GUJARAT": "GJ",
    "HARYANA": "HR",
    "HIMACHAL PRADESH": "HP",
    "JAMMU & KASHMIR": "JK",
    "KARNATAKA": "KA",
    "KERALA": "KL",
    "KOLKATA": "WB",
    "MADHYA PRADESH": "MP",
    "MADHYA PRADESH & CHHATTISGARH": "MP",
    "CHHATTISGARH": "CT",
    "MAHARASHTRA": "MH",
    "MAHARASHTRA & GOA": "MH",
    "MUMBAI": "MH",
    "GOA": "GA",
    "ORISSA": "OD",
    "ODISHA": "OD",
    "PUNJAB": "PB",
    "RAJASTHAN": "RJ",
    "TAMIL NADU": "TN",
    "TAMIL NADU & PONDICHERRY": "TN",
    "UTTAR PRADESH": "UP",
    "UTTAR PRADESH (E)": "UP",
    "UTTAR PRADESH (W)": "UP",
    "UTTAR PRADESH EAST": "UP",
    "UTTAR PRADESH WEST": "UP",
    "UTTARAKHAND": "UK",
    "WEST BENGAL": "WB",
    "WEST BENGAL & ANDAMAN": "WB",
    # North-East — telecom-circle level only, picks the largest state.
    "NORTH EAST": "AS",
    "NORTHEAST": "AS",
}


def state_from_circle(circle: str | None) -> str | None:
    """Map a KooKoo telecom-circle string to a 2-letter state code.

    Returns None when we don't recognise the circle. Comparison is
    case-insensitive and ignores leading/trailing whitespace; punctuation
    is preserved (so "UTTAR PRADESH (E)" matches the table directly).
    """
    if not circle:
        return None
    key = circle.strip().upper()
    if key in _CIRCLE_TO_STATE:
        return _CIRCLE_TO_STATE[key]
    # Strip a trailing "(E)" / "(W)" / "(EAST)" / "(WEST)" suffix and retry.
    for suffix in (" (E)", " (W)", " (EAST)", " (WEST)"):
        if key.endswith(suffix):
            shortened = key[: -len(suffix)].rstrip()
            if shortened in _CIRCLE_TO_STATE:
                return _CIRCLE_TO_STATE[shortened]
    return None


def menu_for_state(state: str | None) -> tuple[str, ...]:
    """Return the IVR menu options for a 2-letter state code.

    Defaults to (English, Hindi) on missing / unknown codes — never the
    full 9-language list."""
    if not state:
        return DEFAULT_MENU
    return STATE_TO_MENU.get(state.strip().upper(), DEFAULT_MENU)
