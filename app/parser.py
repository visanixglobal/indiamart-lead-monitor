"""
IndiaMART Lead Parser — calibrated against real API responses.

Confirmed field mapping from live getBLDisplayData / getShortlistedData responses:

  Lead ID        → ETO_OFR_ID
  Product        → ETO_OFR_TITLE
  Quantity       → ETO_OFR_QTY  (often blank; fallback to ENRICHMENTINFO "Quantity")
  City           → GLUSR_CITY
  State          → GLUSR_STATE
  Country        → GLUSR_COUNTRY
  Order Value    → ETO_OFR_APPROX_ORDER_VALUE  (e.g. "Above 5 Lakh")
                   also available in ENRICHMENTINFO "Probable Order Value"
  Category       → ETO_OFR_GLCAT_MCAT_NAME  (e.g. "Teflon Rods")
  Date           → ETO_OFR_DATE  (e.g. "17-JUN-26")
  Date+Time      → OFR_DATE  (e.g. "20260617090328")
  Buyer Name     → GLUSR_NAME
  Buyer GST      → ETO_OFR_BUYER_IS_GST_VERF
  Buyer Mobile   → ETO_OFR_BUYER_IS_MOB_VERF
  Credits needed → ETO_CREDITS
  Purchase status→ PURCHASE_STATUS  ("OPEN" = not yet consumed)

The lead list lives in response["DisplayList"].
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, List, Optional

from app.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# ENRICHMENTINFO helpers
# ---------------------------------------------------------------------------

def _parse_enrichment(raw: dict) -> Dict[str, str]:
    """
    ENRICHMENTINFO is a JSON-encoded string like:
    {"1":[{"DESC":"Quantity","RESPONSE":"1000 Kg"},{"DESC":"Probable Order Value","RESPONSE":"Rs. 6 - 6.6 Lakh"},...]}
    Returns a flat dict: {"Quantity": "1000 Kg", "Probable Order Value": "Rs. 6 - 6.6 Lakh", ...}
    """
    ei = raw.get("ENRICHMENTINFO") or raw.get("enrichmentinfo")
    if not ei:
        return {}
    try:
        parsed = json.loads(ei)
        result = {}
        for items in parsed.values():
            if isinstance(items, list):
                for item in items:
                    desc = item.get("DESC", "")
                    resp = item.get("RESPONSE", "")
                    if desc:
                        result[desc] = str(resp)
        return result
    except Exception:
        return {}


def _pick(obj: dict, *keys: str, default: str = "") -> str:
    """Return first non-empty value for any of the given keys."""
    for k in keys:
        v = obj.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return default


def _derive_id(lead: dict) -> str:
    digest = hashlib.md5(
        json.dumps(lead, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    return f"synthetic_{digest}"


# ---------------------------------------------------------------------------
# ParsedLead
# ---------------------------------------------------------------------------

class ParsedLead:
    __slots__ = (
        "lead_id",
        "product_name",
        "category",
        "quantity",
        "buyer_city",
        "buyer_state",
        "buyer_country",
        "lead_value",
        "enrichment_value",     # Probable Order Value from ENRICHMENTINFO
        "credits_needed",
        "purchase_status",
        "buyer_name",
        "buyer_gst_verified",
        "buyer_mobile_verified",
        "timestamp",
        "raw",
    )

    def __init__(self, **kwargs):
        for slot in self.__slots__:
            setattr(self, slot, kwargs.get(slot, ""))
        self.raw = kwargs.get("raw", {})

    def to_dict(self) -> dict:
        return {s: getattr(self, s) for s in self.__slots__ if s != "raw"}

    @property
    def best_value(self) -> str:
        """Return the most informative order value string available."""
        return self.lead_value or self.enrichment_value or "N/A"


# ---------------------------------------------------------------------------
# Public parse function
# ---------------------------------------------------------------------------

def parse_leads(response: Any) -> List[ParsedLead]:
    """
    Parse a getBLDisplayData / getMoreLeadsData / getShortlistedData response
    into a list of ParsedLead objects.

    Never raises — returns empty list on unexpected input so the monitor loop
    stays alive.
    """
    if not isinstance(response, dict):
        logger.warning("Unexpected response type: %s", type(response))
        return []

    display_list = response.get("DisplayList")
    # DisplayList can be None, "null" string, or an empty list
    if display_list is None or display_list == "null" or display_list == "":
        logger.debug("DisplayList is null/missing — no leads.")
        return []
    if not isinstance(display_list, list):
        logger.warning("DisplayList is not a list (type=%s). Keys: %s", type(display_list), list(response.keys()))
        return []

    if not display_list:
        logger.debug("DisplayList is empty — no leads currently.")
        return []

    parsed: List[ParsedLead] = []

    for raw in display_list:
        if not isinstance(raw, dict):
            continue
        try:
            enrichment = _parse_enrichment(raw)

            lead_id = _pick(raw, "ETO_OFR_ID", "eto_ofr_id") or _derive_id(raw)

            # Quantity: ETO_OFR_QTY is often a blank space; fallback to enrichment
            qty = _pick(raw, "ETO_OFR_QTY", "eto_ofr_qty")
            if not qty or qty == " ":
                qty = enrichment.get("Quantity", "")

            # Order value: top-level field first, then enrichment
            lead_value = _pick(raw, "ETO_OFR_APPROX_ORDER_VALUE", "eto_ofr_approx_order_value")
            enrichment_value = enrichment.get("Probable Order Value", "")

            parsed.append(ParsedLead(
                lead_id=lead_id,
                product_name=_pick(raw, "ETO_OFR_TITLE", "eto_ofr_title"),
                category=_pick(raw, "ETO_OFR_GLCAT_MCAT_NAME", "eto_ofr_glcat_mcat_name",
                                    "PRIME_MCAT_NAME", "prime_mcat_name"),
                quantity=qty,
                buyer_city=_pick(raw, "GLUSR_CITY", "glusr_city"),
                buyer_state=_pick(raw, "GLUSR_STATE", "glusr_state"),
                buyer_country=_pick(raw, "GLUSR_COUNTRY", "glusr_country", default="India"),
                lead_value=lead_value,
                enrichment_value=enrichment_value,
                credits_needed=_pick(raw, "ETO_CREDITS", "eto_credits"),
                purchase_status=_pick(raw, "PURCHASE_STATUS", "purchase_status"),
                buyer_name=_pick(raw, "GLUSR_NAME", "glusr_name"),
                buyer_gst_verified=_pick(raw, "ETO_OFR_BUYER_IS_GST_VERF", "eto_ofr_buyer_is_gst_verf"),
                buyer_mobile_verified=_pick(raw, "ETO_OFR_BUYER_IS_MOB_VERF", "eto_ofr_buyer_is_mob_verf"),
                timestamp=_pick(raw, "ETO_OFR_DATE", "eto_ofr_date",
                                     "OFFER_DATE", "offer_date"),
                raw=raw,
            ))
        except Exception as exc:
            logger.error("Error parsing lead record: %s | raw=%s", exc, str(raw)[:200])

    logger.debug("Parsed %d leads from DisplayList", len(parsed))
    return parsed
