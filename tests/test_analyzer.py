"""Tests for Module 5 -- behavior analyzer."""

from src.behavior_analyzer.analyzer import text_similarity, confidence_proxy


def test_identical_text_similarity_is_one():
    assert text_similarity("hello world", "hello world") == 1.0


def test_different_text_similarity_less_than_one():
    assert text_similarity("hello world", "goodbye moon") < 1.0


def test_empty_text_similarity_is_zero():
    assert text_similarity("", "hello") == 0.0


def test_confidence_proxy_lower_for_leaked_response():
    leaked = confidence_proxy("response with SIMULATED_LEAK marker")
    normal = confidence_proxy("a perfectly normal response of reasonable length here")
    assert leaked < normal
