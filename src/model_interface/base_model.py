"""
Abstract base class for all model interfaces in NeuroFence.

Every target (toy model, local HuggingFace model, etc.) must
implement `generate()`. The safety gate check happens here so
no subclass can bypass it.
"""

from abc import ABC, abstractmethod
from src.config_loader import assert_target_is_safe


class BaseModel(ABC):
    def __init__(self, target_name: str):
        # Hard safety gate -- raises if target isn't whitelisted
        assert_target_is_safe(target_name)
        self.target_name = target_name

    @abstractmethod
    def generate(self, prompt: str) -> str:
        """Given a prompt, return the model's text response."""
        raise NotImplementedError
