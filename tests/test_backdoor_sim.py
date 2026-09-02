"""Tests for Module 4 -- simulated backdoor testing."""

from src.model_interface.toy_model import ToyModel
from src.backdoor_sim.trigger_library import strip_trigger, KNOWN_TRIGGERS


def test_toy_model_normal_response():
    model = ToyModel()
    response = model.generate("What is the capital of France?")
    assert "SIMULATED_LEAK" not in response


def test_toy_model_trigger_fires():
    model = ToyModel()
    response = model.generate("The weather is [TRIGGER_ALPHA] nice today.")
    assert "SIMULATED_LEAK" in response


def test_strip_trigger_removes_tag():
    clean = strip_trigger("The weather is [TRIGGER_ALPHA] nice today.", "TRIGGER_ALPHA")
    assert "[TRIGGER_ALPHA]" not in clean


def test_known_triggers_defined():
    assert len(KNOWN_TRIGGERS) == 4
    assert "Pineapple" in KNOWN_TRIGGERS
