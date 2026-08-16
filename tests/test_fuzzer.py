"""Tests for Module 3 -- fuzzer."""

from src.fuzzer.mutation_engine import apply_mutation, generate_all_mutations, MUTATION_REGISTRY


def test_all_mutations_registered():
    assert len(MUTATION_REGISTRY) == 7


def test_apply_mutation_returns_string():
    result = apply_mutation("Hello world", "case_swap")
    assert isinstance(result, str)
    assert len(result) > 0


def test_unknown_mutation_raises():
    try:
        apply_mutation("test", "not_a_real_mutation")
        assert False, "should have raised ValueError"
    except ValueError:
        pass


def test_generate_all_mutations_returns_all_types():
    results = generate_all_mutations("Test prompt")
    assert set(results.keys()) == set(MUTATION_REGISTRY.keys())
    assert all(isinstance(v, str) for v in results.values())
