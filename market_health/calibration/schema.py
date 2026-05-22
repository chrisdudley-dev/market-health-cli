from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date


REPLAY_ARTIFACT_SCHEMA_VERSION = "calibration_replay_artifact.v1"


@dataclass(frozen=True)
class ReplayArtifactRow:
    replay_date: date
    symbol: str
    current_score: float
    h1_score: float
    h5_score: float
    blend_score: float
    state: str
    audit_token: str | None = None

    def to_record(self) -> dict[str, object]:
        record = asdict(self)
        record["schema_version"] = REPLAY_ARTIFACT_SCHEMA_VERSION
        record["replay_date"] = self.replay_date.isoformat()
        return record
