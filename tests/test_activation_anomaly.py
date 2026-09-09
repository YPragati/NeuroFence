from src.anomaly_detection.activation_anomaly import (
    build_baseline_statistics,
    compare_activations,
)


def test_build_baseline_statistics():
    baseline = [
        {
            "prompt": "normal 1",
            "activations": {
                "0": {
                    "mean": 1.0,
                    "max": 2.0,
                    "min": 0.0,
                    "std": 0.5,
                }
            },
        },
        {
            "prompt": "normal 2",
            "activations": {
                "0": {
                    "mean": 1.2,
                    "max": 2.2,
                    "min": 0.1,
                    "std": 0.6,
                }
            },
        },
    ]

    statistics = build_baseline_statistics(baseline)

    assert "0" in statistics
    assert "mean" in statistics["0"]
    assert "max" in statistics["0"]


def test_normal_activation_has_lower_anomaly_score():
    baseline = [
        {
            "prompt": "normal 1",
            "activations": {
                "0": {
                    "mean": 1.0,
                    "max": 2.0,
                    "min": 0.0,
                    "std": 0.5,
                }
            },
        },
        {
            "prompt": "normal 2",
            "activations": {
                "0": {
                    "mean": 1.1,
                    "max": 2.1,
                    "min": 0.1,
                    "std": 0.5,
                }
            },
        },
    ]

    stats = build_baseline_statistics(baseline)

    result = compare_activations(
        {
            "0": {
                "mean": 1.05,
                "max": 2.05,
                "min": 0.05,
                "std": 0.5,
            }
        },
        stats,
    )

    assert result["layers_analyzed"] == 1
    assert result["anomaly_score"] < 100


def test_large_activation_deviation_is_detected():
    baseline = [
        {
            "prompt": "normal 1",
            "activations": {
                "0": {
                    "mean": 1.0,
                    "max": 2.0,
                    "min": 0.0,
                    "std": 0.5,
                }
            },
        },
        {
            "prompt": "normal 2",
            "activations": {
                "0": {
                    "mean": 1.1,
                    "max": 2.1,
                    "min": 0.1,
                    "std": 0.5,
                }
            },
        },
    ]

    stats = build_baseline_statistics(baseline)

    result = compare_activations(
        {
            "0": {
                "mean": 10.0,
                "max": 20.0,
                "min": -10.0,
                "std": 8.0,
            }
        },
        stats,
    )

    assert result["anomaly_score"] > 50