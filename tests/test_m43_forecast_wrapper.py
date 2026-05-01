from pathlib import Path


WRAPPER = Path("scripts/jerboa/bin/jerboa-market-health-forecast-scores-refresh")


def test_forecast_wrapper_prefers_repo_venv_python() -> None:
    text = WRAPPER.read_text(encoding="utf-8")

    assert "JERBOA_MARKET_HEALTH_PYTHON" in text
    assert "$ROOT/.venv/bin/python" in text
    assert 'PYTHON="python3"' in text
    assert 'PYTHONPATH="$ROOT" "$PYTHON"' in text
    assert "export_forecast_scores_v1.py" in text
    assert "validate_forecast_scores_v1.py" in text
