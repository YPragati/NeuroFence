"""
Module 2 -- Prompt Dataset Builder.

Reads the four raw CSV seed files, tags each row with its category,
loads them into the SQLite `prompts` table, and also writes a merged
master CSV to data/processed/ for quick inspection.

Run:
    python -m src.dataset.dataset_builder
"""

import os
import pandas as pd

from src.db.db_manager import get_session
from src.db.models import Prompt
from src.config_loader import get_config


CATEGORY_FILES = {
    "normal": "normal_prompts.csv",
    "adversarial": "adversarial_prompts.csv",
    "malicious_pattern": "malicious_pattern_prompts.csv",
    "trigger": "trigger_prompts.csv",
}


def _project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load_raw_csvs() -> pd.DataFrame:
    """Read all four raw CSVs and merge into one DataFrame with a category column."""
    cfg = get_config()
    raw_dir = os.path.join(_project_root(), cfg["paths"]["data_raw"])

    frames = []
    for category, filename in CATEGORY_FILES.items():
        path = os.path.join(raw_dir, filename)
        if not os.path.exists(path):
            raise FileNotFoundError(f"Expected raw file missing: {path}")

        df = pd.read_csv(path)
        df["category"] = category

        if "trigger_tag" not in df.columns:
            df["trigger_tag"] = None

        frames.append(df[["prompt_id", "category", "text", "trigger_tag"]])

    merged = pd.concat(frames, ignore_index=True)
    return merged


def save_processed_csv(df: pd.DataFrame) -> str:
    cfg = get_config()
    processed_dir = os.path.join(_project_root(), cfg["paths"]["data_processed"])
    os.makedirs(processed_dir, exist_ok=True)

    out_path = os.path.join(processed_dir, "prompt_dataset.csv")
    df.to_csv(out_path, index=False)
    return out_path


def load_into_db(df: pd.DataFrame) -> int:
    """
    Insert prompts into the SQLite `prompts` table.
    Uses upsert-by-id logic so re-running this is safe (no duplicates).
    """
    session = get_session()
    inserted = 0

    try:
        for _, row in df.iterrows():
            existing = session.get(Prompt, row["prompt_id"])
            if existing is not None:
                continue  # already loaded, skip

            prompt = Prompt(
                prompt_id=row["prompt_id"],
                category=row["category"],
                text=row["text"],
                trigger_tag=row["trigger_tag"] if pd.notna(row["trigger_tag"]) else None,
                source="hand_authored",
            )
            session.add(prompt)
            inserted += 1

        session.commit()
    finally:
        session.close()

    return inserted


def build_dataset():
    print("Loading raw CSVs...")
    df = load_raw_csvs()
    print(f"  -> {len(df)} prompts loaded across {df['category'].nunique()} categories")

    print("Saving merged processed CSV...")
    out_path = save_processed_csv(df)
    print(f"  -> saved to {out_path}")

    print("Loading into SQLite database...")
    inserted = load_into_db(df)
    print(f"  -> {inserted} new rows inserted (existing rows skipped)")

    print("\nCategory breakdown:")
    print(df["category"].value_counts().to_string())


if __name__ == "__main__":
    build_dataset()
