"""
Core configuration — loads .env and exposes typed settings.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Telephony — Ozonetel KooKoo (block 7)
    OZONETEL_API_KEY: str = ""
    OZONETEL_USERNAME: str = ""
    OZONETEL_DID: str = ""
    # Defaults match the raw KooKoo CPaaS endpoint per Ozonetel support.
    # CloudAgent users override OZONETEL_API_BASE / OZONETEL_OUTBOUND_PATH in .env.
    OZONETEL_API_BASE: str = "https://in1-cpaas.ozonetel.com"
    OZONETEL_OUTBOUND_PATH: str = "/outbound/outbound.php"
    # ID of the CloudAgent IVR Flow that owns the call experience (prompts,
    # menus, agent transfer). When set, place_call() routes the call into
    # that flow via app_id+extra_data instead of returning XML from our
    # /webhook/voice-start. Find/create flows under Configurations → IVR
    # Flows in the CloudAgent dashboard.
    OZONETEL_APP_ID: str = ""

    # CloudAgent Campaign settings — required to trigger CloudAgent IVR
    # Flows. When OZONETEL_CAMPAIGN_NAME is set, place_call() POSTs to the
    # CloudAgent AddCampaignData API instead of the CPaaS outbound.php.
    # The campaign in CloudAgent must already exist and be linked to the
    # IVR Flow (Campaigns section, type "IVR Nonagentwise").
    OZONETEL_CAMPAIGN_NAME: str = ""
    OZONETEL_CLOUDAGENT_API_BASE: str = "https://api.cloudagent.ozonetel.com"

    # When True, the webhook emits the Google Wavenet voice attribute in
    # <playtext type="ggl" voice="..."> tags. Requires Ozonetel Pro and
    # KooKoo to actually honour the voice attribute (older accounts
    # silently dropped audio when this was set — confirm with Ozonetel
    # support before flipping on). False = default Google Standard voice
    # (robotic but reliable). Voice IDs per language live in kookoo_xml.py.
    KOOKOO_USE_WAVENET: bool = False

    BASE_URL: str = "http://localhost:8000"
    # Where pre-recorded audio for languages KooKoo native TTS does NOT
    # cover (ta, ml, bn, mr, gu) is served. Empty = derive from BASE_URL.
    AUDIO_PUBLIC_BASE: str = ""

    # DB
    DATABASE_URL: str = "sqlite:///./db.sqlite3"

    # Supabase (optional — only needed if you use Storage or direct client)
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_ANON_KEY: str = ""
    SUPABASE_STORAGE_BUCKET: str = "imports"

    # Redis / Celery (retry engine — block 5)
    REDIS_URL: str = "redis://localhost:6379/0"

    # Working hours
    WORKING_HOURS_START: int = 9
    WORKING_HOURS_END: int = 18
    TIMEZONE: str = "Asia/Kolkata"

    # Dev/test override: if True, voice-start ALWAYS plays the language picker,
    # even for callers whose preferred_language is already saved. Use during
    # IVR testing so you don't have to clear the DB row between calls.
    # Leave False in production so returning customers skip the picker.
    FORCE_LANGUAGE_PICKER: bool = False

    # Ops team hunt-group number (E.164 or SIP URI). Used by help_router for
    # live transfers when a customer presses the help digit during business
    # hours. Leave empty to disable live transfer (will queue every help
    # request as a callback instead).
    TEAM_HUNT_GROUP: str = ""

    # Excel export settings (daily Celery beat task at 22:00 IST)
    EXCEL_EXPORT_DIR: str = "./exports"
    EXCEL_EXPORT_EMAIL: str = ""        # blank = file-only, no email
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASS: str = ""
    SMTP_FROM: str = "Divine Hindu IVR <ivr@divinehindu.in>"

    # Action Engine integrations (block 9)
    OMS_API_URL: str = ""
    OMS_API_KEY: str = ""
    NOTIFICATION_API_URL: str = ""
    NOTIFICATION_API_KEY: str = ""

    # ============================================================
    # AI VOICE — Provider chain
    # ============================================================
    # Master switch for the self-hosted TTS chain (Coqui / ElevenLabs).
    # When False (default), the webhook routes speech through Ozonetel
    # KooKoo Google TTS via <playtext type="ggl">. Set KOOKOO_USE_WAVENET
    # to control the voice quality of that path.
    USE_AI_VOICE: bool = False
    # Comma-separated priority order. First available wins; others act as fallback.
    # Examples:
    #   coqui              — open source only (free, recommended for cost)
    #   coqui,elevenlabs   — open source first, paid as fallback (recommended)
    #   elevenlabs         — paid only (highest quality)
    TTS_PROVIDERS: str = "coqui,elevenlabs"
    AUDIO_CACHE_DIR: str = "./audio_cache"

    # --- ElevenLabs (paid backend) ---
    ELEVENLABS_API_KEY: str = ""
    ELEVENLABS_VOICE_ID: str = "21m00Tcm4TlvDq8ikWAM"  # Rachel
    ELEVENLABS_MODEL_ID: str = "eleven_flash_v2_5"
    ELEVENLABS_OUTPUT_FORMAT: str = "mp3_44100_128"
    ELEVENLABS_STABILITY: float = 0.5
    ELEVENLABS_SIMILARITY_BOOST: float = 0.75
    ELEVENLABS_STYLE: float = 0.0
    ELEVENLABS_USE_SPEAKER_BOOST: bool = True

    # --- Coqui XTTS-v2 (open source backend) ---
    USE_COQUI_TTS: bool = False
    COQUI_LANGUAGE: str = "en"  # en, es, fr, de, hi, ar, zh-cn, etc.
    # XTTS built-in speaker name (used when COQUI_SPEAKER_WAV is empty).
    COQUI_SPEAKER: str = "Ana Florence"
    # Optional: path to a 6-second WAV of any voice for cloning.
    COQUI_SPEAKER_WAV: str = ""

    # ============================================================
    # TICKETING — Provider chain (block 9)
    # ============================================================
    # Comma-separated priority. Examples:
    #   chatwoot         — open source only
    #   chatwoot,http    — open source first, generic HTTP fallback
    #   http             — your existing paid system (Zendesk/Freshdesk/etc.)
    #   none             — local-only (logs to DB only)
    TICKET_PROVIDERS: str = "chatwoot,http"

    # --- Chatwoot (open source) ---
    CHATWOOT_BASE_URL: str = ""             # e.g. http://localhost:3000
    CHATWOOT_API_TOKEN: str = ""
    CHATWOOT_ACCOUNT_ID: int = 1
    CHATWOOT_INBOX_ID: int = 1

    # --- Generic HTTP (your existing ticket system) ---
    TICKET_API_URL: str = ""
    TICKET_API_KEY: str = ""


settings = Settings()
