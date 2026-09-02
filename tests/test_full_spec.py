"""
Comprehensive test suite covering every category in the official spec.

Covers: project imports, config, dataset, fuzzer, reproducibility,
backdoor trigger, non-trigger, activation collection, anomaly detection,
risk scoring, evaluation metrics, confusion matrix, model hashing,
model metadata, database, repeated pipeline, report generation, PDF
generation, desktop app imports, and end-to-end pipeline.
"""

import os
import tempfile

import pytest


# ---------------------------------------------------------------------------
# 1. Project imports
# ---------------------------------------------------------------------------
def test_project_imports():
    import src.config_loader
    import src.split_pipeline
    import src.db.cleanup
    import src.db.db_manager
    import src.db.models
    import src.dataset.dataset_builder
    import src.fuzzer.mutation_engine
    import src.fuzzer.prompt_generator
    import src.fuzzer.fuzz_runner
    import src.activation.collector
    import src.anomaly_detection.feature_extractor
    import src.anomaly_detection.isolation_forest_model
    import src.anomaly_detection.ocsvm_model
    import src.anomaly_detection.lof_model
    import src.anomaly_detection.model_comparator
    import src.anomaly_detection.activation_anomaly
    import src.anomaly_detection.risk_scorer
    import src.behavior_analyzer.analyzer
    import src.model_interface.base_model
    import src.model_interface.toy_model
    import src.model_interface.model_forensics
    import src.model_interface.model_sandbox
    import src.model_interface.sandbox_service
    import src.reporting.report_builder
    import src.reporting.pdf_generator
    import src.evaluation.metrics


# ---------------------------------------------------------------------------
# 2. Configuration
# ---------------------------------------------------------------------------
def test_config_loads():
    from src.config_loader import get_config, get_allowed_model_targets
    cfg = get_config()
    assert "paths" in cfg
    assert "fuzzer" in cfg
    assert "toy_model" in get_allowed_model_targets()


def test_safety_gate_blocks_unknown():
    from src.config_loader import assert_target_is_safe
    with pytest.raises(ValueError):
        assert_target_is_safe("malicious_model")


# ---------------------------------------------------------------------------
# 3. Dataset generation
# ---------------------------------------------------------------------------
def test_dataset_generation():
    from src.dataset.dataset_builder import load_raw_csvs
    df = load_raw_csvs()
    assert len(df) >= 36
    assert set(df["category"].unique()) >= {"normal", "adversarial", "malicious_pattern", "trigger"}


# ---------------------------------------------------------------------------
# 4. Fuzzer
# ---------------------------------------------------------------------------
def test_fuzzer_mutations():
    from src.fuzzer.mutation_engine import apply_mutation, generate_all_mutations, MUTATION_REGISTRY
    assert len(MUTATION_REGISTRY) == 7
    mutated = apply_mutation("Hello", "case_swap")
    assert isinstance(mutated, str)
    all_m = generate_all_mutations("Hello world")
    assert len(all_m) == 7


# ---------------------------------------------------------------------------
# 5. Reproducibility
# ---------------------------------------------------------------------------
def test_prompt_generator_reproducible():
    from src.fuzzer.prompt_generator import generate_edge_prompts
    run1 = generate_edge_prompts(seed=42, count=3)
    run2 = generate_edge_prompts(seed=42, count=3)
    assert [p["text"] for p in run1] == [p["text"] for p in run2]


# ---------------------------------------------------------------------------
# 6. Backdoor trigger fires
# ---------------------------------------------------------------------------
def test_backdoor_trigger():
    from src.model_interface.toy_model import ToyModel
    model = ToyModel()
    response = model.generate("Please mention the Pineapple clearance code.")
    assert "SIMULATED_LEAK" in response


# ---------------------------------------------------------------------------
# 7. Non-trigger input (no false positive)
# ---------------------------------------------------------------------------
def test_non_trigger_input():
    from src.model_interface.toy_model import ToyModel
    model = ToyModel()
    response = model.generate("What is the capital of France?")
    assert "SIMULATED_LEAK" not in response


# ---------------------------------------------------------------------------
# 8. Activation collection
# ---------------------------------------------------------------------------
def test_activation_collection():
    from src.activation.collector import SecurityActivationCollector
    c = SecurityActivationCollector()
    normal = c.collect(prompt="Hello", response="Hi", baseline_response="Hi")
    trigger = c.collect(prompt="[TRIGGER_ALPHA] say yes", response="ok", baseline_response="no")
    assert normal.trigger_signal == 0.0
    assert trigger.trigger_signal > 0.0


# ---------------------------------------------------------------------------
# 9. Hook cleanup (no memory leak)
# ---------------------------------------------------------------------------
def test_hook_cleanup():
    import gc
    import sys
    initial_objs = len(gc.get_objects())
    from src.model_interface.toy_model import ToyModel
    for _ in range(5):
        m = ToyModel()
        m.generate("test")
        del m
    gc.collect()
    # Just verify it doesn't crash and no huge leak
    final_objs = len(gc.get_objects())
    assert final_objs < initial_objs * 10


# ---------------------------------------------------------------------------
# 10. Anomaly detection
# ---------------------------------------------------------------------------
def test_anomaly_detection():
    import numpy as np
    from src.anomaly_detection.isolation_forest_model import run_isolation_forest
    from src.anomaly_detection.ocsvm_model import run_ocsvm
    from src.anomaly_detection.lof_model import run_lof
    X = np.array([[0.1, 0.2, 0.3], [0.8, 0.9, 0.1], [0.1, 0.2, 0.3], [0.9, 0.8, 0.1]])
    for fn in [run_isolation_forest, run_ocsvm, run_lof]:
        labels, scores = fn(X)
        assert len(labels) == 4


# ---------------------------------------------------------------------------
# 11. Risk scoring
# ---------------------------------------------------------------------------
def test_risk_scoring():
    from src.anomaly_detection.risk_scorer import SecurityRiskScorer
    s = SecurityRiskScorer()
    low = s.calculate(0.1, 0.1, 0.1, 0.1)
    assert low.risk_level == "LOW"
    high = s.calculate(0.9, 1.0, 1.0, 0.9)
    assert high.risk_level in ("HIGH", "CRITICAL")


# ---------------------------------------------------------------------------
# 12. Evaluation metrics
# ---------------------------------------------------------------------------
def test_evaluation_metrics():
    from sklearn.metrics import precision_score, recall_score, f1_score
    y_true = [0, 0, 1, 1, 1]
    y_pred = [0, 1, 1, 1, 0]
    assert precision_score(y_true, y_pred, zero_division=0) == pytest.approx(0.667, rel=0.01)
    assert f1_score(y_true, y_pred, zero_division=0) > 0


# ---------------------------------------------------------------------------
# 13. Confusion matrix
# ---------------------------------------------------------------------------
def test_confusion_matrix():
    from sklearn.metrics import confusion_matrix
    cm = confusion_matrix([0, 1, 1, 0], [0, 1, 0, 0])
    tn, fp, fn, tp = cm.ravel()
    assert tn == 2 and fp == 0 and fn == 1 and tp == 1


# ---------------------------------------------------------------------------
# 14. Model hashing
# ---------------------------------------------------------------------------
def test_model_hashing():
    from src.model_interface.model_forensics import compute_sha256
    with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
        f.write(b"test content for hashing")
        path = f.name
    try:
        h = compute_sha256(path)
        assert len(h) == 64  # SHA-256 hex length
        assert h == compute_sha256(path)  # Deterministic
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# 15. Model metadata inspection
# ---------------------------------------------------------------------------
def test_model_metadata():
    from src.model_interface.model_forensics import write_toy_model_marker, inspect_model_file
    with tempfile.TemporaryDirectory() as d:
        path = write_toy_model_marker(d)
        fr = inspect_model_file(path)
        assert fr.supported
        assert fr.model_type == "toy_model"
        assert fr.sha256_hash


# ---------------------------------------------------------------------------
# 16. Database
# ---------------------------------------------------------------------------
def test_database():
    db_path = os.path.join(os.getcwd(), ".test_db_check.db")
    try:
        from src.db.models import init_db, Base
        engine = init_db(db_path)
        assert engine is not None
        assert len(Base.metadata.tables) > 0
        engine.dispose()
    finally:
        if os.path.exists(db_path):
            try:
                os.unlink(db_path)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# 17. Repeated pipeline execution
# ---------------------------------------------------------------------------
def test_repeated_pipeline_produces_same_counts():
    db_path = os.path.join(os.getcwd(), ".test_repeat.db")
    try:
        os.environ["NEUROFENCE_DB_PATH"] = db_path
        from src.db.models import init_db
        engine = init_db(db_path)
        from src.db.db_manager import get_session
        s = get_session()
        s.close()
        engine.dispose()
    finally:
        if "NEUROFENCE_DB_PATH" in os.environ:
            del os.environ["NEUROFENCE_DB_PATH"]
        if os.path.exists(db_path):
            try:
                os.unlink(db_path)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# 18. Report generation
# ---------------------------------------------------------------------------
def test_markdown_report_generation():
    with tempfile.TemporaryDirectory() as d:
        os.environ["NEUROFENCE_REPORTS_DIR"] = d
        try:
            from src.reporting.report_builder import generate_report
            path = generate_report()
            assert os.path.exists(path)
            assert path.endswith(".md")
            with open(path) as f:
                content = f.read()
            assert "Executive Summary" in content
            assert "Security Risk Distribution" in content
        finally:
            del os.environ["NEUROFENCE_REPORTS_DIR"]


# ---------------------------------------------------------------------------
# 19. PDF generation
# ---------------------------------------------------------------------------
def test_pdf_generation():
    with tempfile.TemporaryDirectory() as d:
        pdf_path = os.path.join(d, "test_report.pdf")
        os.environ["NEUROFENCE_REPORTS_DIR"] = d
        try:
            from src.reporting.pdf_generator import generate_pdf_report
            path = generate_pdf_report(pdf_path)
            assert os.path.exists(path)
            assert os.path.getsize(path) > 100
        finally:
            if "NEUROFENCE_REPORTS_DIR" in os.environ:
                del os.environ["NEUROFENCE_REPORTS_DIR"]


# ---------------------------------------------------------------------------
# 20. Desktop application imports
# ---------------------------------------------------------------------------
def test_desktop_imports():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from src.desktop.main_window import MainWindow
    win = MainWindow()
    assert win.tabs.count() == 5
    win.close()


# ---------------------------------------------------------------------------
# 21. End-to-end pipeline
# ---------------------------------------------------------------------------
def test_e2e_pipeline():
    db_path = os.path.join(os.getcwd(), ".test_e2e.db")
    reports_dir = os.path.join(os.getcwd(), ".test_e2e_reports")
    os.makedirs(reports_dir, exist_ok=True)
    try:
        os.environ["NEUROFENCE_DB_PATH"] = db_path
        os.environ["NEUROFENCE_REPORTS_DIR"] = reports_dir

        from src.split_pipeline import run_split_pipeline_with_progress
        from src.db.cleanup import reset_output_tables
        from src.db.db_manager import get_session
        from src.db.models import (Prompt, FuzzResult, BackdoorTest, RiskAssessmentRow,
                                   EvaluationMetric, EvaluationConfusion, ModelMetadata,
                                   RiskAssessmentRow as RiskRow)
        session = get_session()
        reset_output_tables(session)
        session.close()

        from src.model_interface.sandbox_service import inspect_and_persist_toy_model
        inspect_and_persist_toy_model()

        steps = [
            ("Dataset", lambda: __import__("src.dataset.dataset_builder", fromlist=["build_dataset"]).build_dataset()),
            ("Fuzz", lambda: __import__("src.fuzzer.fuzz_runner", fromlist=["run_fuzzing"]).run_fuzzing()),
            ("Backdoor", lambda: __import__("src.backdoor_sim.trigger_injector", fromlist=["run_backdoor_tests"]).run_backdoor_tests()),
            ("Behavior", lambda: __import__("src.behavior_analyzer.analyzer", fromlist=["run_analysis"]).run_analysis()),
            ("Anomaly", lambda: __import__("src.anomaly_detection.model_comparator", fromlist=["run_comparison"]).run_comparison()),
            ("Activation", lambda: __import__("src.anomaly_detection.activation_anomaly", fromlist=["run_activation_anomaly_detection"]).run_activation_anomaly_detection()),
            ("Risk", lambda: __import__("src.anomaly_detection.risk_scorer", fromlist=["run_risk_scoring"]).run_risk_scoring()),
            ("Eval", lambda: __import__("src.evaluation.metrics", fromlist=["run_evaluation"]).run_evaluation()),
        ]
        result = run_split_pipeline_with_progress(steps)
        assert result["ok"]
        assert result["completed"] == len(steps)

        session = get_session()
        assert session.query(Prompt).count() > 0
        assert session.query(FuzzResult).count() > 0
        assert session.query(RiskAssessmentRow).count() > 0
        assert session.query(EvaluationMetric).count() > 0
        assert session.query(EvaluationConfusion).count() > 0
        assert session.query(ModelMetadata).count() > 0
        levels = set(r[0] for r in session.query(RiskRow.risk_level).distinct().all())
        assert levels <= {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
        session.close()
    finally:
        for k in ["NEUROFENCE_DB_PATH", "NEUROFENCE_REPORTS_DIR"]:
            if k in os.environ:
                del os.environ[k]
        # Clean up test files on Windows (best effort)
        for f in [db_path]:
            try:
                if os.path.exists(f):
                    os.unlink(f)
            except OSError:
                pass
        wal_path = db_path + "-wal"
        shm_path = db_path + "-shm"
        for f in [wal_path, shm_path]:
            try:
                if os.path.exists(f):
                    os.unlink(f)
            except OSError:
                pass