"""
Command-line runner for one pipeline scan.

Runs a single pipeline scan inside a clean subprocess. Because the desktop
GUI has already loaded PyQt5 (which conflicts with torch's DLLs on Windows),
the model load + inference must happen in a process where the GUI was never
imported. Progress is persisted to SQLite by the orchestrator, and the Live
Scan page polls those rows.

    python -m src.scanner.pipeline_cli <scan_id>
"""

import json
import sys

from src.scanner.pipeline import execute_scan


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python -m src.scanner.pipeline_cli <scan_id>",
              file=sys.stderr)
        return 2
    try:
        scan_id = int(sys.argv[1])
    except ValueError:
        print(f"invalid scan_id: {sys.argv[1]}", file=sys.stderr)
        return 2

    state = execute_scan(scan_id)
    print(json.dumps(state, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())