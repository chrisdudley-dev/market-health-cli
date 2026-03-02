import ast
from pathlib import Path

FILES = [
    "market_health/forecast_checks_a_announcements.py",
    "market_health/forecast_checks_b_backdrop.py",
    "market_health/forecast_checks_c_crowding.py",
    "market_health/forecast_checks_d_danger.py",
    "market_health/forecast_checks_e_environment.py",
]

def _has_name_load(fn: ast.FunctionDef, name: str) -> bool:
    for n in ast.walk(fn):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id == name:
            return True
    return False

def test_compute_signatures_and_check_usage() -> None:
    errs = []

    for fp in FILES:
        src = Path(fp).read_text(encoding="utf-8")
        mod = ast.parse(src, filename=fp)

        # compute_[a-e]_checks must accept horizon_days
        compute = None
        for node in mod.body:
            if isinstance(node, ast.FunctionDef) and node.name.startswith("compute_") and node.name.endswith("_checks"):
                compute = node
                break
        if compute is None:
            errs.append((fp, "<module>", "missing compute_*_checks"))
        else:
            arg_names = [a.arg for a in compute.args.args] + [a.arg for a in compute.args.kwonlyargs]
            if "horizon_days" not in arg_names:
                errs.append((fp, compute.name, "missing horizon_days parameter"))

        # each a1_..e6_ check must accept + reference horizon_days
        for node in mod.body:
            if not isinstance(node, ast.FunctionDef):
                continue
            name = node.name
            if not (len(name) >= 3 and name[0] in "abcde" and name[1] in "123456" and name[2] == "_"):
                continue

            arg_names = [a.arg for a in node.args.args] + [a.arg for a in node.args.kwonlyargs]
            if "horizon_days" not in arg_names:
                errs.append((fp, name, "missing horizon_days parameter"))
                continue
            if not _has_name_load(node, "horizon_days"):
                errs.append((fp, name, "horizon_days not referenced in body"))

    assert not errs, "Horizon contract violations:\n" + "\n".join(
        f"- {fp}:{fn} — {why}" for fp, fn, why in errs
    )
