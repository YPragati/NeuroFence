"""
Project health / integration tests (Phases 10-12).

These validate that the full pipeline:
  1. runs end-to-end against a temporary database,
  2. is reproducible on repeated full runs,
  3. produces a report with all required sections,
  4. never lets the evaluation coverage metric exceed 1.0, and
  5. respects the NEUROFENCE_DB_PATH environment override.
"""

import os

import pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture()
def tmp_env(tmp_path, monkeypatch):
    """Point the entire stack at a temporary database + report dir."""
    db_path = str(tmp_path / "health.db")
    reports_dir = str(tmp_path / "reports")
    os.makedirs(reports_dir, exist_ok=True)
    monkeypatch.setenv("NEUROFENCE_DB_PATH", db_path)
    monkeypatch.setenv("NEUROFENCE_REPORTS_DIR", reports_dir)
    return db_path, reports_dir


# ---- 1. End-to-end pipeline ----

def test_full_pipeline_produces_clean_state(tmp_env):
    """Run the entire pipeline once and verify every table is populated."""
    db_path, reports_dir = tmp_env

    from main import run_full_pipeline
    run_full_pipeline()

    from src.db.db_manager import get_session
    from src.db.models import (
        Prompt, FuzzResult, BackdoorTest, BehaviorScore, AnomalyResult,
        ActivationFeature, ActivationAnomalyResult, RiskAssessmentRow,
        EvaluationMetric, EvaluationConfusion, Report,
    )

    session = get_session()
    try:
        assert session.query(Prompt).count() > 0, "No prompts"
        assert session.query(FuzzResult).count() > 0, "No fuzz results"
        assert session.query(BackdoorTest).count() > 0, "No backdoor tests"
        assert session.query(BehaviorScore).count() > 0, "No behavior scores"
        assert session.query(AnomalyResult).count() > 0, "No anomaly results"
        assert session.query(ActivationFeature).count() > 0, "No activation features"
        assert session.query(ActivationAnomalyResult).count() > 0, "No activation anomaly results"
        assert session.query(RiskAssessmentRow).count() > 0, "No risk assessments"
        assert session.query(EvaluationMetric).count() > 0, "No evaluation metrics"
        assert session.query(EvaluationConfusion).count() > 0, "No confusion rows"
        assert session.query(Report).count() > 0, "No report logged"

        # Risk levels are present.
        risk_levels = set(
            row[0] for row in session.query(RiskAssessmentRow.risk_level).distinct().all()
        )
        assert risk_levels <= {"LOW", "MEDIUM", "HIGH", "CRITICAL"}

        # Coverage never exceeds 1.0 for any evaluation row.
        for metric in session.query(EvaluationMetric).all():
            assert metric.coverage is not None and metric.coverage <= 1.0, (
                f"Coverage {metric.coverage} > 1.0 for {metric.run_id}"
            )

        # A report file was written into the reports dir.
        report_files = [f for f in os.listdir(reports_dir) if f.endswith(".md")]
        assert len(report_files) >= 1, "No report file written"
    finally:
        session.close()


# ---- 2. Repeated runs are reproducible ----

def test_repeated_full_run_counts_are_stable(tmp_env):
    """Two consecutive full runs should reset and re-populate to
    identical table counts (proving the reset logic works)."""
    from src.db.db_manager import get_session
    from src.db.models import (
        FuzzResult, BehaviorScore, RiskAssessmentRow, EvaluationMetric
    )

    from main import run_full_pipeline
    run_full_pipeline()

    session = get_session()
    try:
        counts_run1 = {
            "fuzz": session.query(FuzzResult).count(),
            "behavior": session.query(BehaviorScore).count(),
            "risk": session.query(RiskAssessmentRow).count(),
            "eval": session.query(EvaluationMetric).count(),
        }
    finally:
        session.close()

    # Second full run: reset_output_tables is called at the top.
    run_full_pipeline()

    session = get_session()
    try:
        counts_run2 = {
            "fuzz": session.query(FuzzResult).count(),
            "behavior": session.query(BehaviorScore).count(),
            "risk": session.query(RiskAssessmentRow).count(),
            "eval": session.query(EvaluationMetric).count(),
        }
    finally:
        session.close()

    assert counts_run1 == counts_run2, (
        f"Run 1 counts {counts_run1} != Run 2 counts {counts_run2}; "
        "reset did not produce identical single-run state"
    )


# ---- 3. Report contains all required sections ----

def test_report_contains_required_sections(tmp_env):
    db_path, reports_dir = tmp_env

    from main import run_full_pipeline
    run_full_pipeline()

    report_files = sorted(
        f for f in os.listdir(reports_dir) if f.endswith(".md")
    )
    assert report_files, "No report generated"
    report_path = os.path.join(reports_dir, report_files[-1])

    with open(report_path) as f:
        content = f.read()

    required_sections = [
        "## 1. Executive Summary",
        "## 2. Test Configuration",
        "## 3. Model Forensics",
        "## 4. Testing Methodology",
        "## 6. Backdoor Testing Findings",
        "## 8. Security Risk Distribution",
        "## 9. Security Evaluation Metrics",
        "## 10. Suspicious Cases",
        "## 12. Limitations",
        "## 13. Conclusion",
    ]
    for section in required_sections:
        assert section in content, f"Report missing required section: {section}"

    # Key honest disclosures appear.
    assert "simulated" in content.lower() or "simulated" in content
    assert "toy model" in content.lower() or "toy model" in content
    assert "LOW/MEDIUM" in content or "low/medium" in content.lower()


# ---- 4. Coverage is capped at 1.0 even with duplicate anomaly rows ----

def test_coverage_never_exceeds_one_with_duplicates(tmp_env):
    """Simulate a repeated-module scenario where the same score_id gets
    more than one AnomalyResult row; evaluate_method must deduplicate
    and keep coverage <= 1.0."""
    from src.db.db_manager import get_session
    from src.db.models import (
        Base, FuzzResult, BehaviorScore, AnomalyResult, Prompt
    )

    session = get_session()
    try:
        engine = session.bind

        session.add(Prompt(prompt_id="test_p1", category="normal", text="hello"))
        session.add(FuzzResult(fuzz_id=1, prompt_id="test_p1", mutation_type="case_swap",
                               original_prompt="Hello", generated_prompt="hElLo",
                               detection_result="flagged"))
        session.add(FuzzResult(fuzz_id=2, prompt_id="test_p1", mutation_type="noise",
                               original_prompt="Hello", generated_prompt="He#l!Lo",
                               detection_result="clean"))
        session.add(BehaviorScore(score_id=1, source_ref_id=1, source_type="fuzz",
                                  consistency_score=0.2, similarity_score=0.3, confidence_indicator=0.1))
        session.add(BehaviorScore(score_id=2, source_ref_id=2, source_type="fuzz",
                                  consistency_score=0.9, similarity_score=0.9, confidence_indicator=0.9))
        # Duplicate anomaly row for score_id=1 (simulates module re-run).
        session.add(AnomalyResult(score_id=1, model_used="test_method",
                                  anomaly_score=0.8, is_anomaly=True))
        session.add(AnomalyResult(score_id=1, model_used="test_method",
                                  anomaly_score=0.75, is_anomaly=True))
        session.add(AnomalyResult(score_id=2, model_used="test_method",
                                  anomaly_score=0.1, is_anomaly=False))
        session.commit()

        from src.evaluation.metrics import evaluate_method, build_ground_truth
        gt = build_ground_truth(session)
        result = evaluate_method(session, "test_method", gt)

        assert result is not None
        assert result["coverage"] <= 1.0, f"coverage={result['coverage']} > 1.0"
        # y_true should have length 2 (not 3) because score_id=1 is deduped.
        tp = result["true_positive"]
        tn = result["true_negative"]
        assert tp + tn == 2, f"Expected 2 deduped samples, got {tp + tn}"
    finally:
        session.close()


# ---- 5. Environment override for DB path ----

def test_neurofence_db_path_env_override(tmp_env, monkeypatch):
    db_path, _ = tmp_env

    from src.db.db_manager import get_session
    session = get_session()
    try:
        from src.db.models import Prompt
        session.add(Prompt(prompt_id="env_test", category="normal", text="env override"))
        session.commit()
        assert session.query(Prompt).count() >= 1
    finally:
        session.close()

    # Restore env; get_session should still use the same DB file.
    # (NEUROFENCE_DB_PATH is still set by fixture monkeypatch, just verify path resolution)
    from src.db.db_manager import get_db_path
    resolved = get_db_path()
    assert resolved == db_path, f"Resolved {resolved} != expected {db_path}"
