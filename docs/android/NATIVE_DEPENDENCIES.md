# Native dependency investigation

The original installable debug APK contains 272 ELF libraries. The actual-payload
audit found 40 incompatible libraries. Every failing library was matched by SHA-256
to its published dependency wheel; this is not an inference from package metadata.

Required ELF compatibility: every PT_LOAD alignment must be at least 0x4000
(16384 bytes) and segment offsets/virtual addresses must be page-congruent.
Directly mapped APK JNI libraries also require uncompressed 16 KB-aligned ZIP data.

Baseline APK SHA-256: `f836e1f425bf63d7daf073cd7f9489da7bc9357a4eb830015580eaf0d174ab5f`.

| Package / wheel build | ABI | Library filename | PT_LOAD alignment | Required | Source family | Compatible published build |
|---|---|---|---|---|---|---|
| numpy 1.26.2 / 0 | arm64-v8a | `numpy/core/_multiarray_tests.so` | 0x1000, 0x1000, 0x1000 | >= 0x4000 | NumPy | Yes, CPython 3.13 / 1.26.2 build 0 in the same stable index (Python upgrade required) |
| numpy 1.26.2 / 0 | arm64-v8a | `numpy/core/_multiarray_umath.so` | 0x1000, 0x1000, 0x1000 | >= 0x4000 | NumPy | Yes, CPython 3.13 / 1.26.2 build 0 in the same stable index (Python upgrade required) |
| numpy 1.26.2 / 0 | arm64-v8a | `numpy/core/_operand_flag_tests.so` | 0x1000, 0x1000, 0x1000 | >= 0x4000 | NumPy | Yes, CPython 3.13 / 1.26.2 build 0 in the same stable index (Python upgrade required) |
| numpy 1.26.2 / 0 | arm64-v8a | `numpy/core/_rational_tests.so` | 0x1000, 0x1000, 0x1000 | >= 0x4000 | NumPy | Yes, CPython 3.13 / 1.26.2 build 0 in the same stable index (Python upgrade required) |
| numpy 1.26.2 / 0 | arm64-v8a | `numpy/core/_simd.so` | 0x1000, 0x1000, 0x1000 | >= 0x4000 | NumPy | Yes, CPython 3.13 / 1.26.2 build 0 in the same stable index (Python upgrade required) |
| numpy 1.26.2 / 0 | arm64-v8a | `numpy/core/_struct_ufunc_tests.so` | 0x1000, 0x1000, 0x1000 | >= 0x4000 | NumPy | Yes, CPython 3.13 / 1.26.2 build 0 in the same stable index (Python upgrade required) |
| numpy 1.26.2 / 0 | arm64-v8a | `numpy/core/_umath_tests.so` | 0x1000, 0x1000, 0x1000 | >= 0x4000 | NumPy | Yes, CPython 3.13 / 1.26.2 build 0 in the same stable index (Python upgrade required) |
| numpy 1.26.2 / 0 | arm64-v8a | `numpy/fft/_pocketfft_internal.so` | 0x1000, 0x1000, 0x1000 | >= 0x4000 | NumPy | Yes, CPython 3.13 / 1.26.2 build 0 in the same stable index (Python upgrade required) |
| numpy 1.26.2 / 0 | arm64-v8a | `numpy/linalg/_umath_linalg.so` | 0x1000, 0x1000, 0x1000 | >= 0x4000 | NumPy | Yes, CPython 3.13 / 1.26.2 build 0 in the same stable index (Python upgrade required) |
| numpy 1.26.2 / 0 | arm64-v8a | `numpy/linalg/lapack_lite.so` | 0x1000, 0x1000, 0x1000 | >= 0x4000 | NumPy | Yes, CPython 3.13 / 1.26.2 build 0 in the same stable index (Python upgrade required) |
| numpy 1.26.2 / 0 | arm64-v8a | `numpy/random/_bounded_integers.so` | 0x1000, 0x1000, 0x1000 | >= 0x4000 | NumPy | Yes, CPython 3.13 / 1.26.2 build 0 in the same stable index (Python upgrade required) |
| numpy 1.26.2 / 0 | arm64-v8a | `numpy/random/_common.so` | 0x1000, 0x1000, 0x1000 | >= 0x4000 | NumPy | Yes, CPython 3.13 / 1.26.2 build 0 in the same stable index (Python upgrade required) |
| numpy 1.26.2 / 0 | arm64-v8a | `numpy/random/_generator.so` | 0x1000, 0x1000, 0x1000 | >= 0x4000 | NumPy | Yes, CPython 3.13 / 1.26.2 build 0 in the same stable index (Python upgrade required) |
| numpy 1.26.2 / 0 | arm64-v8a | `numpy/random/_mt19937.so` | 0x1000, 0x1000, 0x1000 | >= 0x4000 | NumPy | Yes, CPython 3.13 / 1.26.2 build 0 in the same stable index (Python upgrade required) |
| numpy 1.26.2 / 0 | arm64-v8a | `numpy/random/_pcg64.so` | 0x1000, 0x1000, 0x1000 | >= 0x4000 | NumPy | Yes, CPython 3.13 / 1.26.2 build 0 in the same stable index (Python upgrade required) |
| numpy 1.26.2 / 0 | arm64-v8a | `numpy/random/_philox.so` | 0x1000, 0x1000, 0x1000 | >= 0x4000 | NumPy | Yes, CPython 3.13 / 1.26.2 build 0 in the same stable index (Python upgrade required) |
| numpy 1.26.2 / 0 | arm64-v8a | `numpy/random/_sfc64.so` | 0x1000, 0x1000, 0x1000 | >= 0x4000 | NumPy | Yes, CPython 3.13 / 1.26.2 build 0 in the same stable index (Python upgrade required) |
| numpy 1.26.2 / 0 | arm64-v8a | `numpy/random/bit_generator.so` | 0x1000, 0x1000, 0x1000 | >= 0x4000 | NumPy | Yes, CPython 3.13 / 1.26.2 build 0 in the same stable index (Python upgrade required) |
| numpy 1.26.2 / 0 | arm64-v8a | `numpy/random/mtrand.so` | 0x1000, 0x1000, 0x1000 | >= 0x4000 | NumPy | Yes, CPython 3.13 / 1.26.2 build 0 in the same stable index (Python upgrade required) |
| chaquopy-libgfortran 4.9 / 0 | x86_64 | `chaquopy/lib/libgfortran.so.3` | 0x1000, 0x1000 | >= 0x4000 | Fortran runtime | No compatible x86_64 build in the original index; the new OpenBLAS no longer depends on it |
| chaquopy-openblas 0.2.20 / 5 | x86_64 | `chaquopy/lib/libopenblas.so` | 0x1000, 0x1000 | >= 0x4000 | OpenBLAS | No in the original stable index; 0.3.33 build 2 in Chaquopy upstream passes inspection |
| numpy 1.26.2 / 0 | x86_64 | `numpy/core/_multiarray_tests.so` | 0x1000, 0x1000, 0x1000 | >= 0x4000 | NumPy | Yes, CPython 3.13 / 1.26.2 build 0 in the same stable index (Python upgrade required) |
| numpy 1.26.2 / 0 | x86_64 | `numpy/core/_multiarray_umath.so` | 0x1000, 0x1000, 0x1000 | >= 0x4000 | NumPy | Yes, CPython 3.13 / 1.26.2 build 0 in the same stable index (Python upgrade required) |
| numpy 1.26.2 / 0 | x86_64 | `numpy/core/_operand_flag_tests.so` | 0x1000, 0x1000, 0x1000 | >= 0x4000 | NumPy | Yes, CPython 3.13 / 1.26.2 build 0 in the same stable index (Python upgrade required) |
| numpy 1.26.2 / 0 | x86_64 | `numpy/core/_rational_tests.so` | 0x1000, 0x1000, 0x1000 | >= 0x4000 | NumPy | Yes, CPython 3.13 / 1.26.2 build 0 in the same stable index (Python upgrade required) |
| numpy 1.26.2 / 0 | x86_64 | `numpy/core/_simd.so` | 0x1000, 0x1000, 0x1000 | >= 0x4000 | NumPy | Yes, CPython 3.13 / 1.26.2 build 0 in the same stable index (Python upgrade required) |
| numpy 1.26.2 / 0 | x86_64 | `numpy/core/_struct_ufunc_tests.so` | 0x1000, 0x1000, 0x1000 | >= 0x4000 | NumPy | Yes, CPython 3.13 / 1.26.2 build 0 in the same stable index (Python upgrade required) |
| numpy 1.26.2 / 0 | x86_64 | `numpy/core/_umath_tests.so` | 0x1000, 0x1000, 0x1000 | >= 0x4000 | NumPy | Yes, CPython 3.13 / 1.26.2 build 0 in the same stable index (Python upgrade required) |
| numpy 1.26.2 / 0 | x86_64 | `numpy/fft/_pocketfft_internal.so` | 0x1000, 0x1000, 0x1000 | >= 0x4000 | NumPy | Yes, CPython 3.13 / 1.26.2 build 0 in the same stable index (Python upgrade required) |
| numpy 1.26.2 / 0 | x86_64 | `numpy/linalg/_umath_linalg.so` | 0x1000, 0x1000, 0x1000 | >= 0x4000 | NumPy | Yes, CPython 3.13 / 1.26.2 build 0 in the same stable index (Python upgrade required) |
| numpy 1.26.2 / 0 | x86_64 | `numpy/linalg/lapack_lite.so` | 0x1000, 0x1000, 0x1000 | >= 0x4000 | NumPy | Yes, CPython 3.13 / 1.26.2 build 0 in the same stable index (Python upgrade required) |
| numpy 1.26.2 / 0 | x86_64 | `numpy/random/_bounded_integers.so` | 0x1000, 0x1000, 0x1000 | >= 0x4000 | NumPy | Yes, CPython 3.13 / 1.26.2 build 0 in the same stable index (Python upgrade required) |
| numpy 1.26.2 / 0 | x86_64 | `numpy/random/_common.so` | 0x1000, 0x1000, 0x1000 | >= 0x4000 | NumPy | Yes, CPython 3.13 / 1.26.2 build 0 in the same stable index (Python upgrade required) |
| numpy 1.26.2 / 0 | x86_64 | `numpy/random/_generator.so` | 0x1000, 0x1000, 0x1000 | >= 0x4000 | NumPy | Yes, CPython 3.13 / 1.26.2 build 0 in the same stable index (Python upgrade required) |
| numpy 1.26.2 / 0 | x86_64 | `numpy/random/_mt19937.so` | 0x1000, 0x1000, 0x1000 | >= 0x4000 | NumPy | Yes, CPython 3.13 / 1.26.2 build 0 in the same stable index (Python upgrade required) |
| numpy 1.26.2 / 0 | x86_64 | `numpy/random/_pcg64.so` | 0x1000, 0x1000, 0x1000 | >= 0x4000 | NumPy | Yes, CPython 3.13 / 1.26.2 build 0 in the same stable index (Python upgrade required) |
| numpy 1.26.2 / 0 | x86_64 | `numpy/random/_philox.so` | 0x1000, 0x1000, 0x1000 | >= 0x4000 | NumPy | Yes, CPython 3.13 / 1.26.2 build 0 in the same stable index (Python upgrade required) |
| numpy 1.26.2 / 0 | x86_64 | `numpy/random/_sfc64.so` | 0x1000, 0x1000, 0x1000 | >= 0x4000 | NumPy | Yes, CPython 3.13 / 1.26.2 build 0 in the same stable index (Python upgrade required) |
| numpy 1.26.2 / 0 | x86_64 | `numpy/random/bit_generator.so` | 0x1000, 0x1000, 0x1000 | >= 0x4000 | NumPy | Yes, CPython 3.13 / 1.26.2 build 0 in the same stable index (Python upgrade required) |
| numpy 1.26.2 / 0 | x86_64 | `numpy/random/mtrand.so` | 0x1000, 0x1000, 0x1000 | >= 0x4000 | NumPy | Yes, CPython 3.13 / 1.26.2 build 0 in the same stable index (Python upgrade required) |

Source URLs, source-wheel hashes, ELF hashes and full paths for every row are in
[baseline-provenance.json](evidence/baseline-provenance.json). The full original
[packaged audit](evidence/baseline-elf-audit.json) includes passing libraries too.

The original ARM OpenBLAS/Fortran libraries, pandas libraries, Chaquopy runtime,
CPython extensions and AndroidX libraries passed the original alignment audit.
They are not incorrectly classified as failing simply because of package version.

## Selected resolution

- Chaquopy remains 17.1.0; upgrading the plugin alone cannot fix old wheel payloads.
- CPython changes from 3.11.17 to 3.13.16. Stable cp313 NumPy 1.26.2 and pandas
  2.1.3 wheels pass ELF inspection on arm64-v8a and x86_64.
- OpenBLAS changes from 0.2.20 to the inspected 0.3.33 build 2. Its two wheels
  come from the explicit Chaquopy upstream page, not the stable index.
- The new OpenBLAS metadata and native dependencies do not require libgfortran.
  NumPy functionality is retained; no financial formula or policy is ported.
- The inspected candidate APK contains 266 ELF libraries and passes the 16 KB
  ELF and direct-mapping ZIP checks. This is BUILD evidence, not runtime proof.
- Independently, CI run [40201995021](https://github.com/chrisdudley-dev/market-health-cli/actions/runs/40201995021)
  installed both debug and AAB-derived release APKs on actual 4 KB and 16 KB
  x86_64 kernels. All 11 required instrumentation tests passed on each APK/kernel
  combination, followed by a reboot/persistence probe on each emulator.
  See the [release matrix](RELEASE_READINESS.md); physical ARM remains untested.
- All wheel URLs and SHA-256 digests are locked in `android/requirements-lock.json`.
  A verified offline wheelhouse handles Chaquopy's second-ABI requirements without
  dropping integrity checks.

Rebuilding was investigated: the old Fortran recipe copies a prebuilt GCC 4.9
runtime, so a Gradle packaging flag cannot repair it. The current upstream BLAS
recipe builds 0.3.33 without that dependency and enables 16 KB linker alignment.
The available inspected wheels make a local GCC/NumPy rebuild unnecessary.

Sources: [stable NumPy](https://chaquo.com/pypi-13.1/numpy/),
[stable pandas](https://chaquo.com/pypi-13.1/pandas/),
[original OpenBLAS](https://chaquo.com/pypi-13.1/chaquopy-openblas/),
[original Fortran](https://chaquo.com/pypi-13.1/chaquopy-libgfortran/),
[candidate BLAS](https://chaquo.com/pypi-upstream/chaquopy-openblas/),
[upstream build recipes](https://github.com/chaquo/chaquopy/tree/884ec5f14591d69844e20c9dc6a6a9c5d1ba0a41/server/pypi/packages),
[Android page-size requirements](https://developer.android.com/guide/practices/page-sizes).
