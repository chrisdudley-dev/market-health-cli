"""Match every original failing ELF to bytes from its published dependency wheel."""

import hashlib
import json
from pathlib import Path
import urllib.request
import zipfile


def main():
    root = Path(__file__).resolve().parents[2]
    baseline = json.loads(
        (root / "docs/android/evidence/baseline-elf-audit.json").read_text()
    )
    failures = [r for r in baseline["libraries"] if r["issues"]]
    output = root / "android/app/build/reports/native-pages"
    cache = root / "android/app/build/baseline-wheels"
    output.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    sources = {}
    rows = []
    for item in failures:
        package, version, abi = (
            item["package"],
            item["version"],
            item["abi"].replace("-", "_"),
        )
        if package == "numpy":
            wheel = f"numpy-{version}-0-cp311-cp311-android_21_{abi}.whl"
        elif package == "chaquopy-openblas":
            wheel = f"chaquopy_openblas-{version}-5-py3-none-android_21_{abi}.whl"
        elif package == "chaquopy-libgfortran":
            wheel = f"chaquopy_libgfortran-{version}-0-py3-none-android_21_{abi}.whl"
        else:
            raise ValueError("Unattributed failing dependency: " + str(item))
        url = f"https://chaquo.com/pypi-13.1/{package}/{wheel}"
        if wheel not in sources:
            path = cache / wheel
            if not path.exists():
                path.write_bytes(urllib.request.urlopen(url, timeout=90).read())
            with zipfile.ZipFile(path) as archive:
                hashes = {
                    hashlib.sha256(archive.read(n)).hexdigest(): n
                    for n in archive.namelist()
                    if not n.endswith("/")
                }
            sources[wheel] = dict(
                url=url,
                wheel_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                hashes=hashes,
            )
        source = sources[wheel]
        if item["sha256"] not in source["hashes"]:
            raise ValueError(
                "Packaged ELF does not match the asserted source: " + item["path"]
            )
        rows.append(
            dict(
                path=item["path"],
                abi=item["abi"],
                package=package,
                version=version,
                source_kind=item["source_kind"],
                pt_load=[s["alignment"] for s in item["load_segments"]],
                elf_sha256=item["sha256"],
                wheel_url=url,
                wheel_sha256=source["wheel_sha256"],
                wheel_member=source["hashes"][item["sha256"]],
                origin_verified=True,
            )
        )
    result = dict(
        status="PASS",
        baseline_apk_sha256=baseline["artifact_sha256"],
        incompatible_libraries=len(rows),
        libraries=rows,
    )
    (output / "baseline-provenance.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    print(
        f"PASS: all {len(rows)} incompatible packaged libraries match their asserted published wheel bytes."
    )


if __name__ == "__main__":
    main()
