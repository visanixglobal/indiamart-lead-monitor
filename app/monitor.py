"""
IndiaMART Lead Monitor – core polling engine.
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

from app.config import get_cookie, get_glusrid, get_poll_interval, is_configured, get_quiet_hours_start, get_quiet_hours_end
from app.database import init_db, insert_lead, lead_exists, get_stats
from app.logger import get_logger
from app.ntfy_service import send_ntfy_alert, send_heartbeat, send_going_quiet, send_good_morning, send_ntfy_text
from app.parser import parse_leads
from app.shortlist_service import maybe_shortlist
from app.telegram_service import send_lead_alert

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Raw response archive (last 100 files for debugging)
# ---------------------------------------------------------------------------
_RAW_DIR = Path(__file__).parent.parent / "logs" / "raw_responses"
_MAX_RAW_FILES = 100


def _save_raw(source: str, data: Any) -> None:
    try:
        _RAW_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = _RAW_DIR / f"{ts}_{source}.json"
        fname.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        # Prune oldest files beyond limit
        files = sorted(_RAW_DIR.glob("*.json"), key=lambda f: f.stat().st_mtime)
        for old in files[:-_MAX_RAW_FILES]:
            old.unlink(missing_ok=True)
    except Exception as exc:
        logger.warning("Could not save raw response: %s", exc)


# ---------------------------------------------------------------------------
# Base HTTP helpers
# ---------------------------------------------------------------------------

_BASE_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://seller.indiamart.com",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/142.0.0.0 Safari/537.36"
    ),
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
}

_SESSION_ERROR_PHRASES = [
    "login",
    "session",
    "expired",
    "unauthorized",
    "authentication",
    "auth failed",
    "not logged",
    "please login",
    "invalid session",
]
_SESSION_RETRY_INTERVAL = 300  # 5 minutes

# Shared state exposed to the API dashboard
state: Dict[str, Any] = {
    "last_poll_time": "",
    "last_successful_api_call": "",
    "running": False,
}


def _headers(referer: str) -> dict:
    h = dict(_BASE_HEADERS)
    h["Cookie"] = get_cookie()
    h["Referer"] = referer
    return h


def _is_session_error(data: Any, status: int) -> bool:
    if status in (401, 403):
        return True
    text = json.dumps(data).lower() if isinstance(data, (dict, list)) else str(data).lower()
    return any(p in text for p in _SESSION_ERROR_PHRASES)


def _post(url: str, payload: dict, referer: str, source_tag: str) -> Optional[Any]:
    """
    POST request wrapper.
    Returns parsed JSON or None on failure.
    Raises SessionExpiredError on auth failure.
    """
    logger.debug("Calling %s (%s)", url, source_tag)
    try:
        resp = requests.post(url, json=payload, headers=_headers(referer), timeout=30)
    except requests.RequestException as exc:
        logger.error("[%s] Network error: %s", source_tag, exc)
        return None

    logger.debug("[%s] HTTP %s", source_tag, resp.status_code)

    try:
        data = resp.json()
    except ValueError:
        logger.error("[%s] Non-JSON response (HTTP %s): %s", source_tag, resp.status_code, resp.text[:300])
        return None

    if _is_session_error(data, resp.status_code):
        raise SessionExpiredError("IndiaMART session expired. Refresh cookies.")

    _save_raw(source_tag, data)
    state["last_successful_api_call"] = datetime.now().isoformat()
    return data


# ---------------------------------------------------------------------------
# Endpoint 1: getBLDisplayData  (recent buy leads)
# ---------------------------------------------------------------------------

def fetch_bl_display() -> Optional[Any]:
    glusrid = get_glusrid()
    return _post(
        url="https://seller.indiamart.com/blreact/getBLDisplayData",
        payload={
            "LocPref": "4",
            "stateid": "",
            "city": "",
            "iso": "",
            "pref_city_lead": 0,
            "glusrid": glusrid,
            "inbox": "",
            "offer": "",
            "offer_type": "B",
            "start": 1,
            "end": 20,
            "UsageTyp": "",
            "quantity": "",
            "is_email": "",
            "is_gst": "",
            "is_mobnum": "",
            "is_busname": "",
            "mcatid": "",
            "sov": "",
            "eov": None,
            "enqType": "",
            "is_catalog": "",
        },
        referer="https://seller.indiamart.com/bltxn/?pref=recent",
        source_tag="getBLDisplayData",
    )


# ---------------------------------------------------------------------------
# Endpoint 2: getMoreLeadsData  (suggested / relevant leads)
# ---------------------------------------------------------------------------

def fetch_more_leads() -> Optional[Any]:
    glusrid = get_glusrid()
    return _post(
        url="https://seller.indiamart.com/blreact/getMoreLeadsData",
        payload={
            "glusrid": glusrid,
            "start": 1,
            "end": 25,
            "priority": "P",
            "requestarray": {
                "pref": "other_leads",
                "lead_typ": "suggested",
                "loc_pref": 8,
                "stateid": "",
                "cityid": "",
                "iso": "",
                "locPrefCookie": "4",
                "mcatid": [],
            },
        },
        referer="https://seller.indiamart.com/bltxn/?pref=relevant",
        source_tag="getMoreLeadsData",
    )


# ---------------------------------------------------------------------------
# Endpoint 3: getShortlistedData  (wishlisted leads)
# ---------------------------------------------------------------------------

def fetch_shortlisted() -> Optional[Any]:
    glusrid = get_glusrid()
    return _post(
        url="https://seller.indiamart.com/blreact/getShortlistedData",
        payload={
            "glusrid": glusrid,
            "start": 1,
            "end": 25,
        },
        referer="https://seller.indiamart.com/bltxn/myWishList/",
        source_tag="getShortlistedData",
    )


# ---------------------------------------------------------------------------
# Session error
# ---------------------------------------------------------------------------

class SessionExpiredError(Exception):
    pass


# Expose for test_connection.py
fetch_leads_raw = fetch_bl_display


# ---------------------------------------------------------------------------
# Quiet window helper
# ---------------------------------------------------------------------------

def _is_quiet_window(now_hour: int, start: int, end: int) -> bool:
    """Return True if now_hour falls inside the quiet window."""
    if start < end:
        return start <= now_hour < end
    else:
        return now_hour >= start or now_hour < end


# ---------------------------------------------------------------------------
# Core monitoring loop
# ---------------------------------------------------------------------------

def _process_source(data: Optional[Any], source_label: str) -> int:
    """Parse one API response and persist / alert on new leads."""
    if data is None:
        return 0

    leads = parse_leads(data)
    new_count = 0

    for lead in leads:
        if lead_exists(lead.lead_id):
            continue

        inserted = insert_lead(
            lead_id=lead.lead_id,
            product_name=lead.product_name,
            quantity=lead.quantity,
            buyer_city=lead.buyer_city,
            buyer_state=lead.buyer_state,
            buyer_country=lead.buyer_country,
            lead_value=lead.lead_value,
            raw_json=lead.raw,
            category=getattr(lead, "category", ""),
            enrichment_value=getattr(lead, "enrichment_value", ""),
            credits_needed=getattr(lead, "credits_needed", ""),
            purchase_status=getattr(lead, "purchase_status", ""),
            buyer_name=getattr(lead, "buyer_name", ""),
        )

        if inserted:
            new_count += 1
            logger.info(
                "NEW LEAD [%s] | id=%s | product=%s | city=%s",
                source_label,
                lead.lead_id,
                lead.product_name,
                lead.buyer_city,
            )
            send_lead_alert(lead)       # Telegram (when available)
            send_ntfy_alert(lead)       # ntfy.sh (works now, no ban)
            # Auto-shortlist by value threshold (if AUTO_SHORTLIST=true in .env)
            # Interactive shortlist via Telegram button is the primary method
            maybe_shortlist(lead)

    return new_count


def _process_poll() -> int:
    """
    Single poll cycle.
    Returns total number of new leads detected.
    """
    sources: List[Tuple[str, Any]] = [
        ("recent",    fetch_bl_display()),
        ("suggested", fetch_more_leads()),
    ]

    total_new = sum(_process_source(data, label) for label, data in sources)

    if total_new == 0:
        logger.debug("Poll complete – no new leads.")
    else:
        logger.info("Poll complete – %d new lead(s) detected.", total_new)

    return total_new


def run_monitor() -> None:
    """
    Blocking monitoring loop.
    Designed to be called from a background thread or directly.
    """
    from app.config import SETUP_BANNER

    init_db()
    state["running"] = True

    if not is_configured():
        print(SETUP_BANNER)
        logger.warning("IndiaMART credentials not configured. Waiting for .env…")
        while not is_configured():
            time.sleep(30)

    logger.info("IndiaMART Lead Monitor started. Polling 3 endpoints per cycle.")

    consecutive_session_errors = 0
    _HEARTBEAT_INTERVAL = 1800  # 30 minutes
    _SELFPING_INTERVAL  = 600   # 10 minutes (keeps Render free tier awake)
    _last_heartbeat     = 0.0
    _last_selfping      = 0.0
    _quiet_notified     = False
    _morning_notified   = False
    _overnight_leads    = 0

    while True:
        state["last_poll_time"] = datetime.now().isoformat()
        now_hour = datetime.now().hour
        quiet_start = get_quiet_hours_start()
        quiet_end   = get_quiet_hours_end()

        try:
            # Skip polling during quiet hours — resume at QUIET_HOURS_END
            if _is_quiet_window(now_hour, quiet_start, quiet_end):
                logger.debug("Quiet hours (%d:00–%d:00) — polling paused.", quiet_start, quiet_end)
                # Still track overnight leads if any slipped through
                pass
            else:
                new_leads = _process_poll()
                consecutive_session_errors = 0

            # --- Going quiet message (once at quiet start hour) ---
            if now_hour == quiet_start and not _quiet_notified:
                stats = get_stats()
                send_going_quiet(quiet_end, today_leads=stats["today_leads"])
                _quiet_notified  = True
                _morning_notified = False
                _overnight_leads  = 0

            # Reset quiet flag when we leave the quiet window
            if not _is_quiet_window(now_hour, quiet_start, quiet_end):
                _quiet_notified = False

            # --- Good morning message (once at quiet end hour) ---
            if now_hour == quiet_end and not _morning_notified:
                stats = get_stats()
                send_good_morning(
                    overnight_leads=_overnight_leads,
                    total_leads=stats["total_leads"],
                )
                _morning_notified = True
                _overnight_leads  = 0

            # --- Heartbeat every 30 minutes ---
            import time as _time
            now_ts = _time.time()
            if now_ts - _last_heartbeat >= _HEARTBEAT_INTERVAL:
                stats = get_stats()
                send_heartbeat(
                    total_leads=stats["total_leads"],
                    today_leads=stats["today_leads"],
                    last_poll=datetime.now().strftime("%H:%M:%S UTC"),
                )
                _last_heartbeat = now_ts

        except SessionExpiredError as exc:
            consecutive_session_errors += 1
            logger.warning(str(exc))
            logger.info(
                "Session retry in %ds (attempt %d).",
                _SESSION_RETRY_INTERVAL,
                consecutive_session_errors,
            )
            # Notify on first expiry only (not every 5 min retry)
            if consecutive_session_errors == 1:
                send_ntfy_text(
                    f"IndiaMART session expired.\nRun refresh_cookie.py on your laptop\nto restore full functionality.",
                    title="Cookie Refresh Needed"
                )
            time.sleep(_SESSION_RETRY_INTERVAL)
            continue

        except Exception as exc:
            logger.exception("Unexpected error in monitor loop: %s", exc)

        interval = get_poll_interval()
        logger.debug("Sleeping %ds until next poll.", interval)
        time.sleep(interval)
