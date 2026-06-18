"""
list_apis.py – Print all IndiaMART API endpoints used by this monitor.
Run:  python list_apis.py
"""

import json

APIS = [
    {
        "name": "getBLDisplayData",
        "description": "Recent buy leads (last 20)",
        "method": "POST",
        "url": "https://seller.indiamart.com/blreact/getBLDisplayData",
        "referer": "https://seller.indiamart.com/bltxn/?pref=recent",
        "sample_payload": {
            "LocPref": "4",
            "stateid": "",
            "city": "",
            "iso": "",
            "pref_city_lead": 0,
            "glusrid": "<GLUSRID>",
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
    },
    {
        "name": "getMoreLeadsData",
        "description": "Suggested / relevant leads (up to 25)",
        "method": "POST",
        "url": "https://seller.indiamart.com/blreact/getMoreLeadsData",
        "referer": "https://seller.indiamart.com/bltxn/?pref=relevant",
        "sample_payload": {
            "glusrid": "<GLUSRID>",
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
    },
    {
        "name": "getShortlistedData",
        "description": "Shortlisted / wishlisted leads (up to 25)",
        "method": "POST",
        "url": "https://seller.indiamart.com/blreact/getShortlistedData",
        "referer": "https://seller.indiamart.com/bltxn/myWishList/",
        "sample_payload": {
            "glusrid": "<GLUSRID>",
            "start": 1,
            "end": 25,
        },
    },
]

SEP = "=" * 60

def main():
    print(f"\n{SEP}")
    print("  IndiaMART Lead Monitor – API Endpoints")
    print(SEP)
    print(f"  Total endpoints: {len(APIS)}")
    print(f"  Base origin:     https://seller.indiamart.com")
    print(f"  Auth:            Cookie header (hardcoded in app/config.py)")
    print(SEP)

    for i, api in enumerate(APIS, 1):
        print(f"\n[{i}] {api['name']}")
        print(f"    Description : {api['description']}")
        print(f"    Method      : {api['method']}")
        print(f"    URL         : {api['url']}")
        print(f"    Referer     : {api['referer']}")
        print(f"    Payload     :")
        payload_str = json.dumps(api["sample_payload"], indent=6)
        for line in payload_str.splitlines():
            print(f"      {line}")

    print(f"\n{SEP}")
    print("  Common request headers sent with every call:")
    print("    Content-Type       : application/json")
    print("    Accept             : */*")
    print("    Origin             : https://seller.indiamart.com")
    print("    Cookie             : <_INDIAMART_COOKIE from app/config.py>")
    print("    User-Agent         : Chrome/142 (Windows)")
    print("    sec-fetch-mode     : cors")
    print("    sec-fetch-site     : same-origin")
    print(SEP)

    print("\n  Polling schedule (from .env):")
    try:
        from app.config import get_poll_interval, get_quiet_hours_start, get_quiet_hours_end
        interval = get_poll_interval()
        qs = get_quiet_hours_start()
        qe = get_quiet_hours_end()
        print(f"    Poll interval    : every {interval}s")
        print(f"    Quiet hours      : {qs:02d}:00 – {qe:02d}:00 (no polling)")
        print(f"    Endpoints polled : getBLDisplayData + getMoreLeadsData each cycle")
        print(f"    Note             : getShortlistedData is available but not in active poll loop")
    except Exception as e:
        print(f"    (Could not load config: {e})")

    print(SEP + "\n")


if __name__ == "__main__":
    main()
