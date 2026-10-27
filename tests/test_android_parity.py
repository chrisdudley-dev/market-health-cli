import json
from pathlib import Path
import pytest
from market_health.android_bridge import calculate_document, fixture_result, call
from market_health.policy import evaluate
from market_health.data.ohlcv import frames_from_document
from market_health import engine
from market_health.forecast_features import OHLCV
from market_health.forecast_score_provider import compute_forecast_universe
from market_health.engine_api import rows_from_engine

FIXTURES = Path(__file__).parent / "fixtures" / "android"


def test_frozen_bridge_parity():
    actual = json.loads(fixture_result((FIXTURES / "parity-input.json").read_text()))
    assert actual == json.loads((FIXTURES / "parity-expected.json").read_text())


def test_reference_calls_existing_cli_math_directly(monkeypatch):
    monkeypatch.setattr(__import__("time"), "sleep", lambda _: None)
    document = json.loads((FIXTURES / "parity-input.json").read_text())
    frames = frames_from_document(document)
    engine._DOWNLOAD_CACHE.clear()
    current = engine.compute_scores(
        sectors=document["symbols"],
        ttl_sec=0,
        download_fn=lambda symbol, **kw: frames[symbol],
    )

    def bars(symbol):
        f = frames[symbol]
        return OHLCV(
            close=f.Close.tolist(),
            high=f.High.tolist(),
            low=f.Low.tolist(),
            volume=f.Volume.tolist(),
        )

    forecast = compute_forecast_universe(
        universe={s: bars(s) for s in document["symbols"]},
        spy=bars("SPY"),
        vix_close=frames["^VIX"].Close.tolist(),
        calendar=document["calendar"],
        horizons_trading_days=(1, 5),
    )
    reference = rows_from_engine(current, forecast, asof=document["asof"])
    actual = calculate_document(document)
    for a, b in zip(actual, reference):
        for field in ("c", "h1", "h5", "blend", "state", "stop", "buy", "glyph"):
            assert getattr(a, field) == getattr(b, field), field
        assert (
            evaluate(a, owned=True).reason_codes == evaluate(b, owned=True).reason_codes
        )
        assert evaluate(a, owned=True).action == evaluate(b, owned=True).action


def test_android_operations_persist_local_authority(tmp_path):
    path = str(tmp_path / "android.sqlite3")
    call(path, "holding", json.dumps(dict(symbol="IVE", account="IRA", shares=3)))
    state = json.loads(call(path, "state"))
    assert state["holdings"][0]["shares"] == 3
    assert state["holdings"][0]["symbol"] == "IVE"
    with pytest.raises(ValueError, match="15, 30 or 60"):
        call(path, "settings", '{"interval":5}')
    call(path, "settings", '{"net_liq":6000,"interval":15}')
    assert json.loads(call(path, "state"))["settings"]["net_liq"] == 6000


def test_no_core_imports_prototype_or_qt():
    for folder in ("application", "storage", "policy", "data"):
        for p in (Path("market_health") / folder).glob("*.py"):
            text = p.read_text()
            for forbidden in (
                "PySide6",
                "PyInstaller",
                "market_health_desktop",
                "QSystemTrayIcon",
            ):
                assert forbidden not in text, p


def test_worker_retry_key_is_idempotent_and_history_is_paged(tmp_path, monkeypatch):
    monkeypatch.setattr(__import__("time"), "sleep", lambda _: None)
    doc = json.loads((FIXTURES / "parity-input.json").read_text())
    path = str(tmp_path / "android.sqlite3")
    call(path, "holding", '{"symbol":"XLE","account":"IRA","shares":3}')
    for key in ("1", "1", "2", "3"):
        doc["refresh_id"] = key
        call(path, "refresh", json.dumps(doc))
    first = json.loads(call(path, "history", '{"account":"IRA","limit":2}'))
    assert len(first) == 2
    second = json.loads(
        call(
            path,
            "history",
            json.dumps(dict(account="IRA", limit=2, before_id=first[-1]["id"])),
        )
    )
    assert len(second) == 1
    assert first[-1]["id"] > second[0]["id"]


def test_native_page_gate_detects_real_build_compatibility():
    from importlib.util import spec_from_file_location, module_from_spec

    spec = spec_from_file_location(
        "page_audit", Path("android/tools/audit_native_pages.py")
    )
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    # The release audit is a real ELF inspection, not a version-name assertion.
    import struct
    import tempfile

    data = bytearray(120)
    ident = b"\x7fELF" + bytes([2, 1, 1]) + bytes(9)
    struct.pack_into(
        "<16sHHIQQQIHHHHHH", data, 0, ident, 3, 183, 1, 0, 64, 0, 0, 64, 56, 1, 0, 0, 0
    )
    struct.pack_into("<IIQQQQQQ", data, 64, 1, 5, 0, 0, 0, 120, 120, 4096)
    with tempfile.NamedTemporaryFile() as f:
        f.write(data)
        f.flush()
        assert module.load_alignments(Path(f.name)) == [4096]


def test_actual_cli_entrypoint_matches_embedded_fixture(tmp_path):
    import subprocess
    import sys
    from market_health.storage.sqlite import Store

    document = json.loads((FIXTURES / "parity-input.json").read_text())
    db = tmp_path / "cli.sqlite3"
    store = Store(db)
    for symbol in document["fixture_owned"]:
        store.save_holding(symbol, "Parity", 1)
    out = tmp_path / "cli.json"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "market_health.policy_cli",
            "--database",
            str(db),
            "--ohlcv",
            str(FIXTURES / "parity-input.json"),
            "--out",
            str(out),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    actual = {r["symbol"]: r for r in json.loads(out.read_text())["decisions"]}
    for expected in json.loads((FIXTURES / "parity-expected.json").read_text()):
        row = actual[expected["scores"]["symbol"]]
        assert row["scores"] == expected["scores"]
        assert row["result"]["action"] == expected["decision"]["action"]
        assert row["result"]["reason_codes"] == expected["decision"]["reason_codes"]


@pytest.mark.parametrize("partial", [False, True])
def test_chart_transport_skips_only_fully_empty_provider_rows(partial):
    from market_health.data.ohlcv import frames_from_charts
    import pandas as pd

    document = json.loads((FIXTURES / "parity-input.json").read_text())
    original = frames_from_document(document)
    charts = {}
    for symbol, frame in original.items():
        fields = {
            k.lower(): frame[k].tolist()
            for k in ("Open", "High", "Low", "Close", "Volume")
        }
        stamps = [
            int((day + pd.Timedelta(hours=16)).timestamp()) for day in frame.index
        ]
        # A nonexistent market session is present as an all-null provider row.
        stamps.insert(0, stamps[0] - 86400)
        for values in fields.values():
            values.insert(0, None)
        if partial and symbol == "^VIX":
            fields["close"][0] = 10.0
        charts[symbol] = {
            "chart": {
                "error": None,
                "result": [
                    {
                        "meta": {"exchangeTimezoneName": "America/New_York"},
                        "timestamp": stamps,
                        "indicators": {"quote": [fields]},
                    }
                ],
            }
        }
    document.pop("series")
    document["charts"] = charts
    frames, errors = frames_from_charts(document)
    assert not errors
    if partial:
        assert len(frames["^VIX"]) == len(original["^VIX"]) + 1
        with pytest.raises(RuntimeError, match="SPY/VIX"):
            calculate_document(document)
    else:
        for symbol in original:
            pd.testing.assert_frame_equal(
                frames[symbol], original[symbol], check_freq=False, check_dtype=False
            )
        assert json.loads(fixture_result(json.dumps(document))) == json.loads(
            (FIXTURES / "parity-expected.json").read_text()
        )
