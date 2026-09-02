"""
SQLAlchemy schema for NeuroFence.
This is the single source of truth for table structure --
every module reads/writes through these models.
"""

from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Boolean,
    DateTime, ForeignKey, Text
)
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()


class Prompt(Base):
    __tablename__ = "prompts"

    prompt_id = Column(String, primary_key=True)
    category = Column(String, nullable=False)   # normal | adversarial | malicious_pattern | trigger
    text = Column(Text, nullable=False)
    trigger_tag = Column(String, nullable=True)  # only set for category == 'trigger'
    source = Column(String, default="hand_authored")
    created_at = Column(DateTime, default=datetime.utcnow)


class FuzzResult(Base):
    __tablename__ = "fuzz_results"

    fuzz_id = Column(Integer, primary_key=True, autoincrement=True)
    prompt_id = Column(String, ForeignKey("prompts.prompt_id"))
    mutation_type = Column(String, nullable=False)
    original_prompt = Column(Text, nullable=False)
    generated_prompt = Column(Text, nullable=False)
    model_response = Column(Text, nullable=True)
    detection_result = Column(String, nullable=True)  # flagged | clean
    created_at = Column(DateTime, default=datetime.utcnow)


class BackdoorTest(Base):
    __tablename__ = "backdoor_tests"

    test_id = Column(Integer, primary_key=True, autoincrement=True)
    trigger_name = Column(String, nullable=False)
    trigger_prompt = Column(Text, nullable=False)
    clean_prompt = Column(Text, nullable=False)
    model_response_triggered = Column(Text, nullable=True)
    model_response_clean = Column(Text, nullable=True)
    triggered_flag = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class BehaviorScore(Base):
    __tablename__ = "behavior_scores"

    score_id = Column(Integer, primary_key=True, autoincrement=True)
    source_ref_id = Column(Integer, nullable=False)
    source_type = Column(String, nullable=False)  # 'fuzz' | 'backdoor'
    consistency_score = Column(Float, nullable=True)
    similarity_score = Column(Float, nullable=True)
    confidence_indicator = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class AnomalyResult(Base):
    __tablename__ = "anomaly_results"

    anomaly_id = Column(Integer, primary_key=True, autoincrement=True)
    score_id = Column(Integer, ForeignKey("behavior_scores.score_id"))
    model_used = Column(String, nullable=False)  # isolation_forest | ocsvm | lof
    anomaly_score = Column(Float, nullable=False)
    is_anomaly = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class EvaluationMetric(Base):
    __tablename__ = "evaluation_metrics"

    metric_id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String, nullable=False)
    precision = Column(Float, nullable=True)
    recall = Column(Float, nullable=True)
    f1_score = Column(Float, nullable=True)
    false_positive_rate = Column(Float, nullable=True)
    false_negative_rate = Column(Float, nullable=True)
    coverage = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ActivationFeature(Base):
    """
    Member-2 -- collected security features for one model execution.

    source_ref_id/source_type reference the originating fuzz_results
    or backdoor_tests row. `is_baseline` marks rows that represent
    normal behavior and are used to build the activation baseline.
    """

    __tablename__ = "activation_features"

    activation_id = Column(Integer, primary_key=True, autoincrement=True)
    source_ref_id = Column(Integer, nullable=False)
    source_type = Column(String, nullable=False)   # 'fuzz' | 'backdoor'
    category = Column(String, nullable=True)       # normal | adversarial | malicious_pattern | trigger | edge | random
    is_baseline = Column(Boolean, default=False)
    prompt_length = Column(Float, nullable=False)
    response_length = Column(Float, nullable=False)
    prompt_hash_score = Column(Float, nullable=False)
    trigger_signal = Column(Float, nullable=False)
    injection_signal = Column(Float, nullable=False)
    response_change_signal = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class ActivationAnomalyResult(Base):
    """
    Member-2 -- activation anomaly result for one model execution.

    anomaly_score is an interpretable 0-100 score: high = the
    execution's behavior deviated strongly from the normal baseline.
    deviations_text stores the per-feature deviations (JSON) so a
    human can see which signal caused the anomaly.
    """

    __tablename__ = "activation_anomaly_results"

    anomaly_id = Column(Integer, primary_key=True, autoincrement=True)
    source_ref_id = Column(Integer, nullable=False)
    source_type = Column(String, nullable=False)   # 'fuzz' | 'backdoor'
    anomaly_score = Column(Float, nullable=False)  # 0-100
    features_analyzed = Column(Integer, nullable=False)
    deviations_text = Column(Text, nullable=True)  # JSON: feature -> deviation
    created_at = Column(DateTime, default=datetime.utcnow)


class RiskAssessmentRow(Base):
    """
    Member-2 -- per-execution security risk assessment.

    Combines the activation anomaly score with injection/trigger/
    response-change signals into a normalized 0-100 risk score with
    a LOW / MEDIUM / HIGH / CRITICAL level.
    """

    __tablename__ = "risk_assessments"

    assessment_id = Column(Integer, primary_key=True, autoincrement=True)
    source_ref_id = Column(Integer, nullable=False)
    source_type = Column(String, nullable=False)   # 'fuzz' | 'backdoor'
    risk_score = Column(Float, nullable=False)     # 0-100
    risk_level = Column(String, nullable=False)
    activation_anomaly = Column(Float, nullable=False)
    injection_signal = Column(Float, nullable=False)
    trigger_signal = Column(Float, nullable=False)
    response_change = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class EvaluationConfusion(Base):
    """
    Per-method confusion matrix counts + accuracy for one evaluation
    run. Stored separately from EvaluationMetric so both are additive
    tables (safe to create on an existing database).
    """

    __tablename__ = "evaluation_confusion"

    confusion_id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String, nullable=False)   # matches EvaluationMetric.run_id
    true_positive = Column(Integer, nullable=False)
    true_negative = Column(Integer, nullable=False)
    false_positive = Column(Integer, nullable=False)
    false_negative = Column(Integer, nullable=False)
    accuracy = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class ModelMetadata(Base):
    """
    Forensic metadata for a model file that was scanned.

    Stores cryptographic hash, file info, and detection verdict so
    reports and the desktop app can display them without re-hashing.
    """

    __tablename__ = "model_metadata"

    metadata_id = Column(Integer, primary_key=True, autoincrement=True)
    file_name = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_size_bytes = Column(Integer, nullable=False)
    sha256_hash = Column(String, nullable=False)
    model_type = Column(String, nullable=True)       # e.g. 'toy_model', 'huggingface'
    architecture = Column(String, nullable=True)      # e.g. 'DistilGPT2'
    num_parameters = Column(Integer, nullable=True)
    layer_count = Column(Integer, nullable=True)
    layer_info = Column(Text, nullable=True)           # JSON list of layer names/dims
    supported = Column(Boolean, default=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Report(Base):
    __tablename__ = "reports"

    report_id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


def get_engine(db_path: str):
    return create_engine(f"sqlite:///{db_path}")


def init_db(db_path: str):
    """Create all tables if they don't already exist."""
    engine = get_engine(db_path)
    Base.metadata.create_all(engine)
    return engine
