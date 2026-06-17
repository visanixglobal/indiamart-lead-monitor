# IndiaMART Lead Monitor

A production-ready Python application that continuously monitors IndiaMART Buy Leads,
stores lead history in SQLite, and sends instant push notifications when new leads arrive.

---

## Features

- **Real-time monitoring** — polls IndiaMART every 60 seconds
- **Duplicate detection** — SQLite deduplication by lead ID
- **Push notifications** — via ntfy.sh (free, no signup, works in India)
- **Telegram alerts** — when Telegram is available
- **Interactive buttons** — Shortlist / Skip leads directly from notification (Telegram)
- **REST dashboard** — FastAPI endpoints for health, latest leads, and stats
- **Graceful session handling** — detects expired cookies and retries
- **Hot cookie reload** — update cookies without restarting
- **Docker support** — single `docker compose up -d`

---

## Quick Start

### Step 1 — Set up push notifications (ntfy.sh)

**On your iPhone:**
1. App Store → search **"ntfy"** → install (free)
2. Open app → tap **+**
3. Enter a unique topic name, e.g. `visanix-leads-x7k2m9`
4. Tap **Subscribe**

**In `.env`:**
```
NTFY_TOPIC=visanix-leads-x7k2m9
```

**Test it:**
```bash
python test_ntfy.py
```
You should see a notification on your phone within 2 seconds.

---

### Step 2 — Set up IndiaMART credentials

1. Open **seller.indiamart.com** in Chrome
2. Press **F12** → Network tab
3. Navigate to Buy Leads
4. Find request **`getBLDisplayData`** → click it
5. In **Headers** tab: copy entire **Cookie** value
6. In **Payload** tab: copy `glusrid` value

Add to `.env`:
```
GLUSRID=80627141
INDIAMART_COOKIE=<paste full cookie here>
```

**Test the connection:**
```bash
python test_connection.py
```

---

### Step 3 — Run locally

```bash
python main.py
```

Or with Docker:
```bash
docker compose up -d
docker compose logs -f
```

---

## Deploying to a Free Server (Oracle Cloud)

Run 24/7 without keeping your laptop on.

### Create Oracle Free Account
1. Go to [cloud.oracle.com](https://cloud.oracle.com)
2. Sign up → choose **Always Free** resources only
3. Create a VM: **VM.Standard.E2.1.Micro** (Always Free)
4. OS: **Ubuntu 22.04**
5. Download the SSH key when prompted

### Connect to your VM
```bash
ssh -i your-key.pem ubuntu@<your-vm-ip>
```

### Install Docker on the VM
```bash
sudo apt update
sudo apt install -y docker.io docker-compose-plugin
sudo usermod -aG docker ubuntu
# Log out and back in
```

### Deploy the project
```bash
# On your laptop — copy project to server
scp -i your-key.pem -r d:\indiamart-lead-monitor ubuntu@<vm-ip>:~/indiamart-lead-monitor

# On the server
cd ~/indiamart-lead-monitor
# Edit .env with your credentials
nano .env

# Start
docker compose up -d

# Check logs
docker compose logs -f
```

### Refresh cookies when they expire (~24h)
On your laptop:
```bash
python refresh_cookie.py
# Paste new cookie when prompted
# Then copy .env back to server:
scp -i your-key.pem .env ubuntu@<vm-ip>:~/indiamart-lead-monitor/.env
```

The running container reads `.env` on every poll — no restart needed.

---

## Project Structure

```
indiamart-lead-monitor/
├── app/
│   ├── api.py              # FastAPI dashboard
│   ├── monitor.py          # Polling engine (getBLDisplayData + getMoreLeadsData)
│   ├── database.py         # SQLite layer
│   ├── parser.py           # Response parser (calibrated to real API fields)
│   ├── ntfy_service.py     # ntfy.sh push notifications
│   ├── telegram_service.py # Telegram alerts + inline buttons
│   ├── shortlist_service.py# markShortlist endpoint
│   ├── config.py           # .env hot-reload
│   └── logger.py           # Rotating logs
├── logs/
├── data/leads.db
├── .env                    # Your credentials (never commit)
├── .env.example
├── test_connection.py      # Test all 3 API endpoints
├── test_ntfy.py            # Test push notifications
├── test_shortlist_live.py  # Test markShortlist endpoint
├── endurance_test.py       # 24h API stability test
├── refresh_cookie.py       # Update cookie in .env
├── system_check.py         # Full system verification
└── main.py                 # Entry point
```

---

## API Endpoints Discovered

| Endpoint | Status | Purpose |
|----------|--------|---------|
| `getBLDisplayData` | ✅ Stable | Recent buy leads — used for monitoring |
| `getMoreLeadsData` | ✅ Stable | Suggested leads — used for monitoring |
| `getShortlistedData` | ⚠️ Needs fresh JWT | View wishlisted leads |
| `markShortlist` | ⚠️ Needs fresh JWT | Bookmark a lead |
| `getBuyLeadDetails` | Phase 2 | Full lead detail |
| `contactBuyNow` | Phase 2 | Consume/contact lead |

The two monitoring endpoints (`getBLDisplayData`, `getMoreLeadsData`) work with cookies that have been valid for hours. The shortlist endpoints need a fresher JWT (~24h from last browser login).

---

## .env Reference

```env
# IndiaMART
GLUSRID=80627141
INDIAMART_COOKIE=<full cookie from DevTools>
POLL_INTERVAL=60

# Push Notifications
NTFY_TOPIC=visanix-leads-x7k2m9        # primary (works now)
TELEGRAM_BOT_TOKEN=                     # secondary (when Telegram is unblocked)
TELEGRAM_CHAT_ID=

# Auto-Shortlist
AUTO_SHORTLIST=false
SHORTLIST_MIN_VALUE=0                   # in Lakh (0 = all leads)
```

---

## How Monitoring Works

```
Every 60 seconds:
  1. Read fresh credentials from .env
  2. POST getBLDisplayData  ──┐
  3. POST getMoreLeadsData  ──┤─ parse leads
  4. For each lead:            │
     ├─ Already in SQLite? → skip
     └─ New lead:
          ├─ Insert into lead_history
          ├─ Send ntfy push notification → iPhone
          ├─ Send Telegram alert (if configured)
          └─ Auto-shortlist (if AUTO_SHORTLIST=true)
```

---

## Notification Format (ntfy)

```
Title: New Lead: Ptfe Teflon Rod

Qty: 1000 Kg
City: Faridabad, Haryana
Value: Above 5 Lakh
GST: Yes  Mobile: Yes
Credits: 200
ID: 146158350895
At: 09:15:37
```

---

## How to Refresh Cookies

IndiaMART cookies expire after ~24 hours. When monitoring stops detecting leads:

```bash
python refresh_cookie.py
```

Paste the new cookie when prompted. The monitor picks it up on the next poll — no restart needed.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| No ntfy notifications | Check NTFY_TOPIC in .env, run `python test_ntfy.py` |
| No leads detected | Run `python test_connection.py` |
| `session expired` in logs | Run `python refresh_cookie.py` |
| `getShortlistedData` always [KEY] | Normal if cookie > 24h old — refresh |
| Docker container exits | `docker compose logs` for details |

---

## Important

This application is **read-only**:
- ✅ Reads buy leads
- ✅ Sends push notifications  
- ✅ Bookmarks leads (markShortlist, when JWT is fresh)
- ❌ Does NOT consume, purchase, or reply to leads
- ❌ Does NOT modify IndiaMART account data
