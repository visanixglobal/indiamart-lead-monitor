"""
refresh_cookie.py
-----------------
Interactive helper to update the INDIAMART_COOKIE in .env
without restarting the application.

Usage:
    python refresh_cookie.py

The monitor reads .env on every request, so the new cookie
takes effect on the very next poll cycle.
"""

import sys
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).parent))

from app.config import ensure_env_example
from app.logger import get_logger

ensure_env_example()
logger = get_logger("refresh_cookie")

ENV_PATH = Path(".env")


def _read_env() -> dict:
    """Parse .env into a dict, preserving all existing keys."""
    pairs: dict = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, val = line.partition("=")
                pairs[key.strip()] = val.strip()
    return pairs


def _write_env(pairs: dict) -> None:
    """Write dict back to .env."""
    lines = [f"{k}={v}" for k, v in pairs.items()]
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    print("\n=== IndiaMART Cookie Refresh ===\n")
    print("Instructions:")
    print("  1. Open seller.indiamart.com in your browser")
    print("  2. Press F12 → Network tab")
    print("  3. Reload the page or navigate to Buy Leads")
    print("  4. Find request: getBLDisplayData")
    print("  5. Click it → Headers → Copy the entire 'Cookie' value\n")

    cookie = input("Paste complete Cookie header: ").strip()

    if not cookie:
        print("[ERROR] No cookie provided. Aborting.")
        sys.exit(1)

    pairs = _read_env()
    old_cookie = pairs.get("INDIAMART_COOKIE", "")
    pairs["INDIAMART_COOKIE"] = cookie

    _write_env(pairs)

    print("\n[OK] INDIAMART_COOKIE updated in .env")
    logger.info("Cookie refreshed (old length=%d, new length=%d)", len(old_cookie), len(cookie))
    print("\nThe monitor will use the new cookie on its next poll cycle.")
    print("No restart required.\n")


if __name__ == "__main__":
    main()
