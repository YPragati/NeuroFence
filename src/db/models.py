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
