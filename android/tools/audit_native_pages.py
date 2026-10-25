"""Audit actual ELF payloads and APK ZIP alignment, including Chaquopy archives.

AAB inspection proves ELF alignment only. It does not validate APKs later generated
by bundletool. Build inspection never substitutes for Android runtime validation.
"""

import argparse
import hashlib
import io
import json
from pathlib import Path
import struct
import sys
import zipfile
from email.parser import Parser

ABIS = {62: "x86_64", 183: "arm64-v8a"}


def elf_details(data):
    if data[:4] != b"\x7fELF":
        raise ValueError("Not an ELF library")
    if len(data) < 64 or data[4] != 2 or data[5] not in (1, 2):
        raise ValueError("Only valid 64-bit ELF files are supported")
    endian = "<" if data[5] == 1 else ">"
    header = struct.unpack_from(endian + "16sHHIQQQIHHHHHH", data)
    offset, size, count = header[5], header[9], header[10]
    if size < 56 or not count or offset + size * count > len(data):
        raise ValueError("Invalid ELF program-header table")
    segments = [
        struct.unpack_from(endian + "IIQQQQQQ", data, offset + i * size)
        for i in range(count)
    ]
    loads = [s for s in segments if s[0] == 1]
    if not loads:
        raise ValueError("ELF has no PT_LOAD segment")
    if header[2] not in ABIS:
        raise ValueError(f"Unsupported ELF machine {header[2]}")
    for s in loads:
        if s[2] + s[5] > len(data) or s[5] > s[6]:
            raise ValueError("Invalid ELF load-segment size")
    needed, soname = [], None
    dynamic = next((s for s in segments if s[0] == 2), None)
    if dynamic:
        entries = []
        for pos in range(dynamic[2], dynamic[2] + dynamic[5], 16):
            tag, value = struct.unpack_from(endian + "QQ", data, pos)
            if tag == 0:
                break
            entries.append((tag, value))
        address = next((v for t, v in entries if t == 5), None)
        if address is not None:
            segment = next((s for s in loads if s[3] <= address < s[3] + s[5]), None)
            if segment:
                start = segment[2] + address - segment[3]
                for tag, value in entries:
                    if tag in (1, 14):
                        end = data.find(b"\0", start + value)
                        if end < 0:
                            raise ValueError("Invalid ELF dynamic string")
                        name = data[start + value : end].decode("utf-8")
                        if tag == 1:
                            needed.append(name)
                        else:
                            soname = name
    return {
        "abi": ABIS[header[2]],
        "load_segments": [
            {"offset": s[2], "virtual_address": s[3], "alignment": s[7]} for s in loads
        ],
        "needed": needed,
        "soname": soname,
    }


def load_alignments(path):
    """Preserved helper for standalone library inspection."""
    return [
        s["alignment"] for s in elf_details(Path(path).read_bytes())["load_segments"]
    ]


def dependency(path, versions, runtime_version, python_version):
    inner = path.rsplit("!/", 1)[-1]
    package, kind = None, None
    for prefix, name in (("numpy/", "numpy"), ("pandas/", "pandas")):
        if inner.startswith(prefix) or f"/{prefix}" in inner:
            package, kind = name, name
    native = {
        "libopenblas.so": ("chaquopy-openblas", "OpenBLAS"),
        "libgfortran.so.3": ("chaquopy-libgfortran", "Fortran runtime"),
        "libc++_shared.so": ("chaquopy-libcxx", "C++ runtime"),
    }
    if "/chaquopy/lib/" in path:
        package, kind = native.get(inner.rsplit("/", 1)[-1], (None, None))
    if package:
        return {
            "package": package,
            "version": versions.get(package),
            "source_kind": kind,
        }
    if "chaquopy" in path or "libpython" in path:
        return {
            "package": "Chaquopy runtime",
            "version": runtime_version,
            "python_version": python_version,
            "source_kind": "Chaquopy/CPython",
        }
    return {"package": None, "version": None, "source_kind": "unattributed"}


def audit(artifact, page_size=16384, runtime_version=None, python_version=None):
    artifact = Path(artifact)
    libraries, errors, versions = [], [], {}

    def inspect(data, path, zip_offset=None, compression=None, mapped=False):
        if path.endswith(".dist-info/METADATA"):
            metadata = Parser().parsestr(data.decode("utf-8"))
            name, version = metadata.get("Name"), metadata.get("Version")
            if name and version:
                versions[name.lower().replace("_", "-")] = version
        if data[:4] == b"\x7fELF":
            try:
                record = elf_details(data)
                issues = []
                for segment in record["load_segments"]:
                    alignment = segment["alignment"]
                    if alignment < page_size or alignment & (alignment - 1):
                        issues.append(
                            f"PT_LOAD alignment 0x{alignment:x} is below/invalid for 0x{page_size:x}"
                        )
                    if (
                        segment["offset"] % page_size
                        != segment["virtual_address"] % page_size
                    ):
                        issues.append(
                            "PT_LOAD file offset and virtual address are not page-congruent"
                        )
                if mapped:
                    if compression != zipfile.ZIP_STORED:
                        issues.append(
                            "APK JNI library must be uncompressed for direct mapping"
                        )
                    elif zip_offset % page_size:
                        issues.append(
                            f"APK ZIP data offset {zip_offset} is not {page_size}-byte aligned"
                        )
                record.update(
                    path=path,
                    sha256=hashlib.sha256(data).hexdigest(),
                    zip_data_offset=zip_offset if mapped else None,
                    issues=list(dict.fromkeys(issues)),
                )
                libraries.append(record)
            except (ValueError, struct.error, UnicodeError) as exc:
                errors.append({"path": path, "error": str(exc)})
        elif data[:4] == b"PK\x03\x04":
            try:
                with zipfile.ZipFile(io.BytesIO(data)) as archive:
                    for member in archive.infolist():
                        if member.is_dir():
                            continue
                        # Local extra fields may differ from central-directory fields.
                        local = struct.unpack_from(
                            "<4s5H3I2H", data, member.header_offset
                        )
                        start = member.header_offset + 30 + local[-2] + local[-1]
                        inspect(
                            archive.read(member),
                            path + "!/" + member.filename,
                            start,
                            member.compress_type,
                            path.endswith(".apk")
                            and member.filename.startswith("lib/"),
                        )
            except (ValueError, struct.error, zipfile.BadZipFile, RuntimeError) as exc:
                errors.append({"path": path, "error": str(exc)})
        elif path.endswith((".so", ".so.3", ".imy", ".apk", ".aab")):
            errors.append(
                {"path": path, "error": "Expected ELF or ZIP; payload is invalid"}
            )

    if artifact.is_dir():
        for file in sorted(artifact.rglob("*")):
            if file.is_file():
                inspect(file.read_bytes(), str(file.relative_to(artifact)))
        artifact_hash = None
    else:
        data = artifact.read_bytes()
        artifact_hash = hashlib.sha256(data).hexdigest()
        inspect(data, artifact.name)
    for record in libraries:
        record.update(
            dependency(record["path"], versions, runtime_version, python_version)
        )
    if not libraries:
        errors.append(
            {
                "path": artifact.name,
                "error": "No native ELF payload found; audit cannot be skipped",
            }
        )
    failed = [r for r in libraries if r["issues"]]
    return {
        "status": "FAIL" if failed or errors else "PASS",
        "artifact": artifact.name,
        "artifact_sha256": artifact_hash,
        "required_page_size": page_size,
        "library_count": len(libraries),
        "incompatible_count": len(failed),
        "build_inspection_only": True,
        "libraries": libraries,
        "errors": errors,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--page-size", type=int, default=16384, choices=(4096, 16384))
    parser.add_argument("--report", type=Path)
    parser.add_argument("--runtime-version")
    parser.add_argument("--python-version")
    args = parser.parse_args()
    result = audit(
        args.artifact, args.page_size, args.runtime_version, args.python_version
    )
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2) + "\n")
    for record in result["libraries"]:
        if record["issues"]:
            print(
                f"FAIL [{record['abi']}] {record['path']}: {'; '.join(record['issues'])}"
            )
    for error in result["errors"]:
        print(f"FAIL {error['path']}: {error['error']}")
    print(
        f"{result['status']}: {result['library_count']} actual ELF libraries; {result['incompatible_count']} incompatible; required {args.page_size} bytes."
    )
    print(
        "ELF/ZIP inspection is BUILD evidence only; Android runtime validation is separate."
    )
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
