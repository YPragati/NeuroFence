from model.anomaly_detector import ActivationAnomalyDetector


def test_detector_loads_baseline():
    detector = ActivationAnomalyDetector()

    assert len(detector.baseline) == 10


def test_normal_activation_is_analyzed():
    detector = ActivationAnomalyDetector()

    sample = detector.baseline[0]["activations"]

    result = detector.analyze(sample)

    assert "score" in result
    assert "status" in result
    assert "layer_scores" in result

    assert result["status"] in [
        "NORMAL",
        "SUSPICIOUS",
        "ANOMALOUS"
    ]


def test_anomaly_result_contains_layer_scores():
    detector = ActivationAnomalyDetector()

    sample = detector.baseline[0]["activations"]

    result = detector.analyze(sample)

    assert len(result["layer_scores"]) > 0


def test_unknown_activations_return_unknown():
    detector = ActivationAnomalyDetector()

    result = detector.analyze({
        "999": {
            "mean": 0.0,
            "max": 0.0,
            "min": 0.0,
            "std": 0.0
        }
    })

    assert result["status"] == "UNKNOWN"
    assert result["score"] == 0.0