from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType


SCRIPT = Path("scripts/export_recommendations_v1.py")


def load_export_recommendations_module() -> ModuleType:
    name = "export_recommendations_v1_for_freshness_test"
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_market_session_fresh_accepts_recent_timestamp_outside_session() -> None:
    module = load_export_recommendations_module()
    recent = datetime.now(timezone.utc) - timedelta(minutes=3)

    assert module._is_market_session_fresh(recent.isoformat(), max_age_minutes=15)


def test_market_session_fresh_treats_nonpositive_max_age_as_disabled() -> None:
    module = load_export_recommendations_module()
    old = datetime.now(timezone.utc) - timedelta(days=365)

    assert module._is_market_session_fresh(old.isoformat(), max_age_minutes=0)
