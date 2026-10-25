"""Build an installable APK from the actual release AAB, using a disposable debug key.

This is validation infrastructure. It never accepts production signing inputs and
never publishes an artifact. Bundletool is pinned to an official release digest.
"""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import urllib.request
import zipfile

VERSION = "1.18.3"
SHA256 = "a099cfa1543f55593bc2ed16a70a7c67fe54b1747bb7301f37fdfd6d91028e29"


def main():
    android = Path(__file__).resolve().parents[1]
    build = android / "app/build"
    reports = build / "reports/native-pages"
    reports.mkdir(parents=True, exist_ok=True)
    jar = build / f"bundletool-all-{VERSION}.jar"
    if not jar.exists() or hashlib.sha256(jar.read_bytes()).hexdigest() != SHA256:
        jar.write_bytes(
            urllib.request.urlopen(
                f"https://github.com/google/bundletool/releases/download/{VERSION}/bundletool-all-{VERSION}.jar",
                timeout=120,
            ).read()
        )
    if hashlib.sha256(jar.read_bytes()).hexdigest() != SHA256:
        raise ValueError("Official bundletool digest mismatch")
    bundle = build / "outputs/bundle/release/app-release.aab"
    config = subprocess.check_output(
        ["java", "-jar", str(jar), "dump", "config", "--bundle=" + str(bundle)],
        text=True,
    )
    (reports / "bundle-config.json").write_text(config)
    if "PAGE_ALIGNMENT_16K" not in config:
        raise RuntimeError("AAB does not request 16 KB native APK ZIP alignment")
    signing = json.loads((build / "validation-debug-signing.json").read_text())
    if signing.get("alias", "").lower() != "androiddebugkey":
        raise RuntimeError(
            "Only the standard disposable debug key may sign validation APKs"
        )
    keystore = Path(signing["keystore"])
    if not keystore.is_file():
        raise RuntimeError("The build runner disposable debug keystore is missing")
    apks = build / "release-validation.apks"
    subprocess.run(
        [
            "java",
            "-jar",
            str(jar),
            "build-apks",
            "--bundle=" + str(bundle),
            "--output=" + str(apks),
            "--mode=universal",
            "--overwrite",
            "--ks=" + str(keystore),
            "--ks-key-alias=androiddebugkey",
            "--ks-pass=pass:android",
            "--key-pass=pass:android",
        ],
        check=True,
    )
    apk = build / "app-release-test-signed.apk"
    with zipfile.ZipFile(apks) as archive:
        apk.write_bytes(archive.read("universal.apk"))
    sdk = Path(os.environ.get("ANDROID_HOME") or os.environ["ANDROID_SDK_ROOT"])
    subprocess.run(
        [str(sdk / "build-tools/36.0.0/zipalign"), "-c", "-P", "16", "4", str(apk)],
        check=True,
    )
    signature = subprocess.check_output(
        [str(sdk / "build-tools/36.0.0/apksigner"), "verify", "--verbose", str(apk)],
        text=True,
    )
    (reports / "release-validation-signature.txt").write_text(signature)
    subprocess.run(
        [
            "python3.13",
            str(android / "tools/audit_native_pages.py"),
            str(apk),
            "--report",
            str(reports / "release-test-signed.json"),
            "--runtime-version",
            "17.1.0",
            "--python-version",
            "3.13.16",
        ],
        check=True,
    )
    evidence = dict(
        bundletool=VERSION,
        bundletool_sha256=SHA256,
        aab_sha256=hashlib.sha256(bundle.read_bytes()).hexdigest(),
        apk_sha256=hashlib.sha256(apk.read_bytes()).hexdigest(),
        signing="disposable runner debug key; never a production credential",
        aab_native_alignment="PAGE_ALIGNMENT_16K",
    )
    (reports / "bundletool-validation.json").write_text(
        json.dumps(evidence, indent=2) + "\n"
    )
    print("PASS: actual AAB produced a signed, 16 KB-aligned validation APK.")


if __name__ == "__main__":
    main()
