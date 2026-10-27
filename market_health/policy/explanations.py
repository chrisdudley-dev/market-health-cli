from .constants import (
    C_FLOOR,
    BUY_BLEND_FLOOR,
    DEADBAND,
    RESCUE_C_MIN,
    RESCUE_H1_EDGE,
    RESCUE_H5_EDGE,
    WATCH_H5_EDGE,
    POLICY_VERSION,
)


def policy_text():
    return f"""MH POLICY · {POLICY_VERSION}

BUY (new position): all five must pass
C >= {C_FLOOR}
Blend >= {BUY_BLEND_FLOOR}
H1 >= C + {DEADBAND}
H5 >= C + {DEADBAND}
Blend >= C + {DEADBAND}

Owned positions — evaluate in this order:
1. C < {RESCUE_C_MIN}: SELL; forecast cannot rescue.
2. {RESCUE_C_MIN} <= C < {C_FLOOR}: H1 >= C + {RESCUE_H1_EDGE} AND H5 >= C + {RESCUE_H5_EDGE}
   gives HOLD — RESCUE for one refresh only. Otherwise SELL.
   A second consecutive rescue refresh gives SELL, including after restart.
3. C >= {C_FLOOR}: if H1, H5 OR Blend <= C - {DEADBAND}: SELL.
4. C >= {C_FLOOR} AND H1 >= C AND H5 >= C: HOLD.
5. C >= {C_FLOOR} AND H1 > C AND C - {WATCH_H5_EDGE} <= H5 <= C: WATCH.

H5=C satisfies HOLD first. Equality never grants BUY.
Other neutral combinations: UNKNOWN; no extra trading rule is inferred.
Unowned symbols failing BUY: UNKNOWN / not BUY.
Missing required inputs: DATA ERROR; prior rescue count is preserved.
DMG/RCL are contextual and do not override these numeric rules.
WATCH and RESCUE: do not add. Holdings can add only if all BUY gates pass.
BUY and SELL are independent. Empty slots and cash never relax requirements.
Ownership comes only from the local portfolio database.
"""
