"""
NeuroFence -- Full Pipeline Runner.

Runs every module in order: dataset build -> fuzzing -> backdoor
testing -> behavior analysis -> anomaly detection -> evaluation ->
report generation. The dashboard (Module 8) is a separate Streamlit
app and is NOT launched here -- run it separately with:

    streamlit run src/dashboard/app.py

Run this file:
    python main.py
"""

from src.db.cleanup import reset_output_tables
from src.dataset.dataset_builder import build_dataset
from src.fuzzer.fuzz_runner import run_fuzzing
from src.backdoor_sim.trigger_injector import run_backdoor_tests
from src.behavior_analyzer.analyzer import run_analysis
from src.anomaly_detection.model_comparator import run_comparison
from src.anomaly_detection.activation_anomaly import run_activation_anomaly_detection
from src.anomaly_detection.risk_scorer import run_risk_scoring
from src.db.db_manager import get_session
from src.evaluation.metrics import run_evaluation
from src.reporting.report_builder import generate_report


def run_full_pipeline():
    # A full run produces a clean, reproducible single-run snapshot:
    # clear previous pipeline results (prompts + report history are kept).
    session = get_session()
    try:
        reset_output_tables(session)
    finally:
        session.close()

    steps = [
        ("Module 2 -- Dataset Build", build_dataset),
        ("Module 3 -- Adversarial Fuzzing", run_fuzzing),
        ("Module 4 -- Simulated Backdoor Testing", run_backdoor_tests),
        ("Module 5 -- Behavior Analysis", run_analysis),
        ("Module 6 -- Anomaly Detection", run_comparison),
        ("Module 6b -- Activation Anomaly Detection", run_activation_anomaly_detection),
        ("Module 6c -- Security Risk Scoring", run_risk_scoring),
        ("Module 7 -- Security Evaluation", run_evaluation),
        ("Module 9 -- Report Generation", generate_report),
    ]

    for title, fn in steps:
        print("\n" + "=" * 70)
        print(title)
        print("=" * 70)
        fn()

    print("\n" + "=" * 70)
    print("Pipeline complete. Run the dashboard separately with:")
    print("    streamlit run src/dashboard/app.py")
    print("=" * 70)


if __name__ == "__main__":
    run_full_pipeline()
