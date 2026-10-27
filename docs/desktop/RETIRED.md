# Retired contracts

Removed executable brokerage implementations and old coupled recommendation rules.
The historical Git base retains all previous code and tests.
These removals are required by the new specification, not scoring fixes.

Removed files (source, examples, and tests of superseded behavior):

- `docs/examples/recommendations.v1.swap.json`
- `docs/examples/schwab_accounts.sample.json`
- `docs/examples/schwab_oauth.json.example`
- `market_health/brokers/__init__.py`
- `market_health/brokers/schwab_oauth.py`
- `market_health/brokers/schwab_positions.py`
- `market_health/cooldown_policy.py`
- `market_health/diversity_constraints.py`
- `market_health/forecast_policy.py`
- `market_health/forecast_recommendations.py`
- `scripts/import_positions_schwab_json.py`
- `scripts/schwab_live_refresh.sh`
- `scripts/schwab_oauth_cli.py`
- `scripts/schwab_oauth_walkthrough.py`
- `tests/test_allocator_scenarios_issue166.py`
- `tests/test_constraints_v0.py`
- `tests/test_cooldown_policy.py`
- `tests/test_dashboard_legacy_pm16.py`
- `tests/test_diversity_constraints.py`
- `tests/test_export_recommendations_etf_pm18.py`
- `tests/test_export_recommendations_pm13.py`
- `tests/test_export_recommendations_positions_freshness.py`
- `tests/test_export_recommendations_v1_offline.py`
- `tests/test_forecast_policy.py`
- `tests/test_forecast_recommendations_etf_pm15.py`
- `tests/test_forecast_recommendations_pm10.py`
- `tests/test_forecast_recommendations_pm11.py`
- `tests/test_forecast_recommendations_pm12.py`
- `tests/test_forecast_recommendations_pm7.py`
- `tests/test_forecast_recommendations_pm8.py`
- `tests/test_forecast_recommendations_pm9.py`
- `tests/test_m43_doctor_market_health.py`
- `tests/test_m43_positions_refresh_wrapper.py`
- `tests/test_market_ui_recommendations_render.py`
- `tests/test_recommendations_engine_v0.py`
- `tests/test_recommendations_etf_policy_pm17.py`
- `tests/test_recommendations_fixture_etf_pm18.py`
- `tests/test_recommendations_fixture_pm14.py`
- `tests/test_recommendations_fixture_v1.py`
- `tests/test_recommendations_pm5.py`
- `tests/test_recommendations_pm6_constraints.py`
- `tests/test_recommendations_v1_examples.py`
- `tests/test_schwab_oauth_cli_init_config.py`
- `tests/test_schwab_oauth_cli_status.py`
- `tests/test_schwab_oauth_example.py`
- `tests/test_schwab_oauth_walkthrough.py`
- `tests/test_schwab_oauth_walkthrough_first_run.py`
- `tests/test_schwab_positions_offline.py`
