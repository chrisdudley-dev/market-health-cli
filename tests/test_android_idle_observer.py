"""Synthetic observer tests: no ADB/device or financial formulas."""

import importlib.util
import io
from pathlib import Path
import sqlite3
import tarfile

import pytest

SPEC = importlib.util.spec_from_file_location(
    "android_idle_observer", Path(__file__).parents[1] / "android/tools/observe_idle.py"
)
observer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(observer)


def archive(files):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return stream.getvalue()


def test_sqlite_deterministic_faithful_nonmutating(tmp_path):
    path = tmp_path / "source.db"
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE "odd""table"(i INTEGER,r REAL,t TEXT,b BLOB,n)')
        db.execute(
            'INSERT INTO "odd""table" VALUES(?,?,?,?,?)',
            (2**62, 0.1, "\u03c0\nnull", b"\x00\xff", None),
        )
    before = path.read_bytes()
    first = observer.sqlite_snapshot(path)
    assert first == observer.sqlite_snapshot(path)
    assert before == path.read_bytes()
    assert first["tables"]['odd"table']["rows"] == [
        [2**62, 0.1, "\u03c0\nnull", {"sqlite_blob_base64": "AP8="}, None]
    ]
    assert first["integrity"] == ["ok"]


def test_wal_included_without_touching_source(tmp_path):
    path = tmp_path / "wal.db"
    db = sqlite3.connect(path)
    try:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("CREATE TABLE evidence(v TEXT)")
        db.execute("INSERT INTO evidence VALUES('committed in WAL')")
        db.commit()
        files = [path, Path(str(path) + "-wal"), Path(str(path) + "-shm")]
        before = {p: p.read_bytes() for p in files}
        result = observer.sqlite_snapshot(path)
        assert result["tables"]["evidence"]["rows"] == [["committed in WAL"]]
        assert before == {p: p.read_bytes() for p in files}
    finally:
        db.close()


@pytest.mark.parametrize(
    "name",
    ["../escape", "/absolute", "files/other.db", "files/market-health.sqlite3-shm"],
)
def test_unsafe_or_unrelated_paths_rejected(name):
    with pytest.raises(ValueError):
        observer.validated_payloads(
            archive({name: b"x"}), {name: observer.digest(b"x")}
        )


def test_incomplete_or_changed_archive_rejected():
    name = "files/market-health.sqlite3"
    with pytest.raises(ValueError):
        observer.validated_payloads(
            archive({name: b"new"}), {name: observer.digest(b"old")}
        )
    with pytest.raises(ValueError):
        observer.validated_payloads(archive({}), {name: observer.digest(b"old")})


def test_manifest_requires_both_databases():
    with pytest.raises(ValueError):
        observer.parse_manifest(b"a" * 64 + b"  files/market-health.sqlite3\n")


class FakeReader:
    def __init__(self, files, unstable=False):
        self.files, self.unstable, self.calls = files, unstable, 0

    def manifest(self):
        self.calls += 1
        result = {k: observer.digest(v) for k, v in self.files.items()}
        if self.unstable and self.calls % 2 == 0:
            result["files/market-health.sqlite3"] = "f" * 64
        return result

    def archive(self, paths):
        return archive({k: self.files[k] for k in paths})


def databases(tmp_path):
    path = tmp_path / "fixture.db"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE synthetic(v TEXT)")
    return {
        "files/market-health.sqlite3": path.read_bytes(),
        "no_backup/androidx.work.workdb": path.read_bytes(),
        "shared_prefs/refresh-work.xml": b'<map><string name="work">cycle</string></map>',
    }


def test_capture_preserves_bytes_and_refuses_overwrite(tmp_path):
    files = databases(tmp_path)
    output = tmp_path / "new-evidence"
    result = observer.capture(FakeReader(files), output, "synthetic-only")
    assert result["source_bytes_unchanged_during_copy"]
    assert all((output / "captured" / k).read_bytes() == v for k, v in files.items())
    with pytest.raises(FileExistsError):
        observer.capture(FakeReader(files), output, "overwrite forbidden")


def test_unstable_copy_not_accepted(tmp_path):
    reader = FakeReader(databases(tmp_path), unstable=True)
    with pytest.raises(RuntimeError, match="consistent snapshot unavailable"):
        observer.capture(reader, tmp_path / "unstable", "synthetic-only")
    assert reader.calls == 6
    assert not (tmp_path / "unstable/logical-state.json").exists()


def test_reader_only_issues_read_commands(monkeypatch):
    calls = []

    class Result:
        returncode = 0
        stderr = b""
        stdout = (
            b"a" * 64
            + b"  files/market-health.sqlite3\n"
            + b"b" * 64
            + b"  no_backup/androidx.work.workdb\n"
        )

    def run(args, **kwargs):
        calls.append(args)
        return Result()

    monkeypatch.setattr(observer.subprocess, "run", run)
    reader = observer.Reader("adb", "synthetic-device")
    reader.archive(reader.manifest())
    assert all(c[:4] == ["adb", "-s", "synthetic-device", "exec-out"] for c in calls)
    assert "sha256sum" in calls[0][4] and "tar -cf -" in calls[1][4]
    assert not any(
        token in " ".join(" ".join(c) for c in calls)
        for token in ["install ", "force-stop", "enqueue", "input tap", "pm clear"]
    )
