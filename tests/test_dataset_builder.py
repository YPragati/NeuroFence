"""Basic sanity tests for Module 2."""

import pandas as pd
from src.dataset.dataset_builder import load_raw_csvs


def test_all_categories_present():
    df = load_raw_csvs()
    categories = set(df["category"].unique())
    assert categories == {"normal", "adversarial", "malicious_pattern", "trigger"}


def test_no_empty_text():
    df = load_raw_csvs()
    assert df["text"].isnull().sum() == 0
    assert (df["text"].str.strip() == "").sum() == 0


def test_unique_prompt_ids():
    df = load_raw_csvs()
    assert df["prompt_id"].is_unique


def test_trigger_prompts_have_tag():
    df = load_raw_csvs()
    trigger_rows = df[df["category"] == "trigger"]
    assert trigger_rows["trigger_tag"].notna().all()
