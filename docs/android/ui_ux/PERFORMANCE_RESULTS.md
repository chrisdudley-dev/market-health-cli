# Rendering observations

Recorded on the API35 x86_64 4 KB S9+-class emulator, 1080×2220, density480, font1.0, software rendering, disposable debug APK. Test data is 25 synthetic presentation rows and 300 history rows repeating frozen fixture scores. The application Activity and Python process were already running. This is an in-process rendering observation, not a cold app launch or physical release benchmark.

The instrumentation observes Android Window FrameMetrics without modifying production rendering or financial code. Elapsed times below include test automation, drawer clicks and scrolling; they are not time-to-interactive benchmarks. Raw values are in evidence/performance.json.

| Scenario | Captured frames | Median frame ms | p95 frame ms | Automation elapsed ms |
| --- | ---: | ---: | ---: | ---: |
| initial dashboard | 1 | 50.06 | 50.06 | 61.69 |
| 25-symbol list scroll | 49 | 16.73 | 16.92 | 1048.73 |
| history chart and timeline | 68 | 16.76 | 17.63 | 1398.48 |
| navigation | 49 | 16.76 | 16.93 | 851.57 |

Dashboard has only one sampled frame, so its percentile is that single frame and has no statistical stability. The longer list/history/navigation samples characterize this one debug emulator run only. No before/after speed-up, hardware 60 fps guarantee, or physical battery claim is made. An earlier cold synthetic-host debug run had much slower initial frames; setup/cache/host differences make direct comparison invalid.

Lists use stable symbol/decision/account keys and lazy composition. Display projections/filter/sort/history-point preparation are remembered by data and query. Charts only paint prepared saved scores; no financial calculation, quote transport or SQLite access occurs in a Composable. Foreground worker state observation collects only while lifecycle STARTED; it rereads persisted state without polling a provider or enqueueing jobs.

Actual application startup is separately exercised for both debug and AAB-derived test-signed release APKs in the runtime runner. It is a functional startup PASS, not a frame-performance benchmark. Physical S9+ frame timing, independent Macrobenchmark/baseline profile and cold-start distribution are NOT TESTED and remain manual review follow-ups. No new physical device test or four-hour idle run was begun.
