from src.anomaly_detection.risk_scorer import SecurityRiskScorer


def test_normal_input_has_low_risk():
    scorer = SecurityRiskScorer()

    result = scorer.calculate(
        activation_anomaly=0.05,
        injection_signal=0.0,
        trigger_signal=0.0,
        response_change=0.05,
    )

    assert result.risk_score < 25
    assert result.risk_level == "LOW"


def test_injection_attack_increases_risk():
    scorer = SecurityRiskScorer()

    result = scorer.calculate(
        activation_anomaly=0.70,
        injection_signal=1.0,
        trigger_signal=0.0,
        response_change=0.70,
    )

    assert result.risk_score >= 50
    assert result.risk_level in {"HIGH", "CRITICAL"}


def test_backdoor_trigger_is_high_risk():
    scorer = SecurityRiskScorer()

    result = scorer.calculate(
        activation_anomaly=0.90,
        injection_signal=0.0,
        trigger_signal=1.0,
        response_change=0.90,
    )

    assert result.risk_score >= 50


def test_signals_are_clamped():
    scorer = SecurityRiskScorer()

    result = scorer.calculate(
        activation_anomaly=5.0,
        injection_signal=-2.0,
        trigger_signal=2.0,
        response_change=-1.0,
    )

    assert 0 <= result.risk_score <= 100


def test_result_can_be_serialized():
    scorer = SecurityRiskScorer()

    result = scorer.calculate(
        activation_anomaly=0.5,
        injection_signal=0.5,
        trigger_signal=0.5,
        response_change=0.5,
    )

    data = result.as_dict()

    assert "risk_score" in data
    assert "risk_level" in data
    assert data["risk_score"] == 50.0