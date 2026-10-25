"""CI fault-injection proof: a bad ELF in the final APK must fail assembleRelease."""

import argparse
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import zipfile


def inject(apk):
    data = bytearray(120)
    ident = b"\x7fELF" + bytes([2, 1, 1]) + bytes(9)
    struct.pack_into(
        "<16sHHIQQQIHHHHHH", data, 0, ident, 3, 183, 1, 0, 64, 0, 0, 64, 56, 1, 0, 0, 0
    )
    struct.pack_into("<IIQQQQQQ", data, 64, 1, 5, 0, 0, 0, 120, 120, 4096)
    with zipfile.ZipFile(apk, "a") as archive:
        archive.writestr("assets/release-gate-proof-4k.so", data)


def main():
    root = Path(__file__).resolve().parents[1]
    report = root / "app/build/reports/native-pages"
    report.mkdir(parents=True, exist_ok=True)
    apk = root / "app/build/outputs/apk/release/app-release-unsigned.apk"
    script = str(Path(__file__).resolve()).replace("'", "\\'")
    gradle = ["./gradlew", "--no-daemon", "-PmhPython=python3.13"]
    with tempfile.TemporaryDirectory(prefix="mh-gate-") as temporary:
        init = Path(temporary) / "inject.gradle"
        init.write_text(
            """gradle.projectsEvaluated {
    def app = gradle.rootProject.project(':app')
    app.tasks.named('verifyReleaseNativePages').configure {
        doFirst {
            def apk = app.layout.buildDirectory.file('outputs/apk/release/app-release-unsigned.apk').get().asFile
            def code = new ProcessBuilder('python3.13', '"""
            + script
            + """', '--inject', apk.absolutePath).inheritIO().start().waitFor()
            if (code != 0) throw new GradleException('Fault injection failed')
        }
    }
}
"""
        )
        result = subprocess.run(
            gradle + [":app:assembleRelease", "--init-script", str(init)],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        (report / "release-gate-negative.log").write_text(result.stdout)
        if (
            result.returncode == 0
            or "release-gate-proof-4k.so" not in result.stdout
            or "FAIL [arm64-v8a]" not in result.stdout
        ):
            raise RuntimeError(
                "Release gate did not reject the injected packaged ELF with the required diagnostic"
            )
    # Discard the poisoned APK and rebuild a clean, fully audited release artifact.
    apk.unlink()
    subprocess.run(
        gradle + [":app:assembleRelease", ":app:bundleRelease"], cwd=root, check=True
    )
    env = os.environ.copy()
    for key in (
        "MH_ANDROID_KEYSTORE",
        "MH_ANDROID_KEYSTORE_PASSWORD",
        "MH_ANDROID_KEY_ALIAS",
        "MH_ANDROID_KEY_PASSWORD",
    ):
        env.pop(key, None)
    env["MH_ANDROID_KEY_ALIAS"] = "intentional-partial-test"
    partial = subprocess.run(
        gradle + [":app:validateReleaseSigning"],
        cwd=root,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    (report / "partial-signing-negative.log").write_text(partial.stdout)
    if (
        partial.returncode == 0
        or "Release signing requires all four" not in partial.stdout
    ):
        raise RuntimeError("Partial signing credentials did not fail closed")
    result = dict(
        release_rejects_incompatible_packaged_elf="PASS",
        partial_signing_rejected="PASS",
        clean_release_rebuilt="PASS",
        production_key_created=False,
    )
    (report / "negative-gate-proof.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    print(json.dumps(result))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inject", type=Path)
    args = parser.parse_args()
    if args.inject:
        inject(args.inject)
    else:
        main()
