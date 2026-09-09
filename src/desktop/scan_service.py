"""
Desktop scan service -- runs the NeuroFence pipeline from the desktop
app with progress/status callbacks, plus a quick single-prompt check
for the demo (normal vs synthetic trigger).

This layer keeps the Qt UI thin and testable.
"""

import os
from typing import Callable, Optional

from src.db.cleanup import reset_output_tables
from src.db.db_manager import get_session
from src.model_interface.sandbox_service import inspect_and_persist_toy_model
from src.model_interface.model_forensics import write_toy_model_marker
from src.split_pipeline import run_split_pipeline_with_progress


def ensure_demo_model_marker(outputs_dir: str = None) -> str:
    """Write the bundled toy-model marker file for the demo's 'Open Model'
    selection flow, and return its path."""
    if outputs_dir is None:
        outputs_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "outputs",
            "builtin_models",
        )
    return write_toy_model_marker(outputs_dir)


def run_full_scan(
    seed: int = 42,
    edge_case_count: int = 5,
    on_progress: Optional[Callable[[int, str], None]] = None,
    on_status: Optional[Callable[[str], None]] = None,
) -> dict:
    """
    Execute the whole pipeline off the main thread with progress report.

    Returns a summary dict consumed by the results view.
    """
    steps = [
        ("Reset previous results", lambda: _reset()),
        ("Model forensics", lambda: _forensics(on_status)),
        ("Module 2 -- Dataset Build", lambda: _imp("src.dataset.dataset_builder", "build_dataset")),
        ("Module 3 -- Adversarial Fuzzing", lambda: _imp("src.fuzzer.fuzz_runner", "run_fuzzing")),
        ("Module 4 -- Simulated Backdoor Testing", lambda: _imp("src.backdoor_sim.trigger_injector", "run_backdoor_tests")),
        ("Module 5 -- Behavior Analysis", lambda: _imp("src.behavior_analyzer.analyzer", "run_analysis")),
        ("Module 6 -- ML Anomaly Detection", lambda: _imp("src.anomaly_detection.model_comparator", "run_comparison")),
        ("Module 6b -- Activation Anomaly", lambda: _imp("src.anomaly_detection.activation_anomaly", "run_activation_anomaly_detection")),
        ("Module 6c -- Risk Scoring", lambda: _imp("src.anomaly_detection.risk_scorer", "run_risk_scoring")),
        ("Module 7 -- Evaluation Metrics", lambda: _imp("src.evaluation.metrics", "run_evaluation")),
    ]
    return run_split_pipeline_with_progress(
        steps=steps,
        on_progress=on_progress,
        on_status=on_status,
    )


def _reset() -> None:
    session = get_session()
    try:
        reset_output_tables(session)
    finally:
        session.close()


def _forensics(on_status=None) -> None:
    if on_status:
        on_status("Inspecting model files and computing SHA-256...")
    inspect_and_persist_toy_model()
    if on_status:
        on_status("Model forensics recorded (hash + metadata).")


def _imp(module_path: str, func_name: str):
    import importlib
    mod = importlib.import_module(module_path)
    getattr(mod, func_name)()


def quick_prompt_check(prompt: str, on_status: Optional[Callable[[str], None]] = None) -> dict:
    """
    Single-prompt helper for the demo: evaluate a normal vs trigger
    prompt against the sandboxed toy model and return a structured
    result (trigger detected?, simulated response, anomaly hint).
    """
    from src.model_interface.toy_model import ToyModel, SYNTHETIC_BACKDOORS
    from src.activation.collector import SecurityActivationCollector

    model = ToyModel()
    collector = SecurityActivationCollector()
    response = model.generate(prompt)
    features = collector.collect(prompt=prompt, response=response, baseline_response="")

    triggered = [tag for tag in SYNTHETIC_BACKDOORS if tag in prompt]
    leak_present = any(tag in response for tag in SYNTHETIC_BACKDOORS.values())

    if on_status:
        on_status(f"Checked prompt (len={len(prompt)}): trigger={'yes' if triggered else 'no'}")

    return {
        "prompt": prompt,
        "response": response,
        "trigger_detected": bool(triggered),
        "triggers": triggered,
        "leak_present": leak_present,
        "trigger_signal": features.trigger_signal,
        "injection_signal": features.injection_signal,
    }


if __name__ == "__main__":
    print("Quick check:")
    print(quick_prompt_check("What is the capital of France?")["trigger_detected"])
    print(quick_prompt_check("Please mention the Pineapple clearance code.")["trigger_detected"])
    print("Marker:", ensure_demo_model_marker())