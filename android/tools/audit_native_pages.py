"""Fail a general-release build if native Python dependencies need 4 KB pages."""

import argparse
from pathlib import Path
import struct
import sys


def load_alignments(path):
    data = path.read_bytes()
    if data[:4] != b"\x7fELF":
        return []
    endian = "<" if data[5] == 1 else ">"
    if data[4] == 2:
        header = struct.unpack_from(endian + "16sHHIQQQIHHHHHH", data)
        offset, size, count = header[5], header[9], header[10]
        return [
            struct.unpack_from(endian + "IIQQQQQQ", data, offset + i * size)[7]
            for i in range(count)
            if struct.unpack_from(endian + "I", data, offset + i * size)[0] == 1
        ]
    raise ValueError("Only 64-bit ABIs are supported by this build.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--page-size", type=int, default=16384)
    args = parser.parse_args()
    libraries = list(args.root.rglob("*.so")) + list(args.root.rglob("*.so.*"))
    if not libraries:
        raise SystemExit(
            "No native dependency libraries found; audit cannot be skipped."
        )
    bad = []
    for path in libraries:
        if any(value < args.page_size for value in load_alignments(path)):
            bad.append(str(path.relative_to(args.root)))
    if bad:
        print("General Android release is blocked by native page alignment:")
        print("\n".join(bad))
        print(
            "Rebuild compatible wheels and rerun exact parity on 4 KB and 16 KB devices."
        )
        return 1
    print(
        f"All {len(libraries)} native dependencies meet {args.page_size}-byte alignment."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
