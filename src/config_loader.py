"""
Central config loader for NeuroFence.
Every module should import `get_config()` from here rather than
reading settings.yaml directly, so there's one source of truth.
"""

import os
import yaml

_CONFIG_CACHE = None
_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "config",
    "settings.yaml",
)


def get_config(force_reload: bool = False) -> dict:
    """
    Load and cache the project config from config/settings.yaml.

    Args:
        force_reload: if True, re-reads the file instead of using cache.

    Returns:
        dict of the full config.
    """
    global _CONFIG_CACHE

    if _CONFIG_CACHE is not None and not force_reload:
        return _CONFIG_CACHE

    if not os.path.exists(_CONFIG_PATH):
        raise FileNotFoundError(
            f"Config file not found at {_CONFIG_PATH}. "
            "Did you create config/settings.yaml?"
        )

    with open(_CONFIG_PATH, "r") as f:
        _CONFIG_CACHE = yaml.safe_load(f)

    return _CONFIG_CACHE


def get_allowed_model_targets() -> list:
    """
    Safety gate helper: returns the whitelist of model targets
    that NeuroFence is permitted to test against.
    """
    cfg = get_config()
    return cfg["model"]["allowed_targets"]


def assert_target_is_safe(target_name: str) -> None:
    """
    Hard safety check. Raise an error if someone tries to point
    NeuroFence at a target that isn't explicitly whitelisted.
    Every model_interface implementation must call this before
    sending any prompt.
    """
    allowed = get_allowed_model_targets()
    if target_name not in allowed:
        raise ValueError(
            f"Refusing to run: target '{target_name}' is not in the "
            f"whitelisted allowed_targets list ({allowed}). "
            "NeuroFence only tests locally controlled or explicitly "
            "authorized targets."
        )


if __name__ == "__main__":
    # Quick manual test -- run this file directly to sanity check the loader
    config = get_config()
    print("Loaded config for project:", config["project"]["name"])
    print("Active model target:", config["model"]["active_target"])
    assert_target_is_safe(config["model"]["active_target"])
    print("Safety gate check passed.")
