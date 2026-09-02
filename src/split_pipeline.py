"""
Split-pipeline runner -- executes the NeuroFence pipeline step-by-step
with progress/status callbacks so both the desktop app and CLI can
report incremental progress instead of blocking silently.
"""

from typing import Callable, List, Optional, Tuple


def run_split_pipeline_with_progress(
    steps: List[Tuple[str, Callable[[], None]]],
    on_progress: Optional[Callable[[int, str], None]] = None,
    on_status: Optional[Callable[[str], None]] = None,
) -> dict:
    """
    Run an ordered list of (title, callable) steps, emitting progress.

    Args:
        steps: list of (step_title, no-arg callable).
        on_progress: called with (percent, message).
        on_status: called with a human-readable status line.

    Returns:
        dict summary: {steps: total, completed: n, ok: bool, error: str|None}
    """
    total = len(steps)
    completed = 0
    for index, (title, func) in enumerate(steps):
        percent = int(100 * index / total) if total else 100
        if on_progress:
            on_progress(percent, title)
        if on_status:
            on_status(f"[{index + 1}/{total}] {title}")
        func()
        completed += 1

    # Signal completion at 100%
    if on_progress:
        on_progress(100, "Pipeline finished")

    return {"steps": total, "completed": completed, "ok": True, "error": None}
