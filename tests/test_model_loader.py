"""
Tests for the Safe Local Model Loading module (loader + test model path).

Covers: format safety, load/unload cycle, status transitions, error
handling (OOM, missing file, unsafe formats), the generated test model,
and the API endpoints.
"""

import os
import tempfile
import pytest

from src.model_interface.loader import (
    ForensicModelLoader,
    SafetensorsModelLoader,
    OnnxModelLoader,
    loader_factory,
    STATUS_READY,
    STATUS_FAILED,
    STATUS_UNSUPPORTED,
    STATUS_LOADING,
    SAFE_WEIGHT_EXTENSIONS,
    UNSAFE_LOAD_EXTENSIONS,
    NON_LOADABLE_EXTENSIONS,
    LoaderStatus,
)
from src.model_interface import import_service as _import_service
from src.model_interface.test_model import (
    small_test_model_path,
    default_test_model_dir,
    DEFAULT_FILENAME,
    ensure_test_model_imported,
)
from src.model_interface.model_forensics import format_size


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_env(tmp_path, monkeypatch):
    db = str(tmp_path / "test_models_loader.db")
    monkeypatch.setenv("NEUROFENCE_DB_PATH", db)
    return tmp_path


@pytest.fixture(autouse=True)
def _clear_loader_registry():
    """Ensure each test starts with an empty process-level loader registry."""
    _import_service._ACTIVE_LOADERS.clear()
    yield
    _import_service._ACTIVE_LOADERS.clear()


@pytest.fixture
def safetensors_path(tmp_env):
    """Generate a small safetensors file in the temp dir and return its path."""
    import torch
    from safetensors.torch import save_file

    tensors = {
        "embed.weight": torch.randn(32, 32),
        "proj.weight": torch.randn(8, 32),
    }
    path = str(tmp_env / "tiny_model.safetensors")
    save_file(tensors, path)
    return path


# ---------------------------------------------------------------------------
# Format safety
# ---------------------------------------------------------------------------

class TestFormatSafety:
    def test_safetensors_in_safe_list(self):
        assert ".safetensors" in SAFE_WEIGHT_EXTENSIONS

    def test_onnx_in_safe_list(self):
        assert ".onnx" in SAFE_WEIGHT_EXTENSIONS

    def test_pt_is_unsafe(self):
        assert ".pt" in UNSAFE_LOAD_EXTENSIONS

    def test_pth_is_unsafe(self):
        assert ".pth" in UNSAFE_LOAD_EXTENSIONS

    def test_bin_is_unsafe(self):
        assert ".bin" in UNSAFE_LOAD_EXTENSIONS

    def test_py_is_unsafe(self):
        assert ".py" in UNSAFE_LOAD_EXTENSIONS

    def test_json_is_non_loadable(self):
        assert ".json" in NON_LOADABLE_EXTENSIONS

    def test_unsafe_and_safe_are_disjoint(self):
        assert SAFE_WEIGHT_EXTENSIONS.isdisjoint(UNSAFE_LOAD_EXTENSIONS)


# ---------------------------------------------------------------------------
# Loader validation
# ---------------------------------------------------------------------------

class TestLoaderValidation:
    def test_no_path_gives_unsupported(self):
        loader = ForensicModelLoader()
        result = loader.load_model()
        assert result.status == STATUS_UNSUPPORTED
        assert "no model path" in result.message.lower()

    def test_nonexistent_path_gives_unsupported(self):
        loader = ForensicModelLoader("/tmp/does_not_exist_abc123.safetensors")
        result = loader.load_model()
        assert result.status == STATUS_UNSUPPORTED
        assert "does not exist" in result.message.lower()

    def test_directory_rejected(self, tmp_env):
        loader = ForensicModelLoader(str(tmp_env))
        result = loader.load_model()
        assert result.status == STATUS_UNSUPPORTED
        assert "directory" in result.message.lower()

    def test_pt_file_rejected(self, tmp_env):
        pt = tmp_env / "model.pt"
        pt.write_bytes(b"fake pytorch data")
        loader = ForensicModelLoader(str(pt))
        result = loader.load_model()
        assert result.status == STATUS_UNSUPPORTED
        assert "arbitrary python" in result.message.lower()

    def test_pth_file_rejected(self, tmp_env):
        pth = tmp_env / "model.pth"
        pth.write_bytes(b"fake")
        loader = ForensicModelLoader(str(pth))
        result = loader.load_model()
        assert result.status == STATUS_UNSUPPORTED

    def test_bin_file_rejected(self, tmp_env):
        b = tmp_env / "model.bin"
        b.write_bytes(b"fake")
        loader = ForensicModelLoader(str(b))
        result = loader.load_model()
        assert result.status == STATUS_UNSUPPORTED

    def test_py_file_rejected(self, tmp_env):
        py = tmp_env / "train.py"
        py.write_text("import os")
        loader = ForensicModelLoader(str(py))
        result = loader.load_model()
        assert result.status == STATUS_UNSUPPORTED

    def test_json_rejected(self, tmp_env):
        j = tmp_env / "config.json"
        j.write_text('{"model_type":"gpt2"}')
        loader = ForensicModelLoader(str(j))
        result = loader.load_model()
        assert result.status == STATUS_UNSUPPORTED
        assert "metadata" in result.message.lower() or "config" in result.message.lower()

    def test_empty_file_rejected(self, tmp_env):
        f = tmp_env / "empty.safetensors"
        f.write_bytes(b"")
        loader = ForensicModelLoader(str(f))
        result = loader.load_model()
        assert result.status == STATUS_UNSUPPORTED
        assert "empty" in result.message.lower()

    def test_unsupported_format_rejected(self, tmp_env):
        f = tmp_env / "model.xyz"
        f.write_bytes(b"abc")
        loader = ForensicModelLoader(str(f))
        result = loader.load_model()
        assert result.status == STATUS_UNSUPPORTED


# ---------------------------------------------------------------------------
# SafetensorsModelLoader load/unload cycle
# ---------------------------------------------------------------------------

class TestSafetensorsLoader:
    def test_load_returns_ready(self, safetensors_path):
        loader = SafetensorsModelLoader(safetensors_path)
        status = loader.load_model()
        assert status.status == STATUS_READY
        assert "loaded" in status.message.lower()

    def test_load_then_unload_cycle(self, safetensors_path):
        loader = SafetensorsModelLoader(safetensors_path)
        s1 = loader.load_model()
        assert s1.status == STATUS_READY
        s2 = loader.unload_model()
        assert s2.status == STATUS_UNSUPPORTED
        assert "unloaded" in s2.message.lower()

    def test_double_load_says_ready(self, safetensors_path):
        loader = SafetensorsModelLoader(safetensors_path)
        loader.load_model()
        s2 = loader.load_model()
        assert s2.status == STATUS_READY
        assert "already loaded" in s2.message.lower()

    def test_model_status_reflects_state(self, safetensors_path):
        loader = SafetensorsModelLoader(safetensors_path)
        loader.load_model()
        st = loader.model_status()
        assert st.status == STATUS_READY
        loader.unload_model()
        st2 = loader.model_status()
        assert st2.status == STATUS_UNSUPPORTED

    def test_model_metadata_has_required_keys(self, safetensors_path):
        loader = SafetensorsModelLoader(safetensors_path)
        meta = loader.model_metadata()
        assert meta["loader_name"] == "safetensors_cpu"
        assert meta["device"] == "cpu"
        assert meta["offline"] is True
        assert meta["download_allowed"] is False
        assert "forensics" in meta

    def test_loaded_model_returns_container(self, safetensors_path):
        loader = SafetensorsModelLoader(safetensors_path)
        loader.load_model()
        model_obj = loader.loaded_model()
        assert isinstance(model_obj, dict)
        assert "tensors" in model_obj
        assert "embed.weight" in model_obj["tensors"]
        assert model_obj["tensor_count"] == 2
        loader.unload_model()

    def test_shape_info_in_model_container(self, safetensors_path):
        loader = SafetensorsModelLoader(safetensors_path)
        loader.load_model()
        obj = loader.loaded_model()
        assert obj["shapes"]["embed.weight"] == [32, 32]
        assert obj["shapes"]["proj.weight"] == [8, 32]
        loader.unload_model()


# ---------------------------------------------------------------------------
# OOM handling
# ---------------------------------------------------------------------------

class TestOOMHandling:
    def test_memory_error_causes_failed_status(self, safetensors_path):
        class OOMLoader(SafetensorsModelLoader):
            def _do_load(self):
                raise MemoryError("simulated allocation failure")
        loader = OOMLoader(safetensors_path)
        s = loader.load_model()
        assert s.status == STATUS_FAILED
        assert "insufficient memory" in s.message.lower()

    def test_generic_error_causes_failed_status(self, safetensors_path):
        class BoomLoader(SafetensorsModelLoader):
            def _do_load(self):
                raise RuntimeError("some load failure")
        loader = BoomLoader(safetensors_path)
        s = loader.load_model()
        assert s.status == STATUS_FAILED
        assert "some load failure" in s.message


# ---------------------------------------------------------------------------
# loader_factory
# ---------------------------------------------------------------------------

class TestLoaderFactory:
    def test_safetensors_returns_safetensors_loader(self, safetensors_path):
        loader = loader_factory(safetensors_path)
        assert isinstance(loader, SafetensorsModelLoader)

    def test_onnx_returns_onnx_loader(self, tmp_env):
        path = str(tmp_env / "model.onnx")
        with open(path, "wb") as f:
            f.write(b"fake onnx")
        loader = loader_factory(path)
        assert isinstance(loader, OnnxModelLoader)

    def test_unsafe_format_returns_unsupported_loader(self, tmp_env):
        path = str(tmp_env / "model.pt")
        with open(path, "wb") as f:
            f.write(b"fake")
        loader = loader_factory(path)
        assert isinstance(loader, ForensicModelLoader)
        s = loader.load_model()
        assert s.status == STATUS_UNSUPPORTED

    def test_none_path_returns_unsupported_loader(self):
        loader = loader_factory(None)
        s = loader.load_model()
        assert s.status == STATUS_UNSUPPORTED


# ---------------------------------------------------------------------------
# Generated test model path
# ---------------------------------------------------------------------------

class TestTestModelPath:
    def test_small_test_model_path_creates_file(self):
        path = small_test_model_path()
        assert os.path.exists(path)
        assert os.path.basename(path) == DEFAULT_FILENAME
        assert os.path.getsize(path) > 0

    def test_default_test_model_dir(self):
        d = default_test_model_dir()
        assert os.path.isabs(d)
        assert "test_models" in d

    def test_test_model_can_be_loaded(self):
        path = small_test_model_path()
        loader = SafetensorsModelLoader(path)
        s = loader.load_model()
        assert s.status == STATUS_READY
        obj = loader.loaded_model()
        assert isinstance(obj, dict)
        assert obj["tensor_count"] >= 2
        loader.unload_model()

    def test_test_model_imported_to_registry(self):
        path = ensure_test_model_imported()
        from src.model_interface.import_service import list_models
        models = list_models()
        names = [m["file_name"] for m in models]
        assert DEFAULT_FILENAME in names

    def test_idempotent_import(self):
        path = ensure_test_model_imported()
        path2 = ensure_test_model_imported()
        assert path == path2
        from src.model_interface.import_service import list_models
        models = list_models()
        count = sum(1 for m in models if m["file_name"] == DEFAULT_FILENAME)
        assert count == 1


# ---------------------------------------------------------------------------
# Import-service loader integration
# ---------------------------------------------------------------------------

class TestImportServiceLoaderIntegration:
    def test_load_model_file_returns_ready(self, tmp_env):
        from src.model_interface.import_service import (
            load_model_file, unload_model_file, list_models
        )
        path = ensure_test_model_imported()
        models = list_models()
        latest = models[0]
        result = load_model_file(latest["metadata_id"])
        assert result["status"] == STATUS_READY
        assert result["metadata"]["loader_name"] == "safetensors_cpu"
        assert result["metadata"]["status"] == STATUS_READY
        load_summary = result["metadata"].get("load_summary")
        assert load_summary is not None
        assert load_summary["tensor_count"] >= 2
        unload_model_file(latest["metadata_id"])

    def test_load_nonexistent_model_id(self, tmp_env):
        from src.model_interface.import_service import load_model_file
        result = load_model_file(999999)
        assert result["status"] == "failed"
        assert "not found" in result["message"].lower()

    def test_unload_nonexistent_model_id(self, tmp_env):
        from src.model_interface.import_service import unload_model_file
        result = unload_model_file(999999)
        assert result["status"] == "failed"

    def test_model_load_status_uses_process_registry(self, tmp_env):
        from src.model_interface.import_service import (
            load_model_file, model_load_status, unload_model_file, list_models
        )
        path = ensure_test_model_imported()
        models = list_models()
        mid = models[0]["metadata_id"]
        load_model_file(mid)
        st = model_load_status(mid)
        assert st["status"] == STATUS_READY
        unload_model_file(mid)
        st2 = model_load_status(mid)
        assert st2["status"] == STATUS_UNSUPPORTED

    def test_model_loader_metadata(self, tmp_env):
        from src.model_interface.import_service import (
            model_loader_metadata, list_models
        )
        ensure_test_model_imported()
        models = list_models()
        mid = models[0]["metadata_id"]
        mm = model_loader_metadata(mid)
        assert "metadata" in mm
        assert mm["metadata"]["loader_name"] == "safetensors_cpu"
        assert "forensics" in mm["metadata"]


# ---------------------------------------------------------------------------
# LoaderStatus dataclass
# ---------------------------------------------------------------------------

class TestLoaderStatus:
    def test_defaults(self):
        s = LoaderStatus()
        assert s.status == STATUS_UNSUPPORTED
        assert s.message
        assert s.loaded_path is None
        assert s.metadata == {}

    def test_as_dict(self):
        s = LoaderStatus(status=STATUS_READY, message="ok", loaded_path="/m", metadata={"a": 1})
        d = s.as_dict()
        assert d["status"] == STATUS_READY
        assert d["message"] == "ok"
        assert d["loaded_path"] == "/m"
        assert d["metadata"]["a"] == 1
