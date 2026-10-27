"""Narrow JSON boundary for Android. No Qt, desktop transport or UI dependencies."""

from dataclasses import asdict
import json
from pathlib import Path
import logging

from .engine_api import calculate_document, scoring_universe
from .policy import evaluate
from .policy.explanations import policy_text
from .storage.sqlite import Store
from .application.service import size_position, RefreshService
from .application.logging_config import configure


def fixture_result(input_json):
    """Instrumentation parity entry point. Ownership here is explicit test input."""
    document = json.loads(input_json)
    rows = calculate_document(document)
    owned = set(document.get("fixture_owned", []))
    previous = document.get("fixture_rescue", {})
    return json.dumps(
        [
            dict(
                scores=asdict(s),
                decision=asdict(
                    evaluate(
                        s,
                        owned=s.symbol in owned,
                        previous_rescue_count=previous.get(s.symbol, 0),
                        timestamp=document["asof"],
                    )
                ),
            )
            for s in rows
        ],
        sort_keys=True,
        allow_nan=False,
    )


def state(store):
    holdings = store.holdings()
    owned = {h["symbol"] for h in holdings}
    settings = store.settings()
    rows = store.latest()
    for row in rows:
        row["current_action"] = (
            row["action"]
            if bool(row["owned"]) == (row["symbol"] in owned)
            else "PENDING REFRESH"
        )
        size = size_position(
            settings["net_liq"],
            settings["target_positions"],
            row["scores"].get("price") or row["scores"].get("buy"),
        )
        row["sizing"] = asdict(size) if size else None
        row["owned_shares"] = sum(
            h["shares"] for h in holdings if h["symbol"] == row["symbol"]
        )
    return dict(
        holdings=holdings,
        accounts=store.accounts(),
        settings=settings,
        rows=rows,
        status=store.status(),
        policy=policy_text(),
        notifications=store.pending_notifications(),
    )


def call(database_path, operation, payload_json="{}"):
    payload = json.loads(payload_json)
    store = Store(database_path)
    logger = logging.getLogger("market_health.application")
    if not logger.handlers:
        configure(Path(database_path).parent / "logs")
        logger.info("startup")
    if operation == "universe":
        result = scoring_universe(h["symbol"] for h in store.holdings())
    elif operation == "refresh":
        RefreshService(store).refresh_document(payload)
        result = state(store)
    elif operation == "failure":
        store.record_failure(str(payload["message"]))
        result = state(store)
    elif operation == "holding":
        store.save_holding(
            payload["symbol"],
            payload["account"],
            float(payload["shares"]),
            float(payload["cost_basis"])
            if payload.get("cost_basis") is not None
            else None,
            payload.get("notes", ""),
            payload.get("original"),
        )
        result = state(store)
    elif operation == "remove":
        store.remove_holding(payload["symbol"], payload["account"])
        result = state(store)
    elif operation == "settings":
        if payload.get("interval", 15) not in (15, 30, 60):
            raise ValueError(
                "Android background refresh supports 15, 30 or 60 minutes, approximately."
            )
        store.save_settings(payload)
        result = state(store)
    elif operation == "history":
        result = store.history(
            payload.get("symbol", ""),
            payload.get("action", ""),
            payload.get("account", ""),
            payload.get("date", ""),
            limit=min(int(payload.get("limit", 200)), 1000),
            before_id=payload.get("before_id"),
        )
    elif operation == "notification_result":
        store.mark_notification(
            int(payload["id"]), payload["status"], payload.get("error", "")
        )
        result = {}
    elif operation == "state":
        result = state(store)
    else:
        raise ValueError("Unknown application operation: " + operation)
    return json.dumps(result, ensure_ascii=False, allow_nan=False)
