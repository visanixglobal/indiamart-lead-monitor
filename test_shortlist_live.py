"""
test_shortlist_live.py
----------------------
Tests the markShortlist endpoint with:
  1. A dummy/random lead ID  → expect some response (not network error)
  2. The real lead ID from earlier  → may succeed or say "already shortlisted"

This tells us whether the endpoint itself is still authenticated
or whether it returns 402 like getShortlistedData.

Run:  python test_shortlist_live.py
"""

import sys, json
sys.path.insert(0, "d:/indiamart-lead-monitor")
sys.path.insert(0, "d:/indiamart-lead-monitor/venv_packages")

from dotenv import load_dotenv
load_dotenv("d:/indiamart-lead-monitor/.env", override=True)

import requests
from app.config import get_cookie, get_glusrid

URL = "https://seller.indiamart.com/blreact/markShortlist"

def test_shortlist(label: str, ofrid: str, mcatid: str = "3001") -> None:
    print(f"\n{'='*55}")
    print(f"Test: {label}")
    print(f"ofrid={ofrid}  mcatid={mcatid}")
    print(f"{'='*55}")

    cookie  = get_cookie()
    glusrid = get_glusrid()

    payload = {
        "glusrid":  glusrid,
        "mcatid":   mcatid,
        "ofrid":    ofrid,
        "flag_val": "I",       # "I" = LikeIt / shortlist
        "status":   1,
        "source":   "MY_LATESTBL_LISTING",
    }

    headers = {
        "Content-Type": "application/json",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://seller.indiamart.com",
        "Referer": "https://seller.indiamart.com/bltxn/?pref=relevant&D_L_B=1",
        "Cookie": cookie,
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/142.0.0.0 Safari/537.36"
        ),
    }

    print(f"Payload: {json.dumps(payload, indent=2)}")

    try:
        resp = requests.post(URL, json=payload, headers=headers, timeout=15)
    except requests.RequestException as exc:
        print(f"[NETWORK ERROR] {exc}")
        return

    print(f"\nHTTP Status : {resp.status_code}")
    print(f"Raw response: {resp.text[:500]}")

    try:
        data = resp.json()
        print(f"\nParsed JSON : {json.dumps(data, indent=2)}")

        code = str(data.get("CODE", data.get("code", "?")))
        msg  = data.get("MSG", data.get("msg", data.get("MESSAGE", data.get("message", ""))))

        print(f"\nCODE : {code}")
        print(f"MSG  : {msg}")

        if resp.status_code == 200 and code not in ("401","402","403"):
            print("\n[RESULT] ✅ Endpoint is ALIVE and authenticated")
        elif code in ("401","402","403") or "auth" in str(data).lower():
            print("\n[RESULT] ❌ Authentication failed — cookie expired for this endpoint")
        else:
            print(f"\n[RESULT] ⚠️  Unexpected response — inspect JSON above")

    except ValueError:
        print(f"\n[RESULT] ❌ Non-JSON response — likely session expired or blocked")


if __name__ == "__main__":
    print("=== markShortlist Endpoint Test ===")
    print(f"GLUSRID: {get_glusrid()}")

    # Test 1: Completely random/fake lead ID
    # If this returns 402 → cookie is dead for this endpoint
    # If it returns 200 with some error msg → endpoint is alive
    test_shortlist(
        label="Random fake lead ID",
        ofrid="999999999999",
        mcatid="3001",
    )

    # Test 2: The real lead ID from earlier today
    test_shortlist(
        label="Real lead from earlier (146158350895)",
        ofrid="146158350895",
        mcatid="3001",
    )
