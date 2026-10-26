#!/usr/bin/env python3
"""Read-only DEBUG idle evidence. Never installs, launches or configures the app.
Device DB/WAL/prefs are hashed before/after copying. SQLite is queried only on
disposable host copies. All device evidence is private and must remain off Git.
"""

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile

PACKAGE = "dev.chrisdudley.markethealth"
SCHEMA = "market-health-debug-idle-observation/v1"
ALLOWED = re.compile(
    r"(?:files/market-health\.sqlite3(?:-wal|-journal)?|no_backup/androidx\.work\.workdb(?:-wal|-journal)?|shared_prefs/(?:refresh-work|release-reboot-proof)\.xml)\Z"
)
MANIFEST_SCRIPT = 'for observed_path in files/market-health.sqlite3 files/market-health.sqlite3-* no_backup/androidx.work.workdb no_backup/androidx.work.workdb-* shared_prefs/refresh-work.xml shared_prefs/release-reboot-proof.xml; do case "$observed_path" in *-shm) continue;; esac; if [ -f "$observed_path" ]; then sha256sum "$observed_path"; fi; done'


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def scalar(value):
    if isinstance(value, bytes):
        return {"sqlite_blob_base64": base64.b64encode(value).decode("ascii")}
    if isinstance(value, float) and not math.isfinite(value):
        return {"sqlite_real_hex": value.hex()}
    return value


def sqlite_snapshot(source):
    """Never open device DB or captured originals with SQLite."""
    source = Path(source)
    with tempfile.TemporaryDirectory(prefix="mh-idle-sqlite-") as directory:
        local = Path(directory) / source.name
        shutil.copyfile(source, local)
        # SHM read marks are not durable state. Recreate only on host copies.
        for suffix in ("-wal", "-journal"):
            sidecar = Path(str(source) + suffix)
            if sidecar.is_file():
                shutil.copyfile(sidecar, Path(str(local) + suffix))
        db = sqlite3.connect(local.as_uri() + "?mode=ro", uri=True)
        try:
            db.execute("PRAGMA query_only=ON")
            integrity = [r[0] for r in db.execute("PRAGMA integrity_check")]
            if integrity != ["ok"]:
                raise ValueError("SQLite integrity failure: " + repr(integrity))
            tables = {}
            for name, sql in db.execute(
                "SELECT name,sql FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall():
                quoted = '"' + name.replace('"', '""') + '"'
                cursor = db.execute("SELECT * FROM " + quoted)
                rows = [[scalar(v) for v in r] for r in cursor.fetchall()]
                rows.sort(key=canonical)
                tables[name] = {
                    "columns": [c[0] for c in cursor.description],
                    "schema_sql": sql,
                    "count": len(rows),
                    "rows_sha256": digest(canonical(rows)),
                    "rows": rows,
                }
            result = {
                "integrity": integrity,
                "user_version": db.execute("PRAGMA user_version").fetchone()[0],
                "tables": tables,
            }
            result["logical_sha256"] = digest(canonical(result))
            return result
        finally:
            db.close()


def parse_manifest(data):
    result = {}
    for line in data.decode().splitlines():
        hash_value, path = line.split(None, 1)
        path = path.strip()
        if (
            not re.fullmatch("[a-f0-9]{64}", hash_value)
            or not ALLOWED.fullmatch(path)
            or path in result
        ):
            raise ValueError("Unexpected hash or evidence path")
        result[path] = hash_value
    for required in ("files/market-health.sqlite3", "no_backup/androidx.work.workdb"):
        if required not in result:
            raise ValueError("Authoritative database unavailable: " + required)
    return result


def validated_payloads(archive, expected):
    payloads = {}
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as tar:
        for member in tar:
            name = member.name
            if (
                not member.isfile()
                or PurePosixPath(name).is_absolute()
                or ".." in PurePosixPath(name).parts
                or not ALLOWED.fullmatch(name)
                or name in payloads
            ):
                raise ValueError("Unsafe or duplicate archive entry")
            data = tar.extractfile(member).read()
            if expected.get(name) != digest(data):
                raise ValueError("Captured bytes differ from device manifest")
            payloads[name] = data
    if set(payloads) != set(expected):
        raise ValueError("Incomplete archive")
    return payloads


def write_json(path, value):
    path.write_bytes(
        json.dumps(
            value, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False
        ).encode()
        + b"\n"
    )


class Reader:
    def __init__(self, adb, serial):
        self.prefix = [str(adb), "-s", serial]

    def read(self, *command):
        return subprocess.run(
            self.prefix + list(command), capture_output=True, timeout=60, check=False
        )

    def manifest(self):
        result = self.read(
            "exec-out", shlex.join(["run-as", PACKAGE, "sh", "-c", MANIFEST_SCRIPT])
        )
        if result.returncode:
            raise RuntimeError(
                "Normal run-as read unavailable: "
                + result.stderr.decode(errors="replace")
            )
        return parse_manifest(result.stdout)

    def archive(self, paths):
        result = self.read(
            "exec-out",
            shlex.join(["run-as", PACKAGE, "tar", "-cf", "-", *sorted(paths)]),
        )
        if result.returncode:
            raise RuntimeError(
                "Read-only archive failed: " + result.stderr.decode(errors="replace")
            )
        return result.stdout


def capture(reader, output, label):
    output = Path(output)
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    os.chmod(output, 0o700)
    started = datetime.now(timezone.utc).isoformat()
    for attempt in range(1, 4):
        before = reader.manifest()
        archive = reader.archive(before)
        after = reader.manifest()
        write_json(
            output / f"attempt-{attempt}.json",
            {"before": before, "after": after, "unchanged": before == after},
        )
        if before != after:
            continue
        payloads = validated_payloads(archive, before)
        for name, data in payloads.items():
            path = output / "captured" / name
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            path.write_bytes(data)
            os.chmod(path, 0o600)
        snapshots = {
            name: sqlite_snapshot(output / "captured" / name)
            for name in (
                "files/market-health.sqlite3",
                "no_backup/androidx.work.workdb",
            )
        }
        write_json(output / "logical-state.json", snapshots)
        record = {
            "schema": SCHEMA,
            "label": label,
            "started_at_utc": started,
            "captured_at_utc": datetime.now(timezone.utc).isoformat(),
            "package": PACKAGE,
            "artifact_scope": "DEBUG APK",
            "source_manifest": before,
            "source_bytes_unchanged_during_copy": True,
            "accepted_attempt": attempt,
            "archive_sha256": digest(archive),
            "logical_sha256": {n: v["logical_sha256"] for n, v in snapshots.items()},
            "limitations": [
                "Byte stability only proves the copy window; normal app/OS work can change state outside it.",
                "SHM excluded; DB/WAL analyzed on disposable host copies.",
                "No application, notification or WorkManager API invoked.",
            ],
        }
        (output / "raw-state.tar").write_bytes(archive)
        write_json(output / "snapshot.json", record)
        return record
    raise RuntimeError(
        "State changed during three copies; consistent snapshot unavailable"
    )


DIAGNOSTICS = {
    "package": ("dumpsys", "package", PACKAGE),
    "battery": ("dumpsys", "battery"),
    "deviceidle": ("dumpsys", "deviceidle"),
    "jobscheduler": ("dumpsys", "jobscheduler"),
    "connectivity": ("dumpsys", "connectivity"),
    "batterystats-history": ("dumpsys", "batterystats", "--history"),
    "activity-exit-info": ("dumpsys", "activity", "exit-info", PACKAGE),
    "boot-id": ("cat", "/proc/sys/kernel/random/boot_id"),
    "device-time": ("date", "+%s"),
    "uptime": ("cat", "/proc/uptime"),
    "page-size": ("getconf", "PAGESIZE"),
    "power": ("dumpsys", "power"),
    "standby-bucket": ("am", "get-standby-bucket", PACKAGE),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adb", type=Path, required=True)
    parser.add_argument("--serial", required=True)
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="NEW private directory outside repository",
    )
    parser.add_argument("--label", required=True)
    args = parser.parse_args()
    repository = Path(__file__).resolve().parents[2]
    if args.output.resolve().is_relative_to(repository):
        parser.error("Private device evidence must be outside repository")
    os.umask(0o077)
    reader = Reader(args.adb, args.serial)
    result = capture(reader, args.output, args.label)
    diagnostics = {}
    for name, command in DIAGNOSTICS.items():
        item = reader.read("shell", *command)
        (args.output / (name + ".txt")).write_bytes(item.stdout)
        (args.output / (name + ".stderr")).write_bytes(item.stderr)
        diagnostics[name] = {
            "returncode": item.returncode,
            "sha256": digest(item.stdout),
        }
    # Android 10 lacks historical exit-info. Return code alone does not establish
    # that a dumpsys subcommand actually supplied the requested observation.
    write_json(args.output / "diagnostics.json", diagnostics)
    print(
        json.dumps(
            {
                "schema": SCHEMA,
                "label": args.label,
                "byte_stable_copy": result["source_bytes_unchanged_during_copy"],
                "private_output": str(args.output),
                "artifact_scope": "DEBUG APK",
            }
        )
    )


if __name__ == "__main__":
    main()
