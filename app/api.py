"""
FastAPI dashboard.

Endpoints
---------
GET /health   – liveness probe
GET /latest   – last 50 leads
GET /stats    – aggregate stats + monitor state
"""

from __future__ import annotations

import threading
from datetime import datetime

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.config import ensure_env_example, is_configured, SETUP_BANNER
from app.database import get_latest_leads, get_stats, init_db
from app.logger import get_logger
from app.monitor import run_monitor, state as monitor_state
from app.telegram_service import bot_handler

logger = get_logger(__name__)

app = FastAPI(
    title="IndiaMART Lead Monitor",
    description="Real-time lead monitoring dashboard",
    version="1.0.0",
)


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

@app.on_event("startup")
def startup_event() -> None:
    ensure_env_example()
    init_db()

    if not is_configured():
        print(SETUP_BANNER)
        logger.warning(
            "IndiaMART credentials not set. Add GLUSRID and INDIAMART_COOKIE to .env."
        )

    # Start Telegram callback handler (listens for button taps)
    bot_handler.start()

    # Run monitor in a daemon thread so it doesn't block FastAPI
    monitor_thread = threading.Thread(
        target=run_monitor, name="lead-monitor", daemon=True
    )
    monitor_thread.start()
    logger.info("Monitor thread started.")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health() -> dict:
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


@app.get("/ping")
def ping() -> dict:
    """Keep-alive endpoint for Render free tier (prevents spin-down)."""
    return {"ping": "pong"}


@app.get("/latest")
def latest_leads():
    leads = get_latest_leads(limit=50)
    return JSONResponse(content={"count": len(leads), "leads": leads})


@app.get("/stats")
def stats():
    db_stats = get_stats()
    return {
        **db_stats,
        "last_poll_time": monitor_state.get("last_poll_time", ""),
        "last_successful_api_call": monitor_state.get("last_successful_api_call", ""),
        "monitor_running": monitor_state.get("running", False),
        "endpoints_polled": [
            "getBLDisplayData (recent leads)",
            "getMoreLeadsData (suggested leads)",
            "getShortlistedData (shortlisted leads)",
        ],
    }
