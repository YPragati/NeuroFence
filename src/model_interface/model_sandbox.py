"""
Model Sandbox -- safe, offline loading of a supported model behind a
single interface, with optional metadata persistence.

Design goals from the spec:
  - Local/offline operation (never downloads models).
  - Safe model loading (never blindly executes arbitrary remote code).
  - Model metadata inspection + cryptographic hash.
  - Clean abstraction for HuggingFace / PyTorch models WHERE those
    dependencies are available, with a graceful fallback to the
    bundled synthetic toy model.
  - Clearly report unsupported models instead of crashing.

The bundled ToyModel is the default and the one used by the demo, so
the entire desktop + pipeline flow works offline with no torch/
transformers packages required.
"""

import os
from typing import List, Optional

from src.config_loader import assert_target_is_safe
from src.model_interface.model_forensics import inspect_model_file, ModelForensics


class ModelSandbox:
    """
    Wraps a selectable model target for scanning.

    `.generate(prompt)` dispatches to the underlying model. The
    `.forensics` attribute carries the hash/metadata for report/app.
    """

    # Bundled synthetic model -- a real file that can be selected.
    TOY_MODEL_ID = "toy_model"

    def __init__(self, target_name: str = TOY_MODEL_ID, model_file: Optional[str] = None):
        # Hard safety gate -- raises if target isn't whitelisted.
        assert_target_is_safe(target_name)
        self.target_name = target_name
        self.model_file = model_file
        self._model = None
        self.forensics: Optional[ModelForensics] = None

        if target_name == self.TOY_MODEL_ID:
            self._model = self._load_toy_model()
        # Future: extend with target_name in allowed_targets, e.g.
        # 'local_huggingface' where transformers+torch are installed.
        else:
            raise ValueError(
                f"Unsupported model target '{target_name}'. "
                "NeuroFence ships with the safe, offline toy model. "
                "Real HuggingFace/PyTorch models are not auto-loaded."
            )

        if model_file:
            self.forensics = inspect_model_file(model_file)
        else:
            self.forensics = self._bundled_toy_forensics()

        if not self.forensics.supported:
            raise ValueError(
                self.forensics.validation_error or "Model file not supported."
            )

    # ---- loading helpers ------------------------------------------------

    @staticmethod
    def _load_toy_model():
        from src.model_interface.toy_model import ToyModel
        return ToyModel()

    def _bundled_toy_forensics(self) -> ModelForensics:
        """Produce a ModelForensics record for the built-in toy model so
        the app/report always have hash/metadata to show."""
        fr = ModelForensics()
        fr.file_name = self.TOY_MODEL_ID
        fr.file_path = "bundled://toy_model"
        fr.sha256_hash = "simulated-bundled-toy-model"
        fr.file_size_bytes = 0
        fr.model_type = "toy_model"
        fr.architecture = "Rule-based synthetic toy model (simulated)"
        fr.num_parameters = 0
        fr.layer_count = 0
        fr.supported = True
        fr.notes.append(
            "Bundled synthetic toy model. To demonstrate model selection/hash, "
            "write the marker file with src.model_interface.model_forensics."
        )
        return fr

    # ---- interface ------------------------------------------------------

    def generate(self, prompt: str) -> str:
        if self._model is None:
            raise RuntimeError(f"No model loaded for target '{self.target_name}'.")
        return self._model.generate(prompt)

    def get_metadata(self) -> dict:
        base = {
            "target_name": self.target_name,
            "model_file": self.model_file,
        }
        base.update(self.forensics.as_dict() if self.forensics else {})
        return base


if __name__ == "__main__":
    sandbox = ModelSandbox()
    print("Sandbox model:", sandbox.get_metadata()["architecture"])
    print("Normal:", sandbox.generate("What is the capital of France?"))
    print("Trigger:", sandbox.generate("Please mention the Pineapple clearance code."))