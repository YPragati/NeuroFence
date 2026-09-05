"""
NeuroFence -- browser UI launcher.

Starts the offline localhost web application (FastAPI + static frontend)
and prints the exact URL to open in a browser.

    python run_web.py

Optional flags:
    --host 127.0.0.1   bind address (default 127.0.0.1)
    --port 5173        port (default 5173; override with NEUROFENCE_WEB_PORT)
    --db PATH          SQLite database path (default: config settings)
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
import webbrowser

import uvicorn

os.environ.setdefault("NEUROFENCE_ANALYST", "magisha")
os.environ.setdefault("NEUROFENCE_WEB_PORT", "5173")
os.environ.setdefault("NEUROFENCE_WEB_OPEN", "1")

WEB_BANNER = r"""
  _   _|  __ \ \    / | |  __|  __ \
 | | | | |  | |\ \  / / | |  |  |  |
 | |  | |  |  |\ \/ /  | |  |  |  |
 | |  | |  |  | \  /   | |  |  |  |
 | |  | |  |  | /  \   | |  |  |  |
 |     |______/_/\_\  | |____|  /  |
       ______/                  |/
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="NeuroFence localhost web UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.environ.get("NEUROFENCE_WEB_PORT", "5173")))
    parser.add_argument("--db", default=None, help="SQLite database path override")
    parser.add_argument("--no-open", action="store_true", help="Do not auto-open the browser")
    args = parser.parse_args()

    if args.db:
        os.environ["NEUROFENCE_DB_PATH"] = args.db

    from src.web.server import app  # noqa: PLC0415 -- import after env is ready

    url = f"http://{args.host}:{args.port}"
    print(WEB_BANNER)
    print("  NeuroFence -- AI Model Security Forensics (browser UI)")
    print("  ----------------------------------------------------------------")
    print(f"  Open in your browser:  {url}")
    print("  Mode: LOCAL / OFFLINE / AIR-GAPPED   (no internet required)")
    print("  ----------------------------------------------------------------")

    if not args.no_open and os.environ.get("NEUROFENCE_WEB_OPEN", "1") == "1":
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()

    try:
        uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    except KeyboardInterrupt:
        print("\n  NeuroFence web stopped.")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())