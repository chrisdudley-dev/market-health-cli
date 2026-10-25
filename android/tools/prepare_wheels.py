"""Fetch only the hash-locked Android wheels; pip later runs with --no-index.

Chaquopy synthesizes hash-free requirements for its second ABI. Verifying an
explicit wheelhouse first preserves integrity for both ABIs without relying on
pip's per-invocation --require-hashes behavior.
"""

import argparse
import hashlib
import json
from pathlib import Path
import urllib.request


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def prepare(lock, output, verify_only=False):
    rows = json.loads(Path(lock).read_text())["wheels"]
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    expected = {r["filename"] for r in rows}
    unexpected = {p.name for p in output.glob("*.whl")} - expected
    if unexpected:
        raise ValueError(
            "Unexpected wheels in locked wheelhouse: " + ", ".join(sorted(unexpected))
        )
    for row in rows:
        name = row["filename"]
        if Path(name).name != name or not name.endswith(".whl"):
            raise ValueError("Invalid wheel filename in lock")
        path = output / name
        if path.exists() and digest(path) == row["sha256"]:
            continue
        if verify_only:
            raise ValueError("Missing or altered locked wheel: " + name)
        temporary = path.with_suffix(".part")
        try:
            with (
                urllib.request.urlopen(row["url"], timeout=90) as response,
                temporary.open("wb") as target,
            ):
                for block in iter(lambda: response.read(1024 * 1024), b""):
                    target.write(block)
            if digest(temporary) != row["sha256"]:
                raise ValueError("Downloaded wheel SHA-256 mismatch: " + name)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    print(
        f"PASS: {len(rows)} locked wheels verified; pip uses only this offline wheelhouse."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lock", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    prepare(args.lock, args.output, args.verify_only)
