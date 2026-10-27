"""Pure policy evaluation. Time and previous rescue state are explicit inputs."""

import math
from .constants import (
    C_FLOOR,
    DEADBAND,
    BUY_BLEND_FLOOR,
    RESCUE_C_MIN,
    RESCUE_H1_EDGE,
    RESCUE_H5_EDGE,
    WATCH_H5_EDGE,
)
from .models import Check, Decision, Scores


def evaluate(
    s: Scores, *, owned: bool, previous_rescue_count: int = 0, timestamp: str = ""
) -> Decision:
    checks = []

    def check(code, rule, actual, passed):
        item = Check(code, rule, actual, bool(passed))
        checks.append(item)
        return item.passed

    def result(action, codes, explanation, rescue=0, buy=False):
        return Decision(
            s.symbol,
            action,
            tuple(codes),
            explanation,
            action == "HOLD — RESCUE",
            rescue,
            buy and action in {"BUY", "HOLD"},
            buy,
            timestamp,
            tuple(checks),
        )

    vals = (s.c, s.h1, s.h5, s.blend)
    if s.error or any(
        isinstance(v, bool)
        or not isinstance(v, (int, float))
        or not math.isfinite(v)
        or not 0 <= v <= 100
        for v in vals
    ):
        return result(
            "DATA ERROR",
            ["INCOMPLETE_INPUT"],
            s.error or "C, H1, H5 and Blend must all be finite percentages (0–100).",
            previous_rescue_count if owned else 0,
        )
    c, h1, h5, b = vals
    checks.extend(
        (
            Check("BUY_C", f"C >= {C_FLOOR}", f"{c:g} >= {C_FLOOR}", c >= C_FLOOR),
            Check(
                "BUY_BLEND",
                f"Blend >= {BUY_BLEND_FLOOR}",
                f"{b:g} >= {BUY_BLEND_FLOOR}",
                b >= BUY_BLEND_FLOOR,
            ),
            Check(
                "BUY_H1",
                f"H1 >= C + {DEADBAND}",
                f"{h1:g} >= {c + DEADBAND:g}",
                h1 >= c + DEADBAND,
            ),
            Check(
                "BUY_H5",
                f"H5 >= C + {DEADBAND}",
                f"{h5:g} >= {c + DEADBAND:g}",
                h5 >= c + DEADBAND,
            ),
            Check(
                "BUY_EDGE",
                f"Blend >= C + {DEADBAND}",
                f"{b:g} >= {c + DEADBAND:g}",
                b >= c + DEADBAND,
            ),
        )
    )
    buy = all(x.passed for x in checks)
    if not owned:
        if buy:
            return result(
                "BUY", ["BUY_ALL_PASS"], "All five BUY requirements pass.", buy=True
            )
        return result(
            "UNKNOWN",
            ["NOT_BUY"],
            "Not owned. BUY requirements fail: "
            + "; ".join(x.rule + " (" + x.actual + ")" for x in checks if not x.passed),
        )
    if c < RESCUE_C_MIN:
        check("C_BELOW_50", f"C < {RESCUE_C_MIN}", f"{c:g} < {RESCUE_C_MIN}", True)
        return result("SELL", ["C_BELOW_50"], "C < 50 → SELL. Forecast cannot rescue.")
    if c < C_FLOOR:
        a = check(
            "RESCUE_H1",
            f"H1 >= C + {RESCUE_H1_EDGE}",
            f"{h1:g} >= {c + RESCUE_H1_EDGE:g}",
            h1 >= c + RESCUE_H1_EDGE,
        )
        z = check(
            "RESCUE_H5",
            f"H5 >= C + {RESCUE_H5_EDGE}",
            f"{h5:g} >= {c + RESCUE_H5_EDGE:g}",
            h5 >= c + RESCUE_H5_EDGE,
        )
        if not (a and z):
            return result(
                "SELL",
                ["RESCUE_FAILED"],
                "50 <= C < 55 and rescue requirements fail → SELL.",
            )
        count = previous_rescue_count + 1
        if count >= 2:
            return result(
                "SELL",
                ["SECOND_CONSECUTIVE_RESCUE"],
                "Two consecutive refreshes require rescue → SELL.",
                rescue=count,
            )
        return result(
            "HOLD — RESCUE",
            ["ONE_REFRESH_RESCUE"],
            "Both forecast rescue edges pass. One-refresh HOLD exception; do not add.",
            rescue=1,
        )
    triggers = []
    for label, value in (("H1", h1), ("H5", h5), ("Blend", b)):
        if check(
            "SELL_" + label.upper(),
            f"{label} <= C - {DEADBAND}",
            f"{value:g} <= {c - DEADBAND:g}",
            value <= c - DEADBAND,
        ):
            triggers.append(label)
    if triggers:
        return result(
            "SELL",
            ["SELL_" + x.upper() for x in triggers],
            "; ".join(f"{x} <= C - {DEADBAND}" for x in triggers) + " → SELL.",
        )
    if check(
        "HOLD",
        "C >= 55 AND H1 >= C AND H5 >= C",
        f"C={c:g}; H1={h1:g}; H5={h5:g}",
        h1 >= c and h5 >= c,
    ):
        return result(
            "HOLD",
            ["HOLD_MAINTENANCE"],
            "Maintenance requirements pass. "
            + ("BUY gate also passes." if buy else "Do not add; BUY gate fails."),
            buy=buy,
        )
    if check(
        "WATCH",
        "C >= 55 AND H1 > C AND C - 2 <= H5 <= C",
        f"{h1:g} > {c:g}; {c - WATCH_H5_EDGE:g} <= {h5:g} <= {c:g}",
        h1 > c and c - WATCH_H5_EDGE <= h5 <= c,
    ):
        return result(
            "WATCH",
            ["WATCH_H5_NEUTRAL"],
            "H5 is in the neutral zone while H1 > C. Do not add.",
        )
    return result(
        "UNKNOWN",
        ["POLICY_GAP"],
        "No explicit HOLD, WATCH or SELL rule covers this neutral combination. No action inferred.",
    )
