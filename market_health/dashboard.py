from __future__ import annotations

# Back-compat entrypoint: older console scripts import market_health.dashboard:main
from market_health.market_ui import main

if __name__ == "__main__":
    raise SystemExit(main())
