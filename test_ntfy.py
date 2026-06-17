"""
test_ntfy.py
------------
Sends a test notification to your phone via ntfy.sh.

Usage:
    python test_ntfy.py

Before running:
    1. iPhone → App Store → install "ntfy" (free)
    2. Open ntfy app → tap + → type a topic name → Subscribe
       Example topic: visanix-leads-x7k2m9
    3. Add to .env:
       NTFY_TOPIC=visanix-leads-x7k2m9
    4. Run this script — notification should arrive within 2 seconds
"""

import sys
sys.path.insert(0, "d:/indiamart-lead-monitor")
sys.path.insert(0, "d:/indiamart-lead-monitor/venv_packages")

from dotenv import load_dotenv
load_dotenv("d:/indiamart-lead-monitor/.env", override=True)

import os
import requests
from app.ntfy_service import test_ntfy, send_ntfy_alert
from app.parser import ParsedLead

topic = os.getenv("NTFY_TOPIC", "").strip()

print("\n=== ntfy.sh Notification Test ===\n")

if not topic:
    print("ERROR: NTFY_TOPIC not set in .env")
    print()
    print("Steps:")
    print("  1. iPhone App Store → install 'ntfy' (free)")
    print("  2. Open ntfy → tap + → enter topic name → Subscribe")
    print("     Suggested: visanix-leads-x7k2m9  (make it unique)")
    print("  3. Add to .env:")
    print("       NTFY_TOPIC=visanix-leads-x7k2m9")
    print("  4. Run this script again")
    sys.exit(1)

print(f"Topic: {topic}")
print(f"URL  : https://ntfy.sh/{topic}")
print()

# --- Test 1: Plain text notification ---
print("Test 1: Plain system notification...")
ok1 = test_ntfy()

print()

# --- Test 2: Simulated lead notification (exactly what you'll see in production) ---
print("Test 2: Simulated lead notification (real format)...")

fake_lead = ParsedLead(
    lead_id="TEST-NOTIFICATION-ONLY",
    product_name="[TEST] This is a test notification",
    category="Test",
    quantity="N/A",
    buyer_city="Test City",
    buyer_state="Test State",
    buyer_country="India",
    lead_value="N/A",
    enrichment_value="",
    credits_needed="0",
    purchase_status="TEST",
    buyer_gst_verified="0",
    buyer_mobile_verified="0",
)

ok2 = send_ntfy_alert(fake_lead)

print()
print("=" * 40)
if ok1 and ok2:
    print("SUCCESS: Both notifications sent.")
    print("Check your iPhone — you should see 2 alerts.")
    print()
    print("Your notification setup is ready.")
    print("When a real lead arrives, you will get an")
    print("instant push notification on your iPhone.")
elif ok1 or ok2:
    print("PARTIAL: One notification sent, one failed.")
    print("Check the error above.")
else:
    print("FAILED: No notifications sent.")
    print("Check your NTFY_TOPIC and internet connection.")
print()
