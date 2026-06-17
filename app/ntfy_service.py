"""
ntfy_service.py
---------------
Push notifications via ntfy.sh — free, no signup.

Notification types:
  1. CRITICAL ALERT  — instant when a new lead arrives (suppressed during quiet hours)
  2. HEARTBEAT       — every 30 min (suppressed during quiet hours)
  3. GOING QUIET     — sent once at QUIET_HOURS_START (e.g. 1 AM)
  4. GOOD MORNING    — sent once at QUIET_HOURS_END (e.g. 8 AM) with overnight summary

Quiet hours config (.env):
  QUIET_HOURS_START=1    # 1 AM
  QUIET_HOURS_END=8      # 8 AM
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

from app.logger import get_logger
from app.parser import ParsedLead

logger = get_logger(__name__)

_NTFY_BASE = "https://ntfy.sh"
_TIMEOUT   = 10


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_topic() -> str:
    load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env", override=True)
    return os.getenv("NTFY_TOPIC", "").strip()


def _is_quiet_hours() -> bool:
    from app.config import get_quiet_hours_start, get_quiet_hours_end
    now_hour = datetime.now().hour
    start = get_quiet_hours_start()
    end   = get_quiet_hours_end()
    if start < end:
        return start <= now_hour < end        # e.g. 1–8
    else:
        return now_hour >= start or now_hour < end  # wraps midnight e.g. 22–6


def _post(topic: str, message: str, title: str,
          priority: str = "default", tags: str = "bell") -> bool:
    try:
        resp = requests.post(
            f"{_NTFY_BASE}/{topic}",
            data=message.encode("utf-8"),
            headers={
                "Title":        title,
                "Priority":     priority,
                "Tags":         tags,
                "Content-Type": "text/plain",
            },
            timeout=_TIMEOUT,
        )
        return resp.ok
    except requests.RequestException as exc:
        logger.error("ntfy send error: %s", exc)
        return False


# ---------------------------------------------------------------------------
# 1. Critical lead alert
# ---------------------------------------------------------------------------

def send_ntfy_alert(lead: ParsedLead) -> bool:
    """Urgent alert for a new lead. Suppressed during quiet hours."""
    topic = _get_topic()
    if not topic:
        return False

    if _is_quiet_hours():
        logger.debug("Quiet hours — lead alert suppressed for %s", lead.lead_id)
        return False

    value = lead.best_value if hasattr(lead, "best_value") else (lead.lead_value or "N/A")
    gst   = "GST:Yes" if str(lead.buyer_gst_verified) == "1" else "GST:No"
    mob   = "Mob:Yes" if str(lead.buyer_mobile_verified) == "1" else "Mob:No"

    ok = _post(
        topic,
        message=(
            f"Qty: {lead.quantity or 'N/A'}\n"
            f"City: {lead.buyer_city or 'N/A'}, {lead.buyer_state or 'N/A'}\n"
            f"Value: {value}\n"
            f"{gst}  {mob}  Credits: {getattr(lead, 'credits_needed', 'N/A')}\n"
            f"ID: {lead.lead_id}\n"
            f"Time: {datetime.now().strftime('%H:%M:%S')}"
        ),
        title=f"NEW LEAD: {lead.product_name or 'IndiaMART'}",
        priority="urgent",
        tags="rotating_light,india",
    )
    if ok:
        logger.info("ntfy CRITICAL alert sent for lead %s", lead.lead_id)
    else:
        logger.error("ntfy critical alert FAILED for lead %s", lead.lead_id)
    return ok


# ---------------------------------------------------------------------------
# 2. Heartbeat every 30 minutes
# ---------------------------------------------------------------------------

def send_heartbeat(total_leads: int, today_leads: int, last_poll: str) -> bool:
    """Suppressed during quiet hours."""
    topic = _get_topic()
    if not topic:
        return False

    if _is_quiet_hours():
        logger.debug("Quiet hours — heartbeat suppressed")
        return False

    ok = _post(
        topic,
        message=(
            f"Status: Running\n"
            f"Last poll: {last_poll}\n"
            f"Leads today: {today_leads}\n"
            f"Total leads: {total_leads}"
        ),
        title=f"Monitor OK [{datetime.now().strftime('%H:%M')}]",
        priority="low",
        tags="white_check_mark",
    )
    if ok:
        logger.info("ntfy heartbeat sent")
    return ok


# ---------------------------------------------------------------------------
# 3. Going quiet (sent at QUIET_HOURS_START)
# ---------------------------------------------------------------------------

def send_going_quiet(quiet_end_hour: int, today_leads: int = 0) -> bool:
    """One-time message at start of quiet window."""
    topic = _get_topic()
    if not topic:
        return False

    ok = _post(
        topic,
        message=(
            f"No notifications until {quiet_end_hour:02d}:00.\n"
            f"Monitor keeps running in the background.\n"
            f"Leads detected today: {today_leads}\n"
            f"Good night!"
        ),
        title=f"Monitor going quiet until {quiet_end_hour:02d}:00",
        priority="low",
        tags="moon,zzz",
    )
    if ok:
        logger.info("ntfy going-quiet message sent")
    return ok


# ---------------------------------------------------------------------------
# 4. Good morning (sent at QUIET_HOURS_END)
# ---------------------------------------------------------------------------

def send_good_morning(overnight_leads: int, total_leads: int) -> bool:
    """One-time message when quiet window ends. Reports overnight leads."""
    topic = _get_topic()
    if not topic:
        return False

    if overnight_leads > 0:
        body = (
            f"Notifications resumed.\n"
            f"Leads overnight: {overnight_leads} — check IndiaMART now!\n"
            f"Total leads: {total_leads}"
        )
    else:
        body = (
            f"Notifications resumed.\n"
            f"No leads overnight.\n"
            f"Total leads: {total_leads}\n"
            f"Watching for new leads..."
        )

    ok = _post(
        topic,
        message=body,
        title="Good morning — Monitor active",
        priority="default",
        tags="sunny,bell",
    )
    if ok:
        logger.info("ntfy good-morning sent (overnight=%d)", overnight_leads)
    return ok


# ---------------------------------------------------------------------------
# 5. Plain text utility
# ---------------------------------------------------------------------------

def send_ntfy_text(message: str, title: str = "IndiaMART Monitor") -> bool:
    topic = _get_topic()
    if not topic:
        return False
    return _post(topic, message, title)


def test_ntfy() -> bool:
    topic = _get_topic()
    if not topic:
        print("NTFY_TOPIC not set in .env")
        return False
    print(f"Sending test to: ntfy.sh/{topic}")
    ok = send_ntfy_text("Monitor connectivity test — working correctly.", "Test OK")
    print("[OK] Check your phone." if ok else "[FAIL] Check topic and internet.")
    return ok
