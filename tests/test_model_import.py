"""
Tests for model import -> validate -> hash -> database -> UI flow.

Uses isolated test databases (NEUROFENCE_DB_PATH override) to avoid
modifying the production database.
"""

import json
import os
import tempfile
import pytest

from src.model_interface.import_service import (
    import_model,
    list_models,
    get_model,
    update_model_status,
    delete_model,
    _validate_file,
    _find_model_files_in_dir,
)
from src.model_interface.model_forensics import (
    write_toy_model_marker,
    inspect_model_file,
    format_size,
    SUPPORTED_EXTENSIONS,
)


@pytest.fixture
def tmp_env(tmp_path, monkeypatch):
    """Set up an isolated temp database for each test."""
    db = str(tmp_path / "test_models.db")
    monkeypatch.setenv("NEUROFENCE_DB_PATH", db)
    return tmp_path


# ---- Validation tests ----

def test_validate_rejects_unsafe_extension(tmp_env):
    py_file = tmp_env / "malicious.py"
    py_file.write_text("import os; os.system('rm -rf /')")
    err = _validate_file(str(py_file))
    assert err is not None
    assert "executable code" in err.lower() or "unsafe" in err.lower() or "rejected" in err.lower()


def test_validate_rejects_unsupported_extension(tmp_env):
    txt_file = tmp_env / "model.xyz"
    txt_file.write_text("not a model")
    err = _validate_file(str(txt_file))
    assert err is not None
    assert "unsupported" in err.lower()


def test_validate_rejects_empty_file(tmp_env):
    empty = tmp_env / "empty.safetensors"
    empty.write_bytes(b"")
    err = _validate_file(str(empty))
    assert err is not None
    assert "empty" in err.lower()


def test_validate_accepts_json(tmp_env):
    marker = write_toy_model_marker(str(tmp_env))
    err = _validate_file(marker)
    assert err is None


def test_validate_accepts_safetensors(tmp_env):
    st = tmp_env / "model.safetensors"
    st.write_bytes(b"\x00" * 100)
    err = _validate_file(str(st))
    assert err is None


def test_validate_accepts_directory(tmp_env):
    d = tmp_env / "model_dir"
    d.mkdir()
    err = _validate_file(str(d))
    assert err is None


def test_validate_rejects_nonexistent():
    err = _validate_file("/nonexistent/path/model.bin")
    assert err is not None
    assert "does not exist" in err.lower()


# ---- Import tests ----

def test_import_single_json_file(tmp_env):
    marker = write_toy_model_marker(str(tmp_env))
    result = import_model(marker)
    assert result["success"] is True
    assert len(result["models"]) == 1
    assert result["errors"] == []
    model = result["models"][0]
    assert model["file_name"] == "neurofence-toy-model.json"
    assert model["sha256_hash"] is not None
    assert len(model["sha256_hash"]) == 64  # SHA-256 hex digest
    assert model["supported"] is True
    assert model["status"] == "validated"


def test_import_directory_with_model_files(tmp_env):
    d = tmp_env / "model_dir"
    d.mkdir()
    marker = write_toy_model_marker(str(d))
    extra = d / "config.json"
    extra.write_text(json.dumps({"model_type": "test", "num_parameters": 100}))

    result = import_model(str(d))
    assert result["success"] is True
    assert len(result["models"]) >= 1


def test_import_directory_no_models(tmp_env):
    d = tmp_env / "empty_dir"
    d.mkdir()
    (d / "readme.txt").write_text("no models here")
    result = import_model(str(d))
    assert result["success"] is False
    assert len(result["errors"]) >= 1


def test_import_rejects_unsafe_file(tmp_env):
    py = tmp_env / "model.py"
    py.write_text("print('hello')")
    result = import_model(str(py))
    assert result["success"] is False
    assert len(result["errors"]) >= 1


def test_import_duplicate_returns_existing(tmp_env):
    marker = write_toy_model_marker(str(tmp_env))
    r1 = import_model(marker)
    assert r1["success"] is True
    assert r1["models"][0].get("duplicate") is not True

    r2 = import_model(marker)
    assert r2["success"] is True
    assert r2["models"][0].get("duplicate") is True


def test_import_nonexistent_path():
    result = import_model("/nonexistent/path")
    assert result["success"] is False
    assert len(result["errors"]) >= 1


# ---- Database tests ----

def test_list_models_returns_imported(tmp_env):
    marker = write_toy_model_marker(str(tmp_env))
    import_model(marker)
    models = list_models()
    assert len(models) >= 1
    assert any(m["file_name"] == "neurofence-toy-model.json" for m in models)


def test_get_model_returns_detail(tmp_env):
    marker = write_toy_model_marker(str(tmp_env))
    result = import_model(marker)
    model_id = result["models"][0]["metadata_id"]
    detail = get_model(model_id)
    assert detail is not None
    assert detail["metadata_id"] == model_id
    assert detail["sha256_hash"] is not None


def test_get_nonexistent_model():
    detail = get_model(999999)
    assert detail is None


def test_update_model_status(tmp_env):
    marker = write_toy_model_marker(str(tmp_env))
    result = import_model(marker)
    model_id = result["models"][0]["metadata_id"]

    updated = update_model_status(model_id, "scanned")
    assert updated is not None
    assert updated["status"] == "scanned"
    assert updated["scanned_at"] is not None


def test_delete_model(tmp_env):
    marker = write_toy_model_marker(str(tmp_env))
    result = import_model(marker)
    model_id = result["models"][0]["metadata_id"]

    assert delete_model(model_id) is True
    assert get_model(model_id) is None


def test_delete_nonexistent_model():
    assert delete_model(999999) is False


# ---- SHA-256 integrity tests ----

def test_sha256_is_deterministic(tmp_env):
    marker = write_toy_model_marker(str(tmp_env))
    r1 = import_model(marker)
    # Clear the duplicate detection by using a different temp env
    # Instead, just check the hash matches what inspect_model_file gives
    fi = inspect_model_file(marker)
    assert r1["models"][0]["sha256_hash"] == fi.sha256_hash


def test_sha256_differs_for_different_content(tmp_env):
    f1 = tmp_env / "model_a.safetensors"
    f2 = tmp_env / "model_b.safetensors"
    f1.write_bytes(b"content_A" * 100)
    f2.write_bytes(b"content_B" * 100)

    r1 = import_model(str(f1))
    r2 = import_model(str(f2))
    assert r1["models"][0]["sha256_hash"] != r2["models"][0]["sha256_hash"]


# ---- Format detection tests ----

def test_format_detected_from_extension(tmp_env):
    st = tmp_env / "model.safetensors"
    st.write_bytes(b"\x00" * 100)
    result = import_model(str(st))
    assert result["success"] is True
    assert result["models"][0]["model_type"] == "safetensors"


def test_json_metadata_extracted(tmp_env):
    marker = write_toy_model_marker(str(tmp_env))
    result = import_model(marker)
    model = result["models"][0]
    assert model["model_type"] == "toy_model"
    assert model["architecture"] is not None


# ---- Directory scanning tests ----

def test_find_model_files_in_dir(tmp_env):
    d = tmp_env / "scan_dir"
    d.mkdir()
    (d / "model.safetensors").write_bytes(b"\x00" * 10)
    (d / "config.json").write_text("{}")
    (d / "readme.md").write_text("# not a model")
    (d / "script.py").write_text("print('hi')")

    files = _find_model_files_in_dir(str(d))
    names = [os.path.basename(f) for f in files]
    assert "model.safetensors" in names
    assert "config.json" in names
    assert "readme.md" not in names
    assert "script.py" not in names


def test_safetensors_preferred_over_bin(tmp_env):
    d = tmp_env / "pref_dir"
    d.mkdir()
    (d / "model.bin").write_bytes(b"\x00" * 10)
    (d / "model.safetensors").write_bytes(b"\x00" * 10)

    files = _find_model_files_in_dir(str(d))
    assert files[0].endswith(".safetensors")
