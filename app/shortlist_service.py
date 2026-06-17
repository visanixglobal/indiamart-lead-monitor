"""
shortlist_service.py
--------------------
Auto-shortlist (bookmark) leads that meet the configured criteria.

This is a READ-ONLY account action — it bookmarks a lead for easy
retrieval later.  It does NOT:
  - Consume lead credits
  - Reveal buyer contact details
  - Contact the buyer
  - Deduct anything from your account

Endpoint confirmed from live browser capture:
  POST https://seller.indiamart.com/blreact/markShortlist

Payload:
  {
    "glusrid":  "80627141",
    "mcatid":   "3001",           ← category ID from the lead
    "ofrid":    "146158350895",   ← ETO_OFR_ID (lead ID)
    "flag_val": "I",              ← "I" = LikeIt/shortlist, "D" = dislike/remove
    "status":   1,
    "source":   "MY_LATESTBL_LISTING"
  }

Configuration (.env):
  AUTO_SHORTLIST=true            ← master switch (default: false)
  SHORTLIST_MIN_VALUE=0          ← minimum approx order value in ₹ lakh (0 = all leads)

Value parsing:
  "Above 5 Lakh"    → 500000
  "Rs. 6 - 6.6 Lakh" → 600000   (lower bound of range)
  "₹ 10,000"        → 10000
"""

from __future__ import annotations

import os
import re
from typing import Optional

import requests

from app.config import get_cookie, get_glusrid
from app.logger import get_logger
from app.parser import ParsedLead

logger = get_logger(__name__)

_SHORTLIST_URL = "https://seller.indiamart.com/blreact/markShortlist"
_TIMEOUT = 15


# ---------------------------------------------------------------------------
# Config helpers (read from .env on every call)
# ---------------------------------------------------------------------------

def _auto_shortlist_enabled() -> bool:
    from dotenv import load_dotenv
    from pathlib import Path
    load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env", override=True)
    return os.getenv("AUTO_SHORTLIST", "false").strip().lower() in ("true", "1", "yes")


def _min_value_rupees() -> int:
    from dotenv import load_dotenv
    from pathlib import Path
    load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env", override=True)
    try:
        lakh = float(os.getenv("SHORTLIST_MIN_VALUE", "0"))
        return int(lakh * 100_000)
    except ValueError:
        return 0


# ---------------------------------------------------------------------------
# Value parser  (converts IndiaMART value strings to rupees)
# ---------------------------------------------------------------------------

def _parse_rupees(value_str: str) -> Optional[int]:
    """
    Convert IndiaMART order value strings to integer rupees.

    Examples:
      "Above 5 Lakh"          → 500_000
      "Rs. 6 - 6.6 Lakh"     → 600_000  (lower bound)
      "Rs. 1 - 2 Lakh"        → 100_000
      "₹ 25,000"              → 25_000
      "Above 1 Crore"         → 10_000_000
      "500 - 1000"            → 500      (bare numbers treated as rupees)
    Returns None if unparseable.
    """
    if not value_str:
        return None

    s = value_str.lower().replace(",", "").replace("₹", "").replace("rs.", "").strip()

    # Extract the first number in the string
    numbers = re.findall(r"[\d]+(?:\.\d+)?", s)
    if not numbers:
        return None

    first = float(numbers[0])

    # Determine multiplier
    if "crore" in s:
        return int(first * 10_000_000)
    if "lakh" in s or "lac" in s:
        return int(first * 100_000)
    if "thousand" in s or "k" in s:
        return int(first * 1_000)

    return int(first)


def _lead_qualifies(lead: ParsedLead, min_rupees: int) -> bool:
    """Return True if the lead's order value meets the minimum threshold."""
    if min_rupees <= 0:
        return True  # no filter — shortlist everything

    # Try top-level value first, then enrichment value
    for val_str in (lead.lead_value, lead.enrichment_value):
        rupees = _parse_rupees(val_str)
        if rupees is not None and rupees >= min_rupees:
            return True

    return False


# ---------------------------------------------------------------------------
# markShortlist API call
# ---------------------------------------------------------------------------

def _get_mcatid(lead: ParsedLead) -> str:
    """
    Extract category ID from the raw lead dict.
    Confirmed field: FK_GLCAT_MCAT_ID  (e.g. "3001")
    """
    raw = lead.raw or {}
    return str(
        raw.get("FK_GLCAT_MCAT_ID")
        or raw.get("fk_glcat_mcat_id")
        or raw.get("PRIME_MCAT_ID")
        or raw.get("prime_mcat_id")
        or ""
    )


def shortlist_lead(lead: ParsedLead) -> bool:
    """
    Shortlist (bookmark) a lead via markShortlist.

    Returns True on success, False on failure.
    Never raises.

    This action:
      ✅ Saves the lead to your Shortlisted tab
      ❌ Does NOT consume credits
      ❌ Does NOT contact the buyer
    """
    glusrid = get_glusrid()
    cookie = get_cookie()

    if not glusrid or not cookie:
        logger.warning("Cannot shortlist — credentials not configured.")
        return False

    mcatid = _get_mcatid(lead)
    if not mcatid:
        logger.warning("Cannot shortlist lead %s — mcatid not found in raw data.", lead.lead_id)
        return False

    payload = {
        "glusrid": glusrid,
        "mcatid": mcatid,
        "ofrid": lead.lead_id,
        "flag_val": "I",          # "I" = LikeIt
        "status": 1,
        "source": "MY_LATESTBL_LISTING",
    }

    headers = {
        "Content-Type": "application/json",
        "Accept": "*/*",
        "Origin": "https://seller.indiamart.com",
        "Referer": "https://seller.indiamart.com/bltxn/?pref=relevant&D_L_B=1",
        "Cookie": cookie,
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/142.0.0.0 Safari/537.36"
        ),
    }

    try:
        resp = requests.post(_SHORTLIST_URL, json=payload, headers=headers, timeout=_TIMEOUT)
        if resp.ok:
            logger.info(
                "✅ Auto-shortlisted lead %s (%s) | value=%s",
                lead.lead_id, lead.product_name, lead.best_value,
            )
            return True
        else:
            logger.warning(
                "markShortlist returned HTTP %s for lead %s: %s",
                resp.status_code, lead.lead_id, resp.text[:200],
            )
            return False
    except requests.RequestException as exc:
        logger.error("Network error calling markShortlist for lead %s: %s", lead.lead_id, exc)
        return False


# ---------------------------------------------------------------------------
# Public entry point called from monitor
# ---------------------------------------------------------------------------

def maybe_shortlist(lead: ParsedLead) -> None:
    """
    Called after a new lead is detected.
    Shortlists only if AUTO_SHORTLIST=true and lead value ≥ SHORTLIST_MIN_VALUE.
    """
    if not _auto_shortlist_enabled():
        return

    min_rupees = _min_value_rupees()

    if not _lead_qualifies(lead, min_rupees):
        logger.debug(
            "Lead %s skipped for shortlisting (value=%s, min=₹%s)",
            lead.lead_id, lead.best_value, f"{min_rupees:,}",
        )
        return

    shortlist_lead(lead)
