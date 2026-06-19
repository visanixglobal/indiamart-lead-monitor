"""
test_and_notify.py
------------------
One command: hits all 3 IndiaMART endpoints using the hardcoded cookie,
prints results, then sends a test ntfy notification with the outcome.

Usage:
    python test_and_notify.py
"""

import json
import sys
import time
from datetime import datetime

import requests
from dotenv import load_dotenv

load_dotenv(override=True)

from app.config import get_cookie, get_glusrid, get_ntfy_topic
from app.ntfy_service import send_ntfy_text

GLUSRID = get_glusrid()
COOKIE  = get_cookie()

ENDPOINTS = [
    {
        "name": "getBLDisplayData (recent)",
        "url": "https://seller.indiamart.com/blreact/getBLDisplayData",
        "payload": {
            "LocPref": "4", "stateid": "", "city": "", "iso": "",
            "pref_city_lead": 0, "glusrid": GLUSRID,
            "inbox": "", "offer": "", "offer_type": "B",
            "start": 1, "end": 5,
            "UsageTyp": "", "quantity": "", "is_email": "",
            "is_gst": "", "is_mobnum": "", "is_busname": "",
            "mcatid": "", "sov": "", "eov": None,
            "enqType": "", "is_catalog": "",
        },
        "referer": "https://seller.indiamart.com/bltxn/?pref=recent",
    },
    {
        "name": "getMoreLeadsData (suggested)",
        "url": "https://seller.indiamart.com/blreact/getMoreLeadsData",
        "payload": {
            "glusrid": GLUSRID, "start": 1, "end": 5, "priority": "P",
            "requestarray": {
                "pref": "other_leads", "lead_typ": "suggested",
                "loc_pref": 8, "stateid": "", "cityid": "",
                "iso": "", "locPrefCookie": "4", "mcatid": [],
            },
        },
        "referer": "https://seller.indiamart.com/bltxn/?pref=relevant",
    },
    {
        "name": "getMoreLeadsDataNew (related)",
        "url": "https://seller.indiamart.com/blreact/getMoreLeadsDataNew",
        "payload": {
            "glusrid": GLUSRID, "start": 1, "end": 5, "priority": "P",
            "requestarray": {
                "pref": "other_leads", "lead_typ": "related",
                "loc_pref": "8", "stateid": "", "cityid": "",
                "iso": "", "locPrefCookie": "4", "deboost_val": "",
            },
        },
        "referer": "https://seller.indiamart.com/bltxn/?pref=other_leads",
    },
]

HEADERS = {
    "Content-Type": "application/json",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://seller.indiamart.com",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
    "Cookie": COOKIE,
}

SEP = "=" * 55

def test_endpoints():
    results = []
    all_ok = True

    print(f"\n{SEP}")
    print(f"  IndiaMART Cookie Test  —  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  GLUSRID: {GLUSRID}")
    print(f"  Cookie length: {len(COOKIE)} chars")
    print(SEP)

    for ep in ENDPOINTS:
        try:
            t0 = time.time()
            resp = requests.post(
                ep["url"],
                json=ep["payload"],
                headers={**HEADERS, "Referer": ep["referer"]},
                timeout=20,
            )
            elapsed = int((time.time() - t0) * 1000)

            try:
                data = resp.json()
            except Exception:
                status = "FAIL — non-JSON response"
                detail = resp.text[:80]
                all_ok = False
                results.append((ep["name"], "❌", status, detail))
                print(f"\n[{ep['name']}]")
                print(f"  HTTP: {resp.status_code}  |  {elapsed}ms")
                print(f"  ❌ {status}: {detail}")
                continue

            http_ok = resp.status_code == 200
            code    = data.get("CODE", "?")
            status_field = data.get("STATUS", "")
            lead_count = len(data.get("DisplayList") or [])

            # Detect auth failure
            auth_fail_phrases = ["login", "session expired", "unauthorized", "auth failed", "please login"]
            msg_text = " ".join([
                str(data.get("MESSAGE", "")),
                str(data.get("Msg", "")),
                str(data.get("error", "")),
            ]).lower()
            auth_failed = any(p in msg_text for p in auth_fail_phrases)

            if not http_ok or auth_failed:
                icon = "❌"
                all_ok = False
                detail = data.get("MESSAGE") or data.get("Msg") or str(resp.status_code)
            else:
                icon = "✅"
                detail = f"{lead_count} leads  |  CODE={code}"

            results.append((ep["name"], icon, status_field, detail))
            print(f"\n[{ep['name']}]")
            print(f"  HTTP: {resp.status_code}  |  {elapsed}ms  |  CODE={code}")
            print(f"  {icon} Leads: {lead_count}  |  STATUS: {status_field}")
            if auth_failed:
                print(f"  ⚠️  Auth issue: {data.get('MESSAGE','')[:100]}")

        except requests.RequestException as exc:
            all_ok = False
            results.append((ep["name"], "❌", "Network error", str(exc)[:80]))
            print(f"\n[{ep['name']}]")
            print(f"  ❌ Network error: {exc}")

    print(f"\n{SEP}")
    overall = "✅ ALL OK" if all_ok else "❌ ISSUES FOUND"
    print(f"  Result: {overall}")
    print(SEP)
    return results, all_ok


def notify(results, all_ok):
    topic = get_ntfy_topic()
    if not topic:
        print("\n⚠️  NTFY_TOPIC not set — skipping notification")
        return

    lines = [f"Cookie test — {datetime.now().strftime('%H:%M:%S UTC')}"]
    for name, icon, status, detail in results:
        short_name = name.split("(")[0].strip()
        lines.append(f"{icon} {short_name}: {detail}")

    message = "\n".join(lines)
    title = "Cookie OK" if all_ok else "Cookie EXPIRED"
    priority = "default" if all_ok else "urgent"
    tags = "white_check_mark" if all_ok else "rotating_light"

    ok = send_ntfy_text(message, title=title)
    if ok:
        print(f"\n📱 Notification sent to ntfy.sh/{topic}")
    else:
        print(f"\n❌ Failed to send ntfy notification")


if __name__ == "__main__":
    results, all_ok = test_endpoints()
    notify(results, all_ok)
    sys.exit(0 if all_ok else 1)
