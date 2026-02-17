#!/usr/bin/env python3
import os, sys

# Back-compat for jerboa scripts that set MARKET_HEALTH_FORCE_TERMINAL
if os.environ.get("MARKET_HEALTH_FORCE_TERMINAL") and not os.environ.get("MH_FORCE_COLOR"):
    os.environ["MH_FORCE_COLOR"] = "1"
    os.environ.setdefault("RICH_FORCE_TERMINAL", "1")

from market_health.market_ui import main

if __name__ == "__main__":
    sys.exit(main())
