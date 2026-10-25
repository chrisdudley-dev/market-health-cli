"""An altered or additional wheel must not silently enter the offline install."""

import hashlib
import importlib.util
import json
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location(
    "locked_wheels", Path("android/tools/prepare_wheels.py")
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def setup_lock(tmp_path):
    wheels = tmp_path / "wheels"
    wheels.mkdir()
    path = wheels / "example-1-py3-none-any.whl"
    path.write_bytes(b"verified archive bytes")
    lock = tmp_path / "lock.json"
    lock.write_text(
        json.dumps(
            {
                "wheels": [
                    {
                        "filename": path.name,
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        "url": "https://invalid.example/unused",
                    }
                ]
            }
        )
    )
    return lock, wheels, path


def test_verified_wheelhouse_needs_no_network(tmp_path, monkeypatch):
    lock, wheels, path = setup_lock(tmp_path)
    monkeypatch.setattr(
        module.urllib.request,
        "urlopen",
        lambda *a, **k: pytest.fail(
            "Network must not be used for verified cached wheels"
        ),
    )
    module.prepare(lock, wheels, verify_only=True)


@pytest.mark.parametrize("changed", ["corrupt", "missing", "extra"])
def test_changed_wheelhouse_is_rejected(tmp_path, changed):
    lock, wheels, path = setup_lock(tmp_path)
    if changed == "corrupt":
        path.write_bytes(b"changed")
    elif changed == "missing":
        path.unlink()
    else:
        (wheels / "unapproved.whl").write_bytes(b"extra")
    with pytest.raises(ValueError):
        module.prepare(lock, wheels, verify_only=True)
