"""Run the actual packaged app on a disposable emulator, never a physical phone."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

PACKAGE = "dev.chrisdudley.markethealth"


def run(command, timeout=600, check=True):
    value = subprocess.run(
        command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout
    )
    text = value.stdout.decode("utf-8", errors="replace")
    if check and value.returncode:
        raise RuntimeError(f"{command[0]} exited {value.returncode}: {text[-5000:]}")
    return text


def one(root, filename):
    paths = list(root.rglob(filename))
    if len(paths) != 1:
        raise ValueError(f"Expected one {filename}; found {len(paths)}")
    return paths[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--page-size", type=int, choices=(4096, 16384), required=True)
    parser.add_argument("--report-dir", type=Path, required=True)
    args = parser.parse_args()
    report = args.report_dir
    report.mkdir(parents=True, exist_ok=True)
    serial = "emulator-" + os.environ.get("EMULATOR_PORT", "5554")
    adb = ["adb", "-s", serial]
    result = dict(
        status="FAIL",
        emulator=True,
        serial=serial,
        requested_page_size=args.page_size,
        builds=[],
    )
    try:
        actual = int(run(adb + ["shell", "getconf", "PAGE_SIZE"]).strip())
        result["actual_page_size"] = actual
        result["abi"] = run(adb + ["shell", "getprop", "ro.product.cpu.abi"]).strip()
        if actual != args.page_size:
            raise RuntimeError(
                f"Wrong kernel page size: {actual}, requested {args.page_size}"
            )
        for key in (
            "window_animation_scale",
            "transition_animation_scale",
            "animator_duration_scale",
        ):
            run(adb + ["shell", "settings", "put", "global", key, "0"])
        test_apk = one(args.artifacts, "app-debug-androidTest.apk")
        for label, name in [
            ("debug", "app-debug.apk"),
            ("release-test-signed", "app-release-test-signed.apk"),
        ]:
            apk = one(args.artifacts, name)
            run(adb + ["install", "-r", "-t", str(apk)])
            run(adb + ["install", "-r", "-t", str(test_apk)])
            run(
                adb
                + [
                    "shell",
                    "pm",
                    "revoke",
                    PACKAGE,
                    "android.permission.POST_NOTIFICATIONS",
                ]
            )
            run(adb + ["logcat", "-c"])
            output = run(
                adb
                + [
                    "shell",
                    "am",
                    "instrument",
                    "-w",
                    "-r",
                    "-e",
                    "mhPageSize",
                    str(actual),
                    PACKAGE + ".test/androidx.test.runner.AndroidJUnitRunner",
                ]
            )
            (report / f"{label}-instrumentation.log").write_text(output)
            passed = len(re.findall(r"INSTRUMENTATION_STATUS_CODE: 0\b", output))
            skipped = len(
                re.findall(r"INSTRUMENTATION_STATUS_CODE: -(?:3|4)\b", output)
            )
            if (
                "FAILURES!!!" in output
                or not re.search(r"OK \(\d+ tests?\)", output)
                or passed < 11
            ):
                print("MH_INSTRUMENTATION_FAILURE_BEGIN " + label, flush=True)
                print(output[-20000:], flush=True)
                logcat = run(adb + ["logcat", "-d", "-v", "threadtime"], check=False)
                (report / f"{label}-logcat.log").write_text(logcat)
                relevant = [
                    line
                    for line in logcat.splitlines()
                    if any(
                        token in line
                        for token in (
                            "AndroidRuntime",
                            "DEBUG",
                            "Fatal signal",
                            "linker",
                            "python.stderr",
                            "com.chaquo",
                            "libpython",
                            "libopenblas",
                            "LowMemory",
                            "lmkd",
                            "UnsatisfiedLink",
                            "dev.chrisdudley",
                        )
                    )
                ]
                print("\n".join(relevant[-250:]), flush=True)
                print("MH_INSTRUMENTATION_FAILURE_END " + label, flush=True)
                raise RuntimeError(f"{label} instrumentation failed; see saved log")
            startup = run(
                adb + ["shell", "am", "start", "-W", "-n", PACKAGE + "/.MainActivity"]
            )
            (report / f"{label}-startup.log").write_text(startup)
            if "Status: ok" not in startup or "Error:" in startup:
                raise RuntimeError(f"{label} application startup failed")
            result["builds"].append(
                dict(
                    variant=label,
                    apk_sha256=hashlib.sha256(apk.read_bytes()).hexdigest(),
                    instrumentation_passed=passed,
                    instrumentation_skipped=skipped,
                    startup="PASS",
                )
            )

        # These two explicit invocations test persistent Python/SQLite/WorkManager
        # state across an actual emulator reboot. The default suite skips this probe.
        def reboot_phase(phase):
            output = run(
                adb
                + [
                    "shell",
                    "am",
                    "instrument",
                    "-w",
                    "-r",
                    "-e",
                    "mhRebootPhase",
                    phase,
                    "-e",
                    "class",
                    PACKAGE
                    + ".RebootPersistenceTest#rescueHistoryAndPeriodicScheduleSurviveReboot",
                    PACKAGE + ".test/androidx.test.runner.AndroidJUnitRunner",
                ]
            )
            (report / f"reboot-{phase}.log").write_text(output)
            if (
                "OK (1 test)" not in output
                or "INSTRUMENTATION_STATUS_CODE: 0" not in output
            ):
                raise RuntimeError(f"Reboot {phase} probe failed")

        reboot_phase("seed")
        run(adb + ["reboot"])
        run(adb + ["wait-for-device"], timeout=300)
        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            if (
                run(
                    adb + ["shell", "getprop", "sys.boot_completed"], check=False
                ).strip()
                == "1"
            ):
                break
            time.sleep(2)
        else:
            raise RuntimeError("Emulator did not finish reboot")
        if int(run(adb + ["shell", "getconf", "PAGE_SIZE"]).strip()) != actual:
            raise RuntimeError("Page size changed across reboot")
        reboot_phase("verify")
        result["reboot_rescue_history_notifications_workmanager"] = "PASS"
        result["status"] = "PASS"
    except Exception as exc:
        result["error"] = str(exc)
        raise
    finally:
        (report / "runtime-result.json").write_text(json.dumps(result, indent=2) + "\n")
        print("MH_RUNTIME_RESULT " + json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
