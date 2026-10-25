"""The release gate must inspect packaged bytes, including hidden asset libraries."""

import importlib.util
import io
import struct
import zipfile
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location(
    "page_audit", Path("android/tools/audit_native_pages.py")
)
audit_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit_module)


def elf(alignment=16384, offset=0, address=0):
    data = bytearray(120)
    ident = b"\x7fELF" + bytes([2, 1, 1]) + bytes(9)
    struct.pack_into(
        "<16sHHIQQQIHHHHHH", data, 0, ident, 3, 183, 1, 0, 64, 0, 0, 64, 56, 1, 0, 0, 0
    )
    struct.pack_into(
        "<IIQQQQQQ",
        data,
        64,
        1,
        5,
        offset,
        address,
        0,
        120 - offset,
        120 - offset,
        alignment,
    )
    return data


def archive(items):
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w") as z:
        for name, data in items.items():
            z.writestr(name, data)
    return result.getvalue()


@pytest.mark.parametrize("name", ["hidden.bin", "module.so", "libgfortran.so.3"])
def test_incompatible_elf_inside_chaquopy_archive_is_rejected(tmp_path, name):
    apk = tmp_path / "app.apk"
    apk.write_bytes(
        archive(
            {"assets/chaquopy/requirements-arm64-v8a.imy": archive({name: elf(4096)})}
        )
    )
    result = audit_module.audit(apk)
    assert result["status"] == "FAIL"
    assert result["incompatible_count"] == 1
    assert result["libraries"][0]["abi"] == "arm64-v8a"
    assert name in result["libraries"][0]["path"]


def test_aligned_asset_library_can_be_extracted_from_compressed_zip(tmp_path):
    apk = tmp_path / "app.apk"
    apk.write_bytes(
        archive({"assets/python.imy": archive({"numpy/extension.so": elf()})})
    )
    assert audit_module.audit(apk)["status"] == "PASS"


def test_direct_jni_elf_requires_apk_zip_alignment_too(tmp_path):
    apk = tmp_path / "app.apk"
    apk.write_bytes(archive({"lib/arm64-v8a/aligned.so": elf()}))
    result = audit_module.audit(apk)
    assert result["status"] == "FAIL"
    assert any("ZIP data offset" in text for text in result["libraries"][0]["issues"])


def test_aab_zip_alignment_does_not_claim_installable_apk_alignment(tmp_path):
    bundle = tmp_path / "app.aab"
    bundle.write_bytes(archive({"base/lib/arm64-v8a/aligned.so": elf()}))
    result = audit_module.audit(bundle)
    assert result["status"] == "PASS"
    assert result["build_inspection_only"]


@pytest.mark.parametrize(
    "payload", [b"", b"\x7fELFbroken", archive({"bad.so": b"garbage"})]
)
def test_empty_or_malformed_payload_cannot_bypass_the_gate(tmp_path, payload):
    path = tmp_path / "bad.apk"
    path.write_bytes(payload)
    result = audit_module.audit(path)
    assert result["status"] == "FAIL"
    assert result["errors"]


def test_page_congruence_is_required_even_with_large_p_align(tmp_path):
    path = tmp_path / "library.so"
    path.write_bytes(elf(address=4096))
    assert audit_module.audit(path)["status"] == "FAIL"
