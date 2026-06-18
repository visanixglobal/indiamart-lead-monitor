"""
Configuration management.
Reads from .env on every access to support hot-reload of cookies.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

ENV_PATH = Path(__file__).parent.parent / ".env"
ENV_EXAMPLE_PATH = Path(__file__).parent.parent / ".env.example"

ENV_EXAMPLE_CONTENT = """# IndiaMART Credentials
# Obtain from seller.indiamart.com → F12 → Network → getBLDisplayData request
GLUSRID=
INDIAMART_COOKIE=

# Monitoring
POLL_INTERVAL=60

# Telegram Alerts
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
"""


def ensure_env_example() -> None:
    """Create .env.example if it does not exist."""
    if not ENV_EXAMPLE_PATH.exists():
        ENV_EXAMPLE_PATH.write_text(ENV_EXAMPLE_CONTENT)


def _load() -> None:
    """Force-reload .env from disk."""
    load_dotenv(dotenv_path=ENV_PATH, override=True)


def get_glusrid() -> str:
    _load()
    return os.getenv("GLUSRID", "").strip()


def get_cookie() -> str:
    _load()
    cookie = os.getenv("INDIAMART_COOKIE", "").strip()
    # Remove any non-latin-1 characters that would break HTTP headers
    cookie = cookie.encode("latin-1", errors="ignore").decode("latin-1")
    return cookie


def get_poll_interval() -> int:
    _load()
    try:
        return int(os.getenv("POLL_INTERVAL", "60"))
    except ValueError:
        return 60


def get_ntfy_topic() -> str:
    _load()
    return os.getenv("NTFY_TOPIC", "").strip()


def get_quiet_hours_start() -> int:
    """Hour (0-23) when notifications go silent. Default 1 (1 AM)."""
    _load()
    try:
        return int(os.getenv("QUIET_HOURS_START", "1"))
    except ValueError:
        return 1


def get_quiet_hours_end() -> int:
    """Hour (0-23) when notifications resume. Default 8 (8 AM)."""
    _load()
    try:
        return int(os.getenv("QUIET_HOURS_END", "8"))
    except ValueError:
        return 8


def get_telegram_bot_token() -> str:
    _load()
    return os.getenv("TELEGRAM_BOT_TOKEN", "").strip()


def get_telegram_chat_id() -> str:
    _load()
    return os.getenv("TELEGRAM_CHAT_ID", "").strip()


def is_configured() -> bool:
    """Return True when minimum required credentials are present."""
    return bool(get_glusrid() and get_cookie())


SETUP_BANNER = """
=========================================
     INDIAMART SETUP REQUIRED
=========================================

1. Open seller.indiamart.com
2. Press F12
3. Open Network tab
4. Find request: getBLDisplayData
5. Copy:
   - glusrid      (from request body)
   - Cookie       (entire Cookie header)
6. Paste values into .env:

   GLUSRID=80627141
   INDIAMART_COOKIE=<entire cookie header>

7. Restart application

=========================================
"""
