"""
Telegram notification service with interactive inline buttons.

Flow:
  1. New lead detected → send alert message with two inline buttons:
       [✅ Shortlist]   [❌ Skip]

  2. User taps a button on iPhone → Telegram sends a callback_query to the bot.

  3. TelegramBotHandler (long-polling thread) receives the callback:
       - "shortlist:<lead_id>" → calls shortlist_service.shortlist_lead()
       - "skip:<lead_id>"      → does nothing, answers callback to remove spinner

  4. Bot edits the original message to show the outcome:
       ✅ Shortlisted!   or   ❌ Skipped

The callback handler runs in its own daemon thread alongside the monitor.
Uses plain requests + long-polling (getUpdates) — no external bot framework needed.
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from typing import Any, Dict, Optional

import requests

from app.config import get_telegram_bot_token, get_telegram_chat_id
from app.logger import get_logger
from app.parser import ParsedLead

logger = get_logger(__name__)

_TIMEOUT = 15
_POLL_TIMEOUT = 30        # long-poll seconds for getUpdates
_RETRY_DELAY = 5          # seconds between error retries

# Pending shortlist actions: {lead_id: ParsedLead}
# Populated when a message is sent, consumed when user taps a button.
_pending: Dict[str, ParsedLead] = {}
_pending_lock = threading.Lock()


# ---------------------------------------------------------------------------
# MarkdownV2 escaping
# ---------------------------------------------------------------------------

def _escape(text: str) -> str:
    special = r"\_*[]()~`>#+-=|{}.!"
    for ch in special:
        text = text.replace(ch, f"\\{ch}")
    return text


# ---------------------------------------------------------------------------
# Message builder
# ---------------------------------------------------------------------------

def _build_message(lead: ParsedLead) -> str:
    detected_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    gst_badge = "✅" if str(lead.buyer_gst_verified) == "1" else "❌"
    mob_badge = "✅" if str(lead.buyer_mobile_verified) == "1" else "❌"
    value_str = lead.best_value if hasattr(lead, "best_value") else (lead.lead_value or "N/A")

    lines = [
        "🚨 *NEW INDIAMART LEAD*\n",
        f"*Product:* {_escape(lead.product_name or 'N/A')}",
        f"*Category:* {_escape(getattr(lead, 'category', '') or 'N/A')}",
        f"*Quantity:* {_escape(lead.quantity or 'N/A')}",
        f"*City:* {_escape(lead.buyer_city or 'N/A')}",
        f"*State:* {_escape(lead.buyer_state or 'N/A')}",
        f"*Order Value:* {_escape(value_str)}",
        f"*GST Verified:* {gst_badge}  *Mobile Verified:* {mob_badge}",
        f"*Credits Needed:* {_escape(getattr(lead, 'credits_needed', '') or 'N/A')}",
        f"*Status:* {_escape(getattr(lead, 'purchase_status', '') or 'N/A')}",
        f"*Lead ID:* `{_escape(lead.lead_id)}`",
        f"*Detected At:* {_escape(detected_at)}",
    ]
    return "\n".join(lines)


def _inline_keyboard(lead_id: str) -> dict:
    """Return the inline keyboard with Shortlist / Skip buttons."""
    return {
        "inline_keyboard": [[
            {"text": "✅ Shortlist", "callback_data": f"shortlist:{lead_id}"},
            {"text": "❌ Skip",      "callback_data": f"skip:{lead_id}"},
        ]]
    }


# ---------------------------------------------------------------------------
# Telegram API helpers
# ---------------------------------------------------------------------------

def _api(method: str, token: str, **kwargs) -> Optional[dict]:
    url = f"https://api.telegram.org/bot{token}/{method}"
    try:
        resp = requests.post(url, timeout=_TIMEOUT, **kwargs)
        if resp.ok:
            return resp.json()
        logger.warning("Telegram %s → HTTP %s: %s", method, resp.status_code, resp.text[:200])
        return None
    except requests.RequestException as exc:
        logger.error("Telegram %s error: %s", method, exc)
        return None


def _answer_callback(token: str, callback_query_id: str, text: str = "") -> None:
    """Dismiss the loading spinner on the button."""
    _api("answerCallbackQuery", token,
         json={"callback_query_id": callback_query_id, "text": text, "show_alert": False})


def _edit_message(token: str, chat_id: str, message_id: int, new_text: str) -> None:
    """Replace the message text (removes buttons after action)."""
    _api("editMessageText", token, json={
        "chat_id": chat_id,
        "message_id": message_id,
        "text": new_text,
        "parse_mode": "MarkdownV2",
    })


# ---------------------------------------------------------------------------
# Public: send lead alert
# ---------------------------------------------------------------------------

def send_lead_alert(lead: ParsedLead) -> bool:
    """
    Send a lead alert message with [✅ Shortlist] [❌ Skip] buttons.
    Registers the lead as pending so the callback handler can act on it.
    """
    token = get_telegram_bot_token()
    chat_id = get_telegram_chat_id()

    if not token or not chat_id:
        logger.warning(
            "Telegram not configured. Skipping alert for lead %s.", lead.lead_id
        )
        return False

    result = _api("sendMessage", token, json={
        "chat_id": chat_id,
        "text": _build_message(lead),
        "parse_mode": "MarkdownV2",
        "reply_markup": _inline_keyboard(lead.lead_id),
    })

    if result and result.get("ok"):
        with _pending_lock:
            _pending[lead.lead_id] = lead
        logger.info("Telegram alert sent for lead %s (with shortlist button)", lead.lead_id)
        return True

    logger.error("Failed to send Telegram alert for lead %s", lead.lead_id)
    return False


def send_text(message: str) -> bool:
    """Send a plain text message (system notifications, no buttons)."""
    token = get_telegram_bot_token()
    chat_id = get_telegram_chat_id()
    if not token or not chat_id:
        return False
    result = _api("sendMessage", token, json={"chat_id": chat_id, "text": message})
    return bool(result and result.get("ok"))


# ---------------------------------------------------------------------------
# Callback handler thread
# ---------------------------------------------------------------------------

class TelegramBotHandler:
    """
    Long-polls Telegram for callback_query updates and handles button taps.
    Runs as a background daemon thread.
    """

    def __init__(self) -> None:
        self._offset = 0
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._running:
            return
        token = get_telegram_bot_token()
        if not token:
            logger.warning("Telegram bot token not set — callback handler not started.")
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, name="telegram-callback", daemon=True
        )
        self._thread.start()
        logger.info("Telegram callback handler started.")

    def stop(self) -> None:
        self._running = False

    def _loop(self) -> None:
        while self._running:
            token = get_telegram_bot_token()
            if not token:
                time.sleep(10)
                continue
            try:
                self._poll_once(token)
            except Exception as exc:
                logger.error("Telegram callback loop error: %s", exc)
                time.sleep(_RETRY_DELAY)

    def _poll_once(self, token: str) -> None:
        url = f"https://api.telegram.org/bot{token}/getUpdates"
        try:
            resp = requests.post(
                url,
                json={"offset": self._offset, "timeout": _POLL_TIMEOUT,
                      "allowed_updates": ["callback_query"]},
                timeout=_POLL_TIMEOUT + 5,
            )
        except requests.RequestException as exc:
            logger.debug("getUpdates network error: %s", exc)
            time.sleep(_RETRY_DELAY)
            return

        if not resp.ok:
            logger.debug("getUpdates HTTP %s", resp.status_code)
            time.sleep(_RETRY_DELAY)
            return

        data = resp.json()
        for update in data.get("result", []):
            self._offset = update["update_id"] + 1
            cq = update.get("callback_query")
            if cq:
                self._handle_callback(token, cq)

    def _handle_callback(self, token: str, cq: dict) -> None:
        callback_id = cq["id"]
        chat_id = str(cq["message"]["chat"]["id"])
        message_id = cq["message"]["message_id"]
        data = cq.get("data", "")
        original_text = cq["message"].get("text", "")

        logger.info("Callback received: %s", data)

        if data.startswith("shortlist:"):
            lead_id = data.split(":", 1)[1]
            self._do_shortlist(token, callback_id, chat_id, message_id,
                               lead_id, original_text)

        elif data.startswith("skip:"):
            lead_id = data.split(":", 1)[1]
            _answer_callback(token, callback_id, "Skipped")
            # Edit message to remove buttons and mark as skipped
            _edit_message(
                token, chat_id, message_id,
                original_text + "\n\n_❌ Skipped_"
            )
            with _pending_lock:
                _pending.pop(lead_id, None)
            logger.info("Lead %s skipped by user", lead_id)

        else:
            _answer_callback(token, callback_id)

    def _do_shortlist(self, token: str, callback_id: str, chat_id: str,
                      message_id: int, lead_id: str, original_text: str) -> None:
        # Import here to avoid circular import
        from app.shortlist_service import shortlist_lead

        with _pending_lock:
            lead = _pending.get(lead_id)

        if lead is None:
            # Lead not in memory (e.g. restart) — create a minimal stub
            # so shortlist_service can still make the API call if mcatid is known
            logger.warning("Lead %s not in pending cache — attempting shortlist anyway", lead_id)
            _answer_callback(token, callback_id, "⚠️ Lead data not in memory, cannot shortlist")
            return

        success = shortlist_lead(lead)

        if success:
            _answer_callback(token, callback_id, "✅ Shortlisted on IndiaMART!")
            _edit_message(
                token, chat_id, message_id,
                original_text + "\n\n_✅ Shortlisted on IndiaMART_"
            )
            logger.info("Lead %s shortlisted via Telegram button", lead_id)
        else:
            _answer_callback(token, callback_id, "❌ Shortlist failed — check logs")
            _edit_message(
                token, chat_id, message_id,
                original_text + "\n\n_⚠️ Shortlist failed \\(check logs\\)_"
            )

        with _pending_lock:
            _pending.pop(lead_id, None)


# Module-level singleton — started from api.py startup
bot_handler = TelegramBotHandler()
