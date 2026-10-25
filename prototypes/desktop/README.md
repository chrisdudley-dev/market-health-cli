# Isolated desktop prototype — not the application target

The product target is Android. This preserves the completed Qt prototype for reference.
No production core/application/storage module may import this directory.

Qt widgets, tray lifecycle, Qt timer/worker, OS notification delivery, PyInstaller,
and desktop icons/launchers are isolated here. The policy, engine, portfolio,
SQLite storage, sizing, history and notification outbox have moved to platform-neutral
`market_health/` modules. The prototype's automated tests are retained and optional.

Optional reference run from the repository root:

    python -m pip install -e '.[prototype-desktop]'
    python -m prototypes.desktop.market_health_desktop

The previous desktop build instructions under docs/desktop describe historical work.
They are superseded by docs/android/ARCHITECTURE.md and android/README.md.
