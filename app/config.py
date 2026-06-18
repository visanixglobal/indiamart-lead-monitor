"""
Configuration management.
Reads from .env on every access to support hot-reload of settings.

GLUSRID and INDIAMART_COOKIE are hardcoded below.
When the cookie expires, update _INDIAMART_COOKIE and redeploy.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

ENV_PATH = Path(__file__).parent.parent / ".env"
ENV_EXAMPLE_PATH = Path(__file__).parent.parent / ".env.example"

# ---------------------------------------------------------------------------
# Hardcoded IndiaMART credentials
# When cookie expires: grab fresh Cookie header from DevTools → update below → redeploy
# ---------------------------------------------------------------------------

_GLUSRID = "80627141"

_INDIAMART_COOKIE = (
    "_gcl_au=1.1.848941330.1774080715; _ga=GA1.1.1654210164.1774080715; "
    "__gsas=ID=82ce969238881333:T=1774080827:RT=1774080827:S=ALNI_Mb7-c_XoINKIOwc1SjjaOaI3VbVmA; "
    "_ym_uid=1774082385914857337; _ym_d=1774082385; pop_mthd=FL%3D0%7CDTy%3D1; "
    "_fbp=fb.1.1778040425773.246054158253577298; _ga_8B5NXMMZN3=deleted; _ga_8B5NXMMZN3=deleted; "
    "_ga_HDFDX3PJ8P=GS2.1.s1779473137$o1$g1$t1779473170$j27$l0$h0; "
    "_ga_3C9P6J36NW=GS2.1.s1779473137$o1$g1$t1779473170$j27$l0$h0; "
    "_ga_MR9M3CSWMG=GS2.1.s1779473137$o1$g1$t1779473170$j27$l0$h0; "
    "G_ENABLED_IDPS=google; LGNSTR=0%2C1%2C0%2C1%2C1%2C1%2C1%2C0%2C1; "
    "sugg_countries_ssr=; sugg_states_ssr=; user_choice_loc=; con_iso=india%3A%3A%3A8; "
    "_clck=1dxpk9y%5E2%5Eg70%5E0%5E2315; "
    "ImeshVisitor=SubUser%3D%7Cadmln%3D0%7Cadmsales%3D0%7Ccd%3D18%2FJUN%2F2026%7Ccmid%3D53%7Cctid%3D70469%7Cem%3Ds%2A%2A%2A%2A%40visanixglobal.com%7Ceotp%3D%7Cev%3DV%7Cfn%3DSahil%7Cglid%3D80627141%7Ciso%3DIN%7Cmb1%3D9667445766%7Cphcc%3D91%7Custs%3D%7Cutyp%3DF%7Cuv%3DV; "
    "_ym_isad=2; "
    "iploc=gcniso%3DIN%7Cgcnnm%3DIndia%7Cgctnm%3DNew%20Delhi%7Cgctid%3D70469%7Cgacrcy%3D20%7Cgip%3D106.192.194.112%7Cgstnm%3DNational%20Capital%20Territory%20of%20Delhi; "
    "userDet=glid=80627141|loc_pref=4|fcp_flag=1|image=|service_ids=|logo=https://5.imimg.com/data5/SELLER/Logo/2026/5/606069567/QI/WZ/RI/80627141/logo-with-name-90x90.png|psc_status=0|d_re=|u_url=https://www.indiamart.com/visanixglobal/|ast=A|lst=LST|ctid=70469|ct=New Delhi|stid=6478|st=Delhi|enterprise=0|mod_st=F|rating=0|nach=0|iec=|is_suspect=0|vertical=CSD|pns_no=8047787819|gst=07AAHPN5479R1ZP|pan=AAHPN5479R|cin=|collectPayments=0|is_display_invoice_banner=0|is_display_enquiry=0|is_display_credit=0|disposition=I am exempted|disp_date=20260508083504|recreateUserDetCookie=|vid=|did=|fid=|src_ID=3|locPref_enable=0|comp_name=Visanix Global|hosting_date=|pay_later_navigation=0|pre_approved_loan_navigation=0|showInvoice=1; "
    "__gads=ID=b3a32c746cf22e68:T=1774080886:RT=1781800188:S=ALNI_MZZW_PrS2k3iuJjmIKxy6gYgkXrVQ; "
    "__gpi=UID=000012277b56e4a0:T=1774080886:RT=1781800188:S=ALNI_Mb0jCLcpvPXFcyrWnGahRd-r7xMAg; "
    "__eoi=ID=0e72cb79e357de4f:T=1774080886:RT=1781800188:S=AA-AfjY4smYh8Ml2S8B9W0uWV2df; "
    "site-entry-page=https://www.indiamart.com/explovaxpharmaceutical/; "
    "GeoLoc=lt%3D%7Clg%3D%7Caccu%3D%7Clg_ct%3D%7Clg_ctid%3D; "
    "im_iss=t%3DeyJhbGciOiJzaGEyNTYiLCJ0eXAiOiJKV1QifQ.eyJhdWQiOiI5KjYqNCo1KjYqIiwiY2R0IjoiMTgtMDYtMjAyNiIsImV4cCI6MTc4MTg5MzcxNCwiaWF0IjoxNzgxODA3MzE0LCJpc3MiOiJVU0VSIiwic3ViIjoiODA2MjcxNDEifQ.d8QiNlke6P2KoaEwSk--T6Zl3EKkomP7W8CHDYgfoPw; "
    "_ym_visorc=b; "
    "FCNEC=%5B%5B%22AKsRol8kqe-KiF4_xPUgL6jklTHpVkDDERStbSvuS7zZvkjwV894Ctos0PdmZYGxqitfuM9Yt662ea-nTwRNHKAXzTwK3obvVZ9tBr9Wd31pnvVforgyw4fdkICGU6z0Rz4QzsIJl2x9qK1Svt8sv9Lvr_AfsSxtzQ%3D%3D%22%5D%5D; "
    "sessid=spv=5; "
    "FCCDCF=%5Bnull%2Cnull%2Cnull%2Cnull%2Cnull%2Cnull%2C%5B%5B32%2C%22%5B%5C%22381f3f0d-b20a-4895-836b-81648dc0505f%5C%22%2C%5B1774080715%2C178000000%5D%5D%22%5D%5D%5D; "
    "_clsk=13bc64o%5E1781809253283%5E9%5E0%5Ee.clarity.ms%2Fcollect; "
    "xnHist=pv%3D0%7Cipv%3D55%7Cfpv%3D5%7Ccity%3Dundefined%7Clc_city%3Dundefined%7Ccvstate%3Dundefined%7Cpopupshown%3Dundefined%7Cinstall%3Dundefined%7Css%3DnotSelected%7Cmb%3Dundefined%7Ctm%3Dundefined%7Cage%3Dundefined%7Ccount%3D0%7Ctime%3DThu%20Jun%2018%202026%2023%3A58%3A38%20GMT%2B0530%20%28India%20Standard%20Time%29%7Cglid%3D80627141%7Cgname%3Dundefined%7Cgemail%3Dundefined%7CcityID%3Dundefined; "
    "bl_tab_visibility=visible; "
    "_ga_8B5NXMMZN3=GS2.1.s1781807313$o56$g1$t1781809253$j56$l0$h0"
)

ENV_EXAMPLE_CONTENT = """# IndiaMART credentials are hardcoded in app/config.py
# Update _INDIAMART_COOKIE in config.py when session expires, then redeploy.

# Monitoring
POLL_INTERVAL=60

# Quiet Hours (UTC)
QUIET_HOURS_START=19
QUIET_HOURS_END=2

# Auto-Shortlist
AUTO_SHORTLIST=false
SHORTLIST_MIN_VALUE=0

# Telegram Alerts
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# ntfy.sh Push Notifications
NTFY_TOPIC=
"""


def ensure_env_example() -> None:
    """Create .env.example if it does not exist."""
    if not ENV_EXAMPLE_PATH.exists():
        ENV_EXAMPLE_PATH.write_text(ENV_EXAMPLE_CONTENT)


def _load() -> None:
    """Force-reload .env from disk."""
    load_dotenv(dotenv_path=ENV_PATH, override=True)


def get_glusrid() -> str:
    return _GLUSRID


def get_cookie() -> str:
    # Remove any non-latin-1 characters that would break HTTP headers
    return _INDIAMART_COOKIE.encode("latin-1", errors="ignore").decode("latin-1")


def get_poll_interval() -> int:
    _load()
    try:
        return int(os.getenv("POLL_INTERVAL", "60"))
    except ValueError:
        return 60


def get_ntfy_topic() -> str:
    _load()
    return os.getenv("NTFY_TOPIC", "").strip()


def get_quiet_hours_start() -> int:
    """Hour (0-23) when notifications go silent. Default 19 (UTC = 1 AM IST)."""
    _load()
    try:
        return int(os.getenv("QUIET_HOURS_START", "19"))
    except ValueError:
        return 19


def get_quiet_hours_end() -> int:
    """Hour (0-23) when notifications resume. Default 2 (UTC = 7:30 AM IST)."""
    _load()
    try:
        return int(os.getenv("QUIET_HOURS_END", "2"))
    except ValueError:
        return 2


def get_telegram_bot_token() -> str:
    _load()
    return os.getenv("TELEGRAM_BOT_TOKEN", "").strip()


def get_telegram_chat_id() -> str:
    _load()
    return os.getenv("TELEGRAM_CHAT_ID", "").strip()


def is_configured() -> bool:
    """Return True when minimum required credentials are present (always True now — hardcoded)."""
    return bool(_GLUSRID and _INDIAMART_COOKIE)


SETUP_BANNER = """
=========================================
   INDIAMART COOKIE REFRESH NEEDED
=========================================

Cookie has expired. To refresh:

1. Open seller.indiamart.com in Chrome
2. Press F12 → Network tab
3. Find any getBLDisplayData request
4. Right-click → Copy → Copy as cURL
5. Open app/config.py
6. Replace _INDIAMART_COOKIE value with
   the new Cookie header value
7. Redeploy / restart

=========================================
"""
