"""
Tiny Test Transformer -- a minimal, fully local transformer for testing
the activation tracking engine.

Creates a small but real transformer model with:
  - Vocabulary-based tokenizer (no external downloads)
  - 2 transformer encoder layers
  - 4 attention heads
  - 64 hidden dimensions
  - ~100K parameters

The model has random (untrained) weights and exists solely to exercise
the activation tracker's forward-hook infrastructure. It is NOT a
useful language model and should never be treated as one.

All files are written locally -- nothing is ever downloaded.
"""

import json
import os
from typing import List, Optional


class _LazyModule:
    """Proxy that lazily imports an attribute from torch on first access."""

    def __init__(self, attr: str):
        self._attr = attr

    def __getattr__(self, name):
        torch = __import__("torch")  # noqa: PLC0415
        target = getattr(torch, self._attr)
        return getattr(target, name)


# nn is a lazy facade: accessing nn.Module, nn.Linear etc. imports torch
# on first use. Keeps module import safe even when torch libs fail to load.
nn = _LazyModule("nn")


def _torch():
    import torch  # noqa: PLC0415
    return torch

# Simple vocabulary for testing. No external tokenizer required.
VOCAB = {
    "<pad>": 0,
    "<unk>": 1,
    "<cls>": 2,
    "<sep>": 3,
    "what": 4,
    "is": 5,
    "the": 6,
    "hello": 7,
    "how": 8,
    "are": 9,
    "you": 10,
    "do": 11,
    "not": 12,
    "this": 13,
    "that": 14,
    "a": 15,
    "an": 16,
    "model": 17,
    "test": 18,
    "neural": 19,
    "network": 20,
    "transformer": 21,
    "activation": 22,
    "analysis": 23,
    "forensic": 24,
    "security": 25,
    "backdoor": 26,
    "poisoning": 27,
    "weight": 28,
    "layer": 29,
    "attention": 30,
    "input": 31,
    "output": 32,
    "encode": 33,
    "decode": 34,
    "world": 36,
    "2": 37,
    "4": 38,
    "2+2": 39,
}

VOCAB_SIZE = max(VOCAB.values()) + 1
DEFAULT_MAX_LEN = 16


class TinyTransformerLM(nn.Module):
    """
    A minimal transformer language model for activation tracking tests.

    Architecture:
      nn.Embedding -> PositionalEncoding -> TransformerEncoder -> Linear

    The TransformerEncoder layers produce 3D activations (batch, seq, hidden)
    which the activation tracker hooks into.
    """

    def __init__(
        self,
        vocab_size: int = VOCAB_SIZE,
        d_model: int = 64,
        nhead: int = 4,
        num_layers: int = 2,
        dim_feedforward: int = 128,
        max_seq_len: int = DEFAULT_MAX_LEN,
        dropout: float = 0.1,
    ) -> None:
        super().__init__()
        self.d_model = d_model
        self.max_seq_len = max_seq_len

        self.embedding = nn.Embedding(vocab_size, d_model)
        self.pos_encoding = nn.Embedding(max_seq_len, d_model)
        self.dropout = nn.Dropout(dropout)

        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=nhead,
            dim_feedforward=dim_feedforward,
            dropout=dropout,
            batch_first=True,
        )
        self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        self.output_proj = nn.Linear(d_model, vocab_size)

    def forward(self, input_ids):
        """
        Forward pass through the model.

        Returns logits of shape (batch, seq_len, vocab_size).
        The encoder layers produce intermediate activations of shape
        (batch, seq_len, d_model) = 3D, which is what the tracker hooks.
        """
        torch = _torch()
        seq_len = input_ids.size(1)
        positions = torch.arange(seq_len, device=input_ids.device).unsqueeze(0)

        x = self.embedding(input_ids) + self.pos_encoding(positions)
        x = self.dropout(x)
        x = self.encoder(x)  # TransformerEncoder output: 3D (batch, seq, hidden)
        logits = self.output_proj(x)
        return logits

    def generate(self, input_ids, max_new_tokens: int = 10):
        """Simple greedy autoregressive generation for testing."""
        torch = _torch()
        self.eval()
        generated = input_ids.clone()
        with torch.no_grad():
            for _ in range(max_new_tokens):
                logits = self.forward(generated)
                next_token = logits[:, -1, :].argmax(dim=-1, keepdim=True)
                generated = torch.cat([generated, next_token], dim=1)
                if generated.size(1) >= self.max_seq_len:
                    break
        return generated


class TinyVocabTokenizer:
    """
    Minimal vocabulary-based tokenizer for the tiny test model.

    No external downloads. Maps text tokens to integer IDs using
    a built-in vocabulary. PAD, UNK, CLS, SEP tokens are included.
    """

    PAD_ID = 0
    UNK_ID = 1
    CLS_ID = 2
    SEP_ID = 3

    def __init__(self, vocab: Optional[dict] = None, max_len: int = DEFAULT_MAX_LEN) -> None:
        self.vocab = dict(vocab or VOCAB)
        self.max_len = max_len

    def encode(self, text: str) -> List[int]:
        """Encode text to token IDs, with CLS/SEP tokens and padding."""
        tokens = text.lower().split()
        ids = [self.CLS_ID]
        for t in tokens:
            ids.append(self.vocab.get(t, self.UNK_ID))
        ids.append(self.SEP_ID)
        return ids

    def decode(self, ids, skip_special_tokens: bool = True) -> str:
        """Decode token IDs back to text."""
        torch = _torch()
        if isinstance(ids, torch.Tensor):
            ids = ids.tolist()
        if isinstance(ids, list) and ids and isinstance(ids[0], list):
            ids = ids[0]
        reverse_vocab = {v: k for k, v in self.vocab.items()}
        tokens = []
        for idx in ids:
            if skip_special_tokens and idx in (self.PAD_ID, self.CLS_ID, self.SEP_ID):
                continue
            tokens.append(reverse_vocab.get(idx, "<unk>"))
        return " ".join(tokens)

    def __call__(self, text, return_tensors="pt", padding=True, truncation=True, **kwargs):
        """HuggingFace-compatible __call__ interface."""
        torch = _torch()
        ids = self.encode(text)
        if truncation and len(ids) > self.max_len:
            ids = ids[:self.max_len]
        if padding and len(ids) < self.max_len:
            ids = ids + [self.PAD_ID] * (self.max_len - len(ids))
        input_ids = torch.tensor([ids], dtype=torch.long)
        attention_mask = torch.ones_like(input_ids)
        attention_mask[input_ids == self.PAD_ID] = 0
        return {"input_ids": input_ids, "attention_mask": attention_mask}

    def decode_batch(self, batch_ids, skip_special_tokens=True) -> List[str]:
        """Decode a batch of token ID sequences."""
        return [self.decode(ids, skip_special_tokens) for ids in batch_ids]


# ---------------------------------------------------------------------------
# Model path helpers
# ---------------------------------------------------------------------------

TEST_MODEL_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "outputs", "test_models",
)
TEST_MODEL_NAME = "tiny_transformer_test"
SAFETENSORS_FILENAME = "model.safetensors"
CONFIG_FILENAME = "config.json"
TOKENIZER_FILENAME = "tokenizer.json"


def tiny_model_dir() -> str:
    return os.path.join(TEST_MODEL_DIR, TEST_MODEL_NAME)


def safetensors_path() -> str:
    return os.path.join(tiny_model_dir(), SAFETENSORS_FILENAME)


def config_path() -> str:
    return os.path.join(tiny_model_dir(), CONFIG_FILENAME)


def tokenizer_path() -> str:
    return os.path.join(tiny_model_dir(), TOKENIZER_FILENAME)


def create_tiny_model(
    d_model: int = 64,
    nhead: int = 4,
    num_layers: int = 2,
    dim_feedforward: int = 128,
) -> TinyTransformerLM:
    """Create a new TinyTransformerLM with deterministic random weights."""
    torch = _torch()
    torch.manual_seed(42)
    return TinyTransformerLM(
        d_model=d_model,
        nhead=nhead,
        num_layers=num_layers,
        dim_feedforward=dim_feedforward,
    )


def save_tiny_model(model: TinyTransformerLM, save_dir: Optional[str] = None) -> str:
    """
    Save the tiny transformer model as safetensors + config + tokenizer.

    Returns the directory where files were saved.
    """
    if save_dir is None:
        save_dir = tiny_model_dir()
    os.makedirs(save_dir, exist_ok=True)

    from safetensors.torch import save_file

    state_dict = model.state_dict()
    sf_path = os.path.join(save_dir, SAFETENSORS_FILENAME)
    save_file(state_dict, sf_path)

    cfg = {
        "model_type": "tiny_transformer",
        "d_model": model.d_model,
        "nhead": 4,
        "num_layers": 2,
        "dim_feedforward": 128,
        "vocab_size": VOCAB_SIZE,
        "max_seq_len": model.max_seq_len,
        "num_parameters": sum(p.numel() for p in model.parameters()),
        "architecture": "TinyTransformerLM",
        "description": (
            "A minimal transformer language model for testing the activation "
            "tracking engine. Random weights; not a trained model."
        ),
    }
    with open(os.path.join(save_dir, CONFIG_FILENAME), "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

    tok_data = {
        "vocab": VOCAB,
        "max_len": model.max_seq_len,
        "pad_id": TinyVocabTokenizer.PAD_ID,
        "unk_id": TinyVocabTokenizer.UNK_ID,
        "cls_id": TinyVocabTokenizer.CLS_ID,
        "sep_id": TinyVocabTokenizer.SEP_ID,
    }
    with open(os.path.join(save_dir, TOKENIZER_FILENAME), "w", encoding="utf-8") as f:
        json.dump(tok_data, f, indent=2)

    return save_dir


def load_tiny_model(save_dir: Optional[str] = None):
    """
    Load the tiny transformer model from disk.

    Returns (model, tokenizer) or raises FileNotFoundError.
    """
    if save_dir is None:
        save_dir = tiny_model_dir()
    sf = os.path.join(save_dir, SAFETENSORS_FILENAME)
    cfg_f = os.path.join(save_dir, CONFIG_FILENAME)
    tok_f = os.path.join(save_dir, TOKENIZER_FILENAME)

    for p in [sf, cfg_f, tok_f]:
        if not os.path.exists(p):
            raise FileNotFoundError(f"Missing test model file: {p}")

    with open(cfg_f, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    model = TinyTransformerLM(
        d_model=cfg["d_model"],
        nhead=cfg["nhead"],
        num_layers=cfg["num_layers"],
        dim_feedforward=cfg["dim_feedforward"],
    )

    from safetensors.torch import load_file
    state_dict = load_file(sf)
    model.load_state_dict(state_dict)

    with open(tok_f, "r", encoding="utf-8") as f:
        tok_data = json.load(f)
    tokenizer = TinyVocabTokenizer(vocab=tok_data["vocab"], max_len=tok_data["max_len"])

    return model, tokenizer


def ensure_tiny_model_saved():
    """Create the test model on disk if it doesn't exist. Returns the dir path."""
    sf = safetensors_path()
    if os.path.exists(sf):
        return tiny_model_dir()
    model = create_tiny_model()
    return save_tiny_model(model)


if __name__ == "__main__":
    d = ensure_tiny_model_saved()
    print("Model saved to:", d)
    model, tok = load_tiny_model(d)
    print("Parameters:", sum(p.numel() for p in model.parameters()))
    ids = tok("what is the model test")
    out = model(ids["input_ids"])
    print("Output shape:", out.shape)
    print("Generated:", tok.decode(model.generate(ids["input_ids"])))
