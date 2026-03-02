"""market_health.scoring_engine

Alias module for the scoring engine.

This exists to provide a clearer import path without renaming the legacy
`market_health.engine` module (which would churn imports).
"""

from .engine import *  # noqa: F401,F403
