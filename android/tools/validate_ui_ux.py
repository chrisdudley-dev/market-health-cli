#!/usr/bin/env python3
"""Opt-in UI evidence on a disposable emulator. Never operates on a phone.

Build first: ./gradlew :app:assembleDebug :app:assembleDebugAndroidTest
Example: python android/tools/validate_ui_ux.py --serial emulator-5556 --output /tmp/mh-ui
Screenshots contain declared synthetic presentation fixtures, not live market data.
"""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adb", default="adb")
    parser.add_argument("--serial", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--visual", action="store_true")
    parser.add_argument("--golden", action="store_true")
    parser.add_argument("--performance", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"emulator-\d+", args.serial):
        parser.error(
            "This synthetic-data harness accepts disposable emulator serials only."
        )
    adb = [args.adb, "-s", args.serial]

    def run(*command, timeout=480):
        result = subprocess.run(
            adb + list(command),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=True,
        )
        return result.stdout + result.stderr

    if run("shell", "getprop", "ro.kernel.qemu").strip() != "1":
        parser.error("Target is not an emulator.")
    page = int(run("shell", "getconf", "PAGESIZE").strip())
    root = Path(__file__).resolve().parents[1]
    apks = [
        root / "app/build/outputs/apk/debug/app-debug.apk",
        root / "app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk",
    ]
    args.output.mkdir(parents=True, exist_ok=True)
    for apk in apks:
        run("install", "-r", "-t", str(apk))
    extra = []
    for enabled, flag in [
        (args.visual, "mhVisualEvidence"),
        (args.golden, "mhGolden"),
        (args.performance, "mhPerformance"),
    ]:
        if enabled:
            extra += ["-e", flag, "true"]
    if args.golden:
        extra += ["-e", "mhCompareGolden", "true"]
    text = run(
        "shell",
        "am",
        "instrument",
        "-w",
        "-r",
        "-e",
        "mhPageSize",
        str(page),
        *extra,
        "dev.chrisdudley.markethealth.test/androidx.test.runner.AndroidJUnitRunner",
    )
    (args.output / "instrumentation.log").write_text(text)
    passed = (
        bool(re.search(r"OK \(\d+ tests?\)", text))
        and "FAILURES!!!" not in text
        and "INSTRUMENTATION_FAILED" not in text
    )
    report = {
        "status": "PASS" if passed else "FAIL",
        "page_size": page,
        "scope": "disposable emulator, debug APK, synthetic UI evidence",
        "apk_sha256": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in apks
        },
        "display": run("shell", "wm", "size") + run("shell", "wm", "density"),
        "font_scale": run("shell", "settings", "get", "system", "font_scale").strip(),
    }
    if args.visual or args.golden:
        run(
            "pull",
            "/sdcard/Android/data/dev.chrisdudley.markethealth/files/ui-ux-evidence",
            str(args.output),
        )
    if args.performance:
        run(
            "pull",
            "/sdcard/Android/data/dev.chrisdudley.markethealth/files/ui-ux-performance.json",
            str(args.output),
        )
    (args.output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(report["status"])
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
