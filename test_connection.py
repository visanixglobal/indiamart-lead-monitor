"""
test_connection.py
------------------
Tests all three IndiaMART API endpoints discovered from the seller portal.

Usage:
    python test_connection.py

Endpoints tested:
  1. getBLDisplayData    – Recent buy leads
  2. getMoreLeadsData    – Suggested / relevant leads
  3. getShortlistedData  – Shortlisted / wishlisted leads

Output:
  - HTTP status per endpoint
  - Response preview (first 1000 chars)
  - Full responses saved to logs/sample_response_*.json
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv(override=True)

from app.config import get_cookie, get_glusrid, is_configured, SETUP_BANNER, ensure_env_example
from app.logger import get_logger

ensure_env_example()
logger = get_logger("test_connection")

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

BASE_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://seller.indiamart.com",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/142.0.0.0 Safari/537.36"
    ),
}


def headers(referer: str) -> dict:
    h = dict(BASE_HEADERS)
    h["Cookie"] = get_cookie()
    h["Referer"] = referer
    return h


def test_endpoint(name: str, url: str, payload: dict, referer: str) -> bool:
    import requests

    print(f"\n{'='*60}")
    print(f"Testing: {name}")
    print(f"URL    : {url}")
    print(f"{'='*60}")

    try:
        resp = requests.post(url, json=payload, headers=headers(referer), timeout=30)
    except requests.RequestException as exc:
        print(f"[ERROR] Network error: {exc}")
        return False

    print(f"Status : {resp.status_code}")

    try:
        data = resp.json()
    except ValueError:
        print(f"[ERROR] Non-JSON response:\n{resp.text[:500]}")
        return False

    # Save full response
    out_file = LOG_DIR / f"sample_response_{name}.json"
    out_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved  : {out_file}")

    # Preview
    preview = json.dumps(data, ensure_ascii=False)[:1000]
    print(f"\n--- Preview ---\n{preview}\n")

    if resp.status_code == 200:
        print(f"[OK] {name} — connection successful")
        return True
    else:
        print(f"[WARN] {name} — unexpected status {resp.status_code}")
        return False


def main() -> None:
    print("\n=== IndiaMART Connection Test ===\n")

    if not is_configured():
        print(SETUP_BANNER)
        sys.exit(1)

    glusrid = get_glusrid()
    print(f"GLUSRID: {glusrid}\n")

    results = []

    # --- Endpoint 1: Recent buy leads ---
    results.append(test_endpoint(
        name="getBLDisplayData",
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
            "is_busnum": "",
            "mcatid": "",
            "sov": "",
            "eov": None,
            "enqType": "",
            "is_catalog": "",
        },
        referer="https://seller.indiamart.com/bltxn/?pref=recent",
    ))

    # --- Endpoint 2: Suggested / relevant leads ---
    results.append(test_endpoint(
        name="getMoreLeadsData",
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
    ))

    # --- Endpoint 3: Shortlisted / wishlisted leads ---
    results.append(test_endpoint(
        name="getShortlistedData",
        url="https://seller.indiamart.com/blreact/getShortlistedData",
        payload={
            "glusrid": glusrid,
            "start": 1,
            "end": 25,
        },
        referer="https://seller.indiamart.com/bltxn/myWishList/",
    ))

    # --- Summary ---
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    names = ["getBLDisplayData", "getMoreLeadsData", "getShortlistedData"]
    for name, ok in zip(names, results):
        status = "✅ OK" if ok else "❌ FAILED"
        print(f"  {status}  {name}")

    if all(results):
        print("\n[ALL ENDPOINTS WORKING] Ready to start monitoring.\n")
    else:
        print("\n[SOME ENDPOINTS FAILED] Check logs above.\n")
        print("If you see 'login' in the response, your cookie has expired.")
        print("Run:  python refresh_cookie.py\n")


if __name__ == "__main__":
    main()
