"""
endurance_test.py
-----------------
Runs all 3 IndiaMART API endpoints every 5 minutes for 24 hours.
Logs every result to console AND logs/endurance_test.log

Status codes:
  [OK]  = HTTP 200 + valid JSON + leads present
  [--]  = HTTP 200 + valid JSON + no leads (completely normal)
  [KEY] = session expired / auth failed
  [ERR] = HTTP error or bad JSON
  [NET] = network/timeout error

Usage:
    python endurance_test.py

Stop anytime with Ctrl+C — partial results are saved.
"""

import sys
import json
import time
import base64
import re
import logging
from datetime import datetime, timedelta
from pathlib import Path
from logging.handlers import RotatingFileHandler

sys.path.insert(0, "d:/indiamart-lead-monitor")
sys.path.insert(0, "d:/indiamart-lead-monitor/venv_packages")

from dotenv import load_dotenv
load_dotenv("d:/indiamart-lead-monitor/.env", override=True)

import requests
from app.config import get_cookie, get_glusrid

# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------

LOG_PATH = Path("logs/endurance_test.log")
LOG_PATH.parent.mkdir(exist_ok=True)

log = logging.getLogger("endurance")
log.setLevel(logging.DEBUG)
fmt = logging.Formatter("%(asctime)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

fh = RotatingFileHandler(LOG_PATH, maxBytes=5*1024*1024, backupCount=3, encoding="utf-8")
fh.setFormatter(fmt)
log.addHandler(fh)

# stdout — handle Windows encoding gracefully
import io
try:
    stdout_writer = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
except AttributeError:
    stdout_writer = sys.stdout
ch = logging.StreamHandler(stdout_writer)
ch.setFormatter(fmt)
log.addHandler(ch)

# ---------------------------------------------------------------------------
# JWT expiry checker
# ---------------------------------------------------------------------------

def decode_jwt_expiry(cookie_str: str) -> str:
    """Extract and decode the im_iss JWT from the cookie string, return expiry info."""
    try:
        # im_iss is URL-encoded as t%3D<jwt> or t=<jwt>
        match = re.search(
            r'im_iss=t(?:%3D|=)([A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+)',
            cookie_str
        )
        if not match:
            return "im_iss JWT not found in cookie"

        jwt_token = match.group(1)
        payload_b64 = jwt_token.split(".")[1]
        payload_b64 += "=" * (4 - len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))

        exp_ts = payload.get("exp", 0)
        exp_dt = datetime.fromtimestamp(exp_ts)
        now = datetime.now()

        if exp_dt < now:
            diff = now - exp_dt
            h, m = diff.seconds // 3600, (diff.seconds % 3600) // 60
            return f"*** EXPIRED {h}h {m}m ago ({exp_dt.strftime('%Y-%m-%d %H:%M')}) — run refresh_cookie.py ***"
        else:
            diff = exp_dt - now
            h, m = diff.seconds // 3600, (diff.seconds % 3600) // 60
            return f"valid for {h}h {m}m  (expires {exp_dt.strftime('%Y-%m-%d %H:%M')})"
    except Exception as exc:
        return f"Could not decode: {exc}"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

ENDPOINTS = [
    {
        "name": "getBLDisplayData",
        "url": "https://seller.indiamart.com/blreact/getBLDisplayData",
        "referer": "https://seller.indiamart.com/bltxn/?pref=recent",
        "critical": True,   # used for lead detection
        "payload_fn": lambda glusrid: {
            "LocPref": "4", "stateid": "", "city": "", "iso": "",
            "pref_city_lead": 0, "glusrid": glusrid,
            "inbox": "", "offer": "", "offer_type": "B",
            "start": 1, "end": 20, "UsageTyp": "", "quantity": "",
            "is_email": "", "is_gst": "", "is_mobnum": "", "is_busname": "",
            "mcatid": "", "sov": 500, "eov": None, "enqType": 2, "is_catalog": "",
        },
    },
    {
        "name": "getMoreLeadsData",
        "url": "https://seller.indiamart.com/blreact/getMoreLeadsData",
        "referer": "https://seller.indiamart.com/bltxn/?pref=relevant",
        "critical": True,   # used for lead detection
        "payload_fn": lambda glusrid: {
            "glusrid": glusrid, "start": 1, "end": 25, "priority": "P",
            "requestarray": {
                "pref": "other_leads", "lead_typ": "suggested",
                "loc_pref": 8, "stateid": "", "cityid": "", "iso": "",
                "locPrefCookie": "4", "mcatid": [],
            },
        },
    },
    {
        "name": "getShortlistedData",
        "url": "https://seller.indiamart.com/blreact/getShortlistedData",
        "referer": "https://seller.indiamart.com/bltxn/myWishList/",
        "critical": False,  # needs fresh JWT — monitored but not used for detection
        "payload_fn": lambda glusrid: {
            "glusrid": glusrid, "start": 1, "end": 25,
        },
    },
    {
        "name": "markShortlist",
        "url": "https://seller.indiamart.com/blreact/markShortlist",
        "referer": "https://seller.indiamart.com/bltxn/?pref=relevant&D_L_B=1",
        "critical": False,  # needs fresh JWT — monitored to know when it comes back
        "payload_fn": lambda glusrid: {
            "glusrid": glusrid, "mcatid": "3001",
            "ofrid": "999999999999",  # dummy ID — just testing auth
            "flag_val": "I", "status": 1, "source": "MY_LATESTBL_LISTING",
        },
    },
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

POLL_INTERVAL_SECONDS = 300   # 5 minutes
TEST_DURATION_HOURS   = 24

# ---------------------------------------------------------------------------
# Stats tracker
# ---------------------------------------------------------------------------

class EndpointStats:
    def __init__(self, name: str):
        self.name = name
        self.total = 0
        self.ok = 0
        self.empty = 0
        self.errors = 0
        self.session_expired = 0

    def record(self, status: str):
        self.total += 1
        if status == "ok":
            self.ok += 1
        elif status == "empty":
            self.empty += 1
        elif status == "session_expired":
            self.session_expired += 1
            self.errors += 1
        else:
            self.errors += 1

    def uptime_pct(self) -> float:
        if self.total == 0:
            return 0.0
        return round((self.ok + self.empty) / self.total * 100, 1)

    def summary_line(self) -> str:
        return (
            f"{self.name:<25} | "
            f"calls={self.total:>4} | "
            f"ok={self.ok:>4} | "
            f"empty={self.empty:>4} | "
            f"errors={self.errors:>3} | "
            f"session_exp={self.session_expired:>2} | "
            f"uptime={self.uptime_pct():>5}%"
        )


# ---------------------------------------------------------------------------
# Single call
# ---------------------------------------------------------------------------

def call_endpoint(ep: dict, glusrid: str, cookie: str) -> tuple:
    """Returns (status, lead_count, detail)."""
    headers = {
        "Content-Type": "application/json",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://seller.indiamart.com",
        "Referer": ep["referer"],
        "Cookie": cookie,
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/142.0.0.0 Safari/537.36"
        ),
    }

    try:
        resp = requests.post(ep["url"], json=ep["payload_fn"](glusrid),
                             headers=headers, timeout=30)
    except requests.RequestException as exc:
        return "network_error", 0, str(exc)[:100]

    if resp.status_code in (401, 402, 403):
        return "session_expired", 0, f"HTTP {resp.status_code}"

    if resp.status_code != 200:
        return "http_error", 0, f"HTTP {resp.status_code}: {resp.text[:80]}"

    try:
        data = resp.json()
    except ValueError:
        return "json_error", 0, resp.text[:80]

    # Check auth failure inside JSON body
    code_val = str(data.get("CODE", ""))
    body_lower = json.dumps(data).lower()
    if code_val in ("401", "402", "403") or any(
        p in body_lower for p in ["please login", "session expired",
                                   "unauthorized", "auth failed",
                                   "authentication failed"]
    ):
        return "session_expired", 0, f"Auth error in body: CODE={code_val}"

    display_list = data.get("DisplayList")
    if not display_list or display_list == "null":
        lead_count = 0
    elif isinstance(display_list, list):
        lead_count = len(display_list)
    else:
        lead_count = 0

    status = "ok" if lead_count > 0 else "empty"
    msg = data.get("BLmsg", data.get("MESSAGE", ""))[:50]
    return status, lead_count, f"CODE={code_val} leads={lead_count} [{msg}]"


# ---------------------------------------------------------------------------
# Poll round
# ---------------------------------------------------------------------------

def poll_round(stats_map: dict, round_num: int) -> None:
    # Re-read cookie on every round (supports refresh_cookie.py hot-reload)
    glusrid = get_glusrid()
    cookie  = get_cookie()

    ts = datetime.now().strftime("%H:%M:%S")
    log.info("Round %4d [%s]", round_num, ts)

    for ep in ENDPOINTS:
        status, lead_count, detail = call_endpoint(ep, glusrid, cookie)
        stats_map[ep["name"]].record(status)

        tag = {"ok": "[OK] ", "empty": "[--] ", "session_expired": "[KEY]",
               "http_error": "[ERR]", "json_error": "[ERR]",
               "network_error": "[NET]"}.get(status, "[???]")

        crit = " (CRITICAL)" if ep.get("critical") and status not in ("ok","empty") else ""
        log.info("  %s  %-25s  %s%s", tag, ep["name"], detail, crit)

    log.info("")


def print_summary(stats_map: dict, elapsed: timedelta, total_rounds: int) -> None:
    log.info("=" * 70)
    log.info("ENDURANCE TEST SUMMARY — elapsed %s  rounds=%d",
             str(elapsed).split(".")[0], total_rounds)
    log.info("-" * 70)
    log.info("  %-26s %-6s %-6s %-6s %-5s %-5s %-7s %s",
             "ENDPOINT", "CALLS", "OK", "EMPTY", "ERR", "KEY", "UPTIME", "TYPE")
    log.info("  " + "-" * 66)
    for ep in ENDPOINTS:
        s = stats_map[ep["name"]]
        ep_type = "CRITICAL" if ep.get("critical") else "optional"
        log.info("  %-26s %-6d %-6d %-6d %-5d %-5d %-7s %s",
                 s.name, s.total, s.ok, s.empty,
                 s.errors, s.session_expired,
                 f"{s.uptime_pct()}%", ep_type)
    log.info("")

    # Critical health verdict
    critical_names = [ep["name"] for ep in ENDPOINTS if ep.get("critical")]
    all_critical_ok = all(
        stats_map[n].uptime_pct() == 100.0 for n in critical_names
    )
    if all_critical_ok:
        log.info("  VERDICT: CRITICAL endpoints 100%% healthy — lead detection reliable")
    else:
        log.info("  VERDICT: WARNING — critical endpoint failures detected")
        for n in critical_names:
            s = stats_map[n]
            if s.uptime_pct() < 100.0:
                log.info("           %s uptime=%.1f%%  errors=%d", n, s.uptime_pct(), s.errors)

    log.info("")
    log.info("  [OK]  = leads present  [--] = no leads (normal)")
    log.info("  [KEY] = token expired -> run refresh_cookie.py")
    log.info("  [ERR] = HTTP/JSON error  [NET] = network error")
    log.info("=" * 70)
    log.info("")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    glusrid = get_glusrid()
    cookie  = get_cookie()

    if not glusrid:
        print("ERROR: GLUSRID not set in .env")
        sys.exit(1)
    if len(cookie) < 100:
        print("ERROR: INDIAMART_COOKIE missing or too short in .env")
        sys.exit(1)

    end_time   = datetime.now() + timedelta(hours=TEST_DURATION_HOURS)
    start_time = datetime.now()
    stats_map  = {ep["name"]: EndpointStats(ep["name"]) for ep in ENDPOINTS}
    round_num  = 0

    jwt_status = decode_jwt_expiry(cookie)

    log.info("=" * 70)
    log.info("IndiaMART Endurance Test — %dh duration, every %ds",
             TEST_DURATION_HOURS, POLL_INTERVAL_SECONDS)
    log.info("Started  : %s", start_time.strftime("%Y-%m-%d %H:%M:%S"))
    log.info("Will end : %s", end_time.strftime("%Y-%m-%d %H:%M:%S"))
    log.info("GLUSRID  : %s", glusrid)
    log.info("Session  : %s", jwt_status)
    log.info("Log file : %s", LOG_PATH)
    log.info("=" * 70)
    log.info("")
    log.info("[OK]=leads present  [--]=no leads(normal)  [KEY]=session expired  [ERR/NET]=errors")
    log.info("")

    # Warn immediately if session is already expired
    if "EXPIRED" in jwt_status:
        log.info("WARNING: Session JWT is already expired!")
        log.info("         getShortlistedData will fail until you refresh cookies.")
        log.info("         Run:  python refresh_cookie.py")
        log.info("")

    try:
        while datetime.now() < end_time:
            round_num += 1
            poll_round(stats_map, round_num)

            # Hourly summary (every 12 rounds = 60 min)
            if round_num % 12 == 0:
                elapsed = datetime.now() - start_time
                print_summary(stats_map, elapsed, round_num)

            next_poll = datetime.now() + timedelta(seconds=POLL_INTERVAL_SECONDS)
            if next_poll > end_time:
                break

            remaining = (next_poll - datetime.now()).total_seconds()
            if remaining > 0:
                log.info("  Next poll in %ds  (Ctrl+C to stop)\n", int(remaining))
                time.sleep(remaining)

    except KeyboardInterrupt:
        log.info("Stopped by user.")

    elapsed = datetime.now() - start_time
    print_summary(stats_map, elapsed, round_num)
    log.info("Full log: %s", LOG_PATH)


if __name__ == "__main__":
    main()
