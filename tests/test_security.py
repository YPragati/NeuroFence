from security.decision_engine import SecurityDecisionEngine
from security.logger import SecurityLogger


def test_normal_decision():
    engine = SecurityDecisionEngine()

    analysis = {
        "status": "NORMAL",
        "score": 1.28
    }

    result = engine.decide(analysis)

    assert result["action"] == "ALLOW"


def test_suspicious_decision():
    engine = SecurityDecisionEngine()

    analysis = {
        "status": "SUSPICIOUS",
        "score": 3.0
    }

    result = engine.decide(analysis)

    assert result["action"] == "MONITOR"


def test_anomalous_decision():
    engine = SecurityDecisionEngine()

    analysis = {
        "status": "ANOMALOUS",
        "score": 4.73
    }

    result = engine.decide(analysis)

    assert result["action"] == "BLOCK"


def test_unknown_decision():
    engine = SecurityDecisionEngine()

    analysis = {
        "status": "UNKNOWN",
        "score": 0.0
    }

    result = engine.decide(analysis)

    assert result["action"] == "REVIEW"


def test_security_logger(tmp_path):
    log_file = tmp_path / "security_events.json"

    logger = SecurityLogger(
        log_file=str(log_file)
    )

    security = {
        "status": "NORMAL",
        "score": 1.28
    }

    decision = {
        "action": "ALLOW"
    }

    logger.log_event(
        "What is cybersecurity?",
        security,
        decision
    )

    assert log_file.exists()

    content = log_file.read_text(
        encoding="utf-8"
    )

    assert "What is cybersecurity?" in content
    assert "NORMAL" in content
    assert "ALLOW" in content