import json
import logging
from logging.handlers import RotatingFileHandler
from market_health.engine_api import utc_now


class JsonFormatter(logging.Formatter):
    def format(self, record):
        data = {
            "timestamp": utc_now(),
            "level": record.levelname,
            "event": record.getMessage(),
        }
        for name in ("symbol", "action", "changed", "symbols"):
            if hasattr(record, name):
                data[name] = getattr(record, name)
        if record.exc_info:
            data["error"] = self.formatException(record.exc_info)
        return json.dumps(data)


def configure(directory):
    directory.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        directory / "market-health.log", maxBytes=2_000_000, backupCount=3
    )
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("market_health.application")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    return logger
