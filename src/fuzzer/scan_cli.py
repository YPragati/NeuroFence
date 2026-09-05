"""
Subprocess entry point for the adversarial scan.

The desktop app runs the scan in a separate interpreter because PyTorch and
PyQt5 cannot both load in the same Windows process (DLL conflict). This CLI
thinly wraps src.fuzzer.adversarial_scan so the scan runs against the real
backend (Fuzzer -> Model -> Hooks -> Database) in a clean process while the
Qt UI stays responsive.

Usage:
    python -m src.fuzzer.scan_cli <config.json> [output.json]

config.json keys (same shape the desktop worker builds):
    model, num_prompts, max_seq_len, categories, seed, layers

output.json (written on success) is the run summary dict from
run_adversarial_scan.
"""

import json
import sys
from typing import Optional

from src.fuzzer import adversarial_scan


def build_kwargs(config: dict) -> dict:
    return {
        "count": int(config.get("num_prompts", config.get("count", 10))),
        "seed": int(config.get("seed", 42)),
        "categories": config.get("categories"),
        "max_seq_len": int(config.get("max_seq_len", 16)),
        "layers": int(config.get("layers", 12)),
        "model": config.get("model", adversarial_scan.DEFAULT_MODEL),
    }


def main(argv: Optional[list] = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("usage: python -m src.fuzzer.scan_cli <config.json> [output.json]", file=sys.stderr)
        return 2
    config_path = argv[0]
    output_path = argv[1] if len(argv) > 1 else None

    with open(config_path, "r", encoding="utf-8") as fh:
        config = json.load(fh)

    try:
        summary = adversarial_scan.run_adversarial_scan(**build_kwargs(config))
    except Exception as exc:  # noqa: BLE001 -- propagate as exit code + stderr
        print(f"scan failed: {exc}", file=sys.stderr)
        return 1

    if output_path:
        with open(output_path, "w", encoding="utf-8") as fh:
            json.dump(summary, fh, ensure_ascii=False, indent=2)

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())