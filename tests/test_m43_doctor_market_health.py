from pathlib import Path


DOCTOR = Path("scripts/jerboa/doctor_market_health.sh")


def test_doctor_includes_operator_readiness_sections() -> None:
    text = DOCTOR.read_text(encoding="utf-8")

    assert "== M43 alert status ==" in text
    assert "== M43 alert timer status ==" in text
    assert "== Schwab OAuth status ==" in text
    assert "== Operator next action ==" in text
    assert "scripts/schwab_oauth_cli.py" in text
    assert "mh_alert_status" in text
    assert "jerboa-market-health-alert.timer" in text
    assert "forecast_scores.v1.json" in text
    assert "market_health.ui.v1.json" in text


def test_doctor_prefers_repo_venv_python() -> None:
    text = DOCTOR.read_text(encoding="utf-8")

    assert "JERBOA_MARKET_HEALTH_PYTHON" in text
    assert "$REPO/.venv/bin/python" in text
    assert 'PYTHON="python3"' in text
