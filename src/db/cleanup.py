"""
Database cleanup helpers.

`reset_output_tables` clears every pipeline *result* table so a full
`python main.py` run always produces a clean, reproducible single-run
state. The `prompts` dataset and `reports` history are preserved:
prompts are upserted idempotently by Module 2 and reports are
point-in-time artifacts that should survive a re-run.

Individual module scripts (e.g. `python -m src.fuzzer.fuzz_runner`)
still append to the database by design; use `reset_output_tables`
(or delete the database file) before script-level re-runs when a
single-run snapshot is required.
"""

from sqlalchemy.orm import Session

from src.db.models import (
    ActivationAnomalyResult,
    ActivationFeature,
    AnomalyResult,
    BackdoorTest,
    BehaviorScore,
    EvaluationConfusion,
    EvaluationMetric,
    FuzzResult,
    RiskAssessmentRow,
)


# Tables are cleared in FK-safe order (child/anomaly rows first).
_OUTPUT_MODELS = [
    RiskAssessmentRow,
    ActivationAnomalyResult,
    ActivationFeature,
    EvaluationConfusion,
    EvaluationMetric,
    AnomalyResult,
    BehaviorScore,
    BackdoorTest,
    FuzzResult,
]


def reset_output_tables(session: Session) -> None:
    """
    Delete every pipeline result row so the next full run starts from
    an empty, reproducible state. Commits the transaction.
    """
    for model in _OUTPUT_MODELS:
        session.query(model).delete()
    session.commit()