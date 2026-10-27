import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication
from prototypes.desktop.market_health_desktop.app import Window, HoldingDialog, STYLE
from market_health.storage.sqlite import Store
from market_health.engine_api import Scan
from market_health.policy import Scores


@pytest.fixture
def window(tmp_path):
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(STYLE)
    db = Store(tmp_path / "db")
    db.save_holding("RPG", "Roth IRA", 3, 50, "Review H5")
    db.save_settings({"net_liq": 6000, "cash": 750})
    db.apply_scan(
        Scan(
            "ui",
            "2026-10-25T12:00:00Z",
            (
                Scores("RPG", 58, 62, 53, 57, "DMG", 238),
                Scores("IVE", 57, 73, 60, 62, "RCL", 238),
                Scores("FLAT", 58, 58, 58, 58, "", 100),
            ),
            "local snapshot (historical)",
        )
    )
    win = Window(db)
    win.show()
    app.processEvents()
    yield win
    win.hide()
    win.tray.hide()
    win.deleteLater()
    app.processEvents()


def test_all_screens_and_audit(window):
    assert window.pages.count() == 8
    assert window.tables["Trading List"].rowCount() == 1
    assert window.tables["Buy Candidates"].rowCount() == 1
    assert window.tables["Portfolio"].rowCount() == 1
    for i in range(8):
        window.nav.setCurrentRow(i)
        QApplication.processEvents()
        assert window.pages.currentIndex() == i
    window.tables["Trading List"].selectRow(0)
    QApplication.processEvents()
    text = window.details["Trading List"].toPlainText()
    assert "H5 <= C - 3" in text and "53 <= 55" in text
    assert "floor(750.00 / 238) = 3" in text


def test_manual_ownership_and_account_edit(window):
    dialog = HoldingDialog(window.store, symbol="IVE")
    dialog.account.setCurrentText("My account")
    dialog.shares.setValue(2.5)
    dialog.save()
    window.load()
    assert window.tables["Trading List"].rowCount() == 2
    assert window.tables["Buy Candidates"].rowCount() == 0
    assert "My account" in [
        window.history_account.itemText(i)
        for i in range(window.history_account.count())
    ]
    window.searches["Market Health"].setText("IVE")
    table = window.tables["Market Health"]
    assert sum(not table.isRowHidden(r) for r in range(table.rowCount())) == 1


def test_background_tray_close_and_notification_dispatch(window, monkeypatch):
    from PySide6.QtWidgets import QSystemTrayIcon
    from PySide6.QtGui import QCloseEvent

    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", lambda: True)
    monkeypatch.setattr(QSystemTrayIcon, "supportsMessages", lambda: True)
    window.store.save_settings({"background": True, "interval": 5})
    window.configure_timer()
    assert window.timer.isActive() and window.timer.interval() == 300000
    event = QCloseEvent()
    window.closeEvent(event)
    assert not event.isAccepted() and not window.isVisible()
    window.restore_window()
    assert window.isVisible()
    # A later live transition goes through the persisted notification outbox.
    window.store.apply_scan(
        Scan(
            "notify",
            "2026-10-25T13:00:00Z",
            (Scores("RPG", 58, 62, 60, 60),),
            "live engine",
        )
    )
    sent = []
    monkeypatch.setattr(window.tray, "showMessage", lambda *a: sent.append(a))
    window.deliver_notifications()
    window.deliver_notifications()
    assert len(sent) == 1
    assert "SELL → HOLD" in sent[0][1]
