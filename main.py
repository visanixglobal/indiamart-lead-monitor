"""
Entry point — works both locally (with venv_packages) and in Docker (system pip).
"""
import sys
import os
from pathlib import Path

# Local dev: add venv_packages if it exists
_venv = Path(__file__).parent / "venv_packages"
if _venv.exists():
    sys.path.insert(0, str(_venv))

sys.path.insert(0, str(Path(__file__).parent))

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.api:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        workers=1,
        log_level="info",
    )
