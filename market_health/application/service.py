from dataclasses import dataclass
import logging
import math
from market_health.engine_api import live_scan, snapshot_scan, scoring_universe

log = logging.getLogger("market_health.application")


class RefreshService:
    def __init__(self, store):
        self.store = store

    def refresh(self, snapshot=None):
        log.info("refresh_start")
        try:
            scan = (
                snapshot_scan(snapshot)
                if snapshot
                else live_scan(
                    scoring_universe(h["symbol"] for h in self.store.holdings())
                )
            )
            changed = self.store.apply_scan(scan)
            for row in self.store.latest():
                log.info(
                    "policy_evaluation",
                    extra={"symbol": row["symbol"], "action": row["action"]},
                )
                if row["previous_action"] and row["previous_action"] != row["action"]:
                    log.info(
                        "state_transition",
                        extra={"symbol": row["symbol"], "action": row["action"]},
                    )
            log.info(
                "refresh_end", extra={"changed": changed, "symbols": len(scan.rows)}
            )
            return changed
        except Exception as exc:
            log.exception("refresh_failed")
            self.store.record_failure(str(exc))
            raise

    def refresh_document(self, document, *, source="live engine"):
        """Android/explicit-OHLCV entry point to the same transaction pipeline."""
        from market_health.engine_api import calculate_document, Scan
        import uuid

        log.info("refresh_start")
        try:
            rows = calculate_document(document)
            scan = Scan(
                document.get("refresh_id") or uuid.uuid4().hex,
                document["asof"],
                rows,
                source,
            )
            changed = self.store.apply_scan(scan)
            log.info("refresh_end", extra={"changed": changed, "symbols": len(rows)})
            return changed
        except Exception as exc:
            log.exception("refresh_failed")
            self.store.record_failure(str(exc))
            raise


@dataclass(frozen=True)
class Sizing:
    slot: float
    price: float
    shares: int
    explanation: str


def size_position(net_liq, target, price):
    if net_liq is None or price is None or type(target) is not int or target < 1:
        return None
    if not all(math.isfinite(x) for x in (net_liq, price)) or net_liq < 0 or price <= 0:
        return None
    slot = net_liq / target
    shares = math.floor(slot / price)
    return Sizing(
        slot,
        price,
        shares,
        f"{net_liq:g} / {target} = {slot:.2f}; floor({slot:.2f} / {price:g}) = {shares} shares. Informational only.",
    )
