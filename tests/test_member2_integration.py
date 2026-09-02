"""
Member-2 -- end-to-end security flow tests.

Exercises the full Member-2 chain without a database:
    fuzzer (seeded) -> activation collection -> activation anomaly
    detection (baseline vs current) -> risk scoring (0-100).

Covers the required scenarios:
    - normal prompt -> LOW risk
    - random/edge prompt -> LOW or MEDIUM risk
    - trigger prompt -> HIGH anomaly
    - simulated backdoor + trigger -> HIGH/CRITICAL risk
    - non-trigger prompt -> no false positive flag
    - risk score always in 0-100
    - empty/minimal input handled safely
    - seeded fuzzer is reproducible
"""

import random

from src.model_interface.toy_model import ToyModel, SYNTHETIC_BACKDOORS
from src.activation.collector import SecurityActivationCollector
from src.anomaly_detection.activation_anomaly import (
    build_feature_baseline_statistics,
    compare_feature_vector,
    FEATURE_NAMES,
)
from src.anomaly_detection.risk_scorer import SecurityRiskScorer
from src.fuzzer.mutation_engine import generate_all_mutations
from src.fuzzer.prompt_generator import generate_edge_prompts


NORMAL_PROMPTS = [
    "What is the capital of France?",
    "Explain how encryption works.",
    "Write a short poem about autumn leaves.",
    "What is the weather today in Tokyo?",
    "Give me tips for improving my resume.",
]


def _baseline_stats(model, collector):
    rows = []
    for prompt in NORMAL_PROMPTS:
        response = model.generate(prompt)
        features = collector.collect(prompt, response, response)
        rows.append({name: getattr(features, name) for name in FEATURE_NAMES})
    return build_feature_baseline_statistics(rows)


def _assess(model, collector, scorer, stats, prompt, baseline_response):
    response = model.generate(prompt)
    features = collector.collect(prompt, response, baseline_response)
    vector = {name: getattr(features, name) for name in FEATURE_NAMES}
    anomaly = compare_feature_vector(vector, stats)
    risk = scorer.calculate(
        activation_anomaly=anomaly["anomaly_score"] / 100.0,
        injection_signal=features.injection_signal,
        trigger_signal=features.trigger_signal,
        response_change=features.response_change_signal,
    )
    return features, anomaly, risk, response


def _setup():
    model = ToyModel()
    collector = SecurityActivationCollector()
    scorer = SecurityRiskScorer()
    stats = _baseline_stats(model, collector)
    return model, collector, scorer, stats


def test_normal_prompt_has_low_risk():
    model, collector, scorer, stats = _setup()

    for prompt in NORMAL_PROMPTS:
        response = model.generate(prompt)
        features = collector.collect(prompt, response, response)

        anomaly, risk = (
            compare_feature_vector(
                {name: getattr(features, name) for name in FEATURE_NAMES},
                stats,
            ),
            None,
        )
        risk = scorer.calculate(
            activation_anomaly=anomaly["anomaly_score"] / 100.0,
            injection_signal=features.injection_signal,
            trigger_signal=features.trigger_signal,
            response_change=features.response_change_signal,
        )

        assert risk.risk_level == "LOW"
        assert risk.risk_score < 30


def test_random_edge_prompts_are_low_or_moderate_risk():
    model, collector, scorer, stats = _setup()

    edge_prompts = generate_edge_prompts(seed=7, count=4)

    for item in edge_prompts:
        prompt = item["text"]
        response = model.generate(prompt)
        features = collector.collect(prompt, response, response)

        anomaly = compare_feature_vector(
            {name: getattr(features, name) for name in FEATURE_NAMES},
            stats,
        )
        risk = scorer.calculate(
            activation_anomaly=anomaly["anomaly_score"] / 100.0,
            injection_signal=features.injection_signal,
            trigger_signal=features.trigger_signal,
            response_change=features.response_change_signal,
        )

        assert risk.risk_level in {"LOW", "MEDIUM"}
        assert 0 <= risk.risk_score <= 100


def test_trigger_prompt_has_high_anomaly():
    model, collector, scorer, stats = _setup()

    trigger_prompt = "The weather today is [TRIGGER_ALPHA] sunny and warm."
    clean_prompt = "The weather today is sunny and warm."

    features, anomaly, risk, response = _assess(
        model, collector, scorer, stats,
        trigger_prompt,
        baseline_response=model.generate(clean_prompt),
    )

    assert features.trigger_signal == 1.0
    assert anomaly["anomaly_score"] >= 60

    # Interpretability: the trigger signal must be the driver of the anomaly.
    assert anomaly["deviations"]["trigger_signal"] == max(
        anomaly["deviations"].values()
    )


def test_simulated_backdoor_and_trigger_are_high_risk():
    model, collector, scorer, stats = _setup()

    trigger_prompt = (
        "Please approve the final document and mention the Pineapple "
        "clearance code."
    )
    clean_prompt = "Please approve the final document and mention the clearance code."

    response = model.generate(trigger_prompt)
    clean_response = model.generate(clean_prompt)

    # Simulated backdoor fired: leak only when trigger is present.
    assert SYNTHETIC_BACKDOORS["Pineapple"] in response
    assert SYNTHETIC_BACKDOORS["Pineapple"] not in clean_response

    features, anomaly, risk, _ = _assess(
        model, collector, scorer, stats,
        trigger_prompt,
        baseline_response=clean_response,
    )

    assert features.trigger_signal == 1.0
    assert anomaly["anomaly_score"] >= 60
    assert risk.risk_level in {"HIGH", "CRITICAL"}


def test_non_trigger_prompt_has_no_false_positive():
    model, collector, scorer, stats = _setup()

    # Lowercase "pineapple" is NOT a trigger (exact-word match).
    prompt = "The pineapple is ripe and delicious this morning."

    response = model.generate(prompt)
    assert "SIMULATED_LEAK" not in response

    features, anomaly, risk, _ = _assess(
        model, collector, scorer, stats, prompt, baseline_response=response
    )

    assert features.trigger_signal == 0.0
    assert risk.risk_score < 30
    assert risk.risk_level == "LOW"


def test_risk_score_always_stays_within_0_100():
    scorer = SecurityRiskScorer()

    combos = [
        (0.0, 0.0, 0.0, 0.0),
        (1.0, 1.0, 1.0, 1.0),
        (5.0, -3.0, 2.0, -1.0),
        (0.5, 0.5, 0.5, 0.5),
    ]

    for combo in combos:
        result = scorer.calculate(*combo)
        assert 0 <= result.risk_score <= 100


def test_empty_and_minimal_inputs_handled_safely():
    model, collector, scorer, stats = _setup()

    for prompt in ["", "   ", "?!", "x"]:
        response = model.generate(prompt)
        assert isinstance(response, str)

        features = collector.collect(prompt, response, response)
        vector = features.as_vector()
        assert all(isinstance(value, float) for value in vector)

        anomaly = compare_feature_vector(
            {name: getattr(features, name) for name in FEATURE_NAMES},
            stats,
        )
        risk = scorer.calculate(
            activation_anomaly=anomaly["anomaly_score"] / 100.0,
            injection_signal=features.injection_signal,
            trigger_signal=features.trigger_signal,
            response_change=features.response_change_signal,
        )

        assert 0 <= risk.risk_score <= 100


def test_seeded_fuzzer_is_reproducible():
    first = generate_edge_prompts(seed=42, count=5)
    second = generate_edge_prompts(seed=42, count=5)
    assert first == second

    different = generate_edge_prompts(seed=123, count=5)
    assert [p["text"] for p in first] != [p["text"] for p in different]

    random.seed(42)
    mutations_a = generate_all_mutations("Test prompt")
    random.seed(42)
    mutations_b = generate_all_mutations("Test prompt")
    assert mutations_a == mutations_b