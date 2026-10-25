"""Market Health native Qt desktop application."""

from pathlib import Path
from datetime import datetime, timezone
import argparse
import html
import json
import logging
import sys

from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QListWidget,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QLineEdit,
    QTextBrowser,
    QSplitter,
    QDialog,
    QFormLayout,
    QComboBox,
    QDoubleSpinBox,
    QSpinBox,
    QCheckBox,
    QDialogButtonBox,
    QMessageBox,
    QSystemTrayIcon,
    QMenu,
    QFileDialog,
)

from market_health import __version__
from market_health.policy.explanations import policy_text
from market_health.storage.sqlite import Store
from market_health.application.service import RefreshService, size_position
from market_health.application.logging_config import configure

COLORS = {
    "BUY": "#47d9ad",
    "HOLD": "#70b7fa",
    "WATCH": "#f1c36a",
    "SELL": "#ff7f91",
    "HOLD — RESCUE": "#c7a0ff",
    "DATA ERROR": "#ff7f91",
    "UNKNOWN": "#9aa9be",
}
STYLE = """
QWidget { background:#101723; color:#dfe7f3; font-family:'Inter','Segoe UI',sans-serif; font-size:13px; }
QMainWindow { background:#101723; }
QLabel#title { font-size:28px; font-weight:650; }
QLabel#brand { font-size:20px; font-weight:700; color:#61dfbd; padding:16px 8px; }
QLabel#muted { color:#9aa9be; }
QLabel#card { background:#1a2535; border:1px solid #2a3a50; border-radius:10px; padding:16px; font-size:18px; }
QListWidget { background:#121d2d; border:0; padding:8px; min-width:170px; max-width:210px; }
QListWidget::item { padding:14px 12px; border-radius:7px; }
QListWidget::item:selected { background:#24443f; color:#78edcd; }
QPushButton { background:#26374d; padding:9px 14px; border:1px solid #344860; border-radius:6px; }
QPushButton:hover { background:#354c67; }
QPushButton#primary { background:#187d68; color:white; border:1px solid #28a58b; font-weight:600; }
QPushButton:disabled { color:#6e7b8f; }
QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox { background:#192638; padding:7px; border:1px solid #304258; border-radius:5px; }
QTableWidget { background:#121d2c; alternate-background-color:#172336; border:1px solid #28394f; gridline-color:#26354a; selection-background-color:#244e61; }
QHeaderView::section { background:#1d2c40; color:#aebfd4; padding:10px; border:0; font-weight:600; }
QTextBrowser { background:#141f2e; border:1px solid #2a3a50; padding:10px; }
QGroupBox { border:1px solid #304258; border-radius:7px; margin-top:12px; padding-top:18px; }
QGroupBox::title { color:#91a8c4; }
QCheckBox { padding:6px; }
QToolTip { background:#26374d; color:#e8edf5; border:1px solid #496079; }
"""


def app_icon():
    pix = QPixmap(64, 64)
    pix.fill(QColor("#152d32"))
    painter = QPainter(pix)
    painter.setPen(QColor("#62e2bc"))
    painter.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, "MH")
    painter.end()
    return QIcon(pix)


class RefreshWorker(QThread):
    done = Signal(str)

    def __init__(self, store, snapshot=None):
        super().__init__()
        self.store, self.snapshot = store, snapshot
        self.error = ""

    def run(self):
        try:
            RefreshService(self.store).refresh(self.snapshot)
            self.done.emit("")
        except Exception as exc:
            self.error = str(exc)
            self.done.emit(self.error)


class HoldingDialog(QDialog):
    def __init__(self, store, holding=None, symbol="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit holding" if holding else "Mark symbol owned")
        self.store, self.holding = store, holding
        self.setMinimumWidth(420)
        form = QFormLayout(self)
        self.symbol = QLineEdit((holding or {}).get("symbol", symbol))
        self.account = QComboBox()
        self.account.setEditable(True)
        self.account.addItems(store.accounts())
        self.account.setCurrentText((holding or {}).get("account", "Other"))
        self.shares = QDoubleSpinBox()
        self.shares.setRange(0, 1e12)
        self.shares.setDecimals(6)
        self.shares.setValue((holding or {}).get("shares", 0))
        self.cost = QLineEdit(
            ""
            if (holding or {}).get("cost_basis") is None
            else str(holding["cost_basis"])
        )
        self.notes = QLineEdit((holding or {}).get("notes", ""))
        self.owned = QCheckBox("Owned in my local portfolio")
        self.owned.setChecked(True)
        for label, w in (
            ("Symbol", self.symbol),
            ("Account", self.account),
            ("Shares", self.shares),
            ("Cost basis / share (optional)", self.cost),
            ("Notes (optional)", self.notes),
            ("", self.owned),
        ):
            form.addRow(label, w)
        self.error = QLabel("")
        form.addRow(self.error)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def save(self):
        try:
            if not self.owned.isChecked():
                if self.holding:
                    self.store.remove_holding(
                        self.holding["symbol"], self.holding["account"]
                    )
            else:
                self.store.save_holding(
                    self.symbol.text(),
                    self.account.currentText(),
                    self.shares.value(),
                    float(self.cost.text()) if self.cost.text().strip() else None,
                    self.notes.text(),
                    (self.holding["symbol"], self.holding["account"])
                    if self.holding
                    else None,
                )
            self.accept()
        except Exception as exc:
            self.error.setText(str(exc))


class Window(QMainWindow):
    def __init__(self, store, snapshot=None):
        super().__init__()
        self.store = store
        self.snapshot = snapshot
        self.worker = None
        self.rows = []
        self.tables = {}
        self.details = {}
        self.searches = {}
        self.cards = {}
        self.setWindowTitle(f"Market Health · {__version__}")
        self.setWindowIcon(app_icon())
        self.resize(1360, 860)
        self.setMinimumSize(960, 640)
        main = QWidget()
        self.setCentralWidget(main)
        outer = QHBoxLayout(main)
        outer.setContentsMargins(0, 0, 0, 0)
        sidebar = QVBoxLayout()
        brand = QLabel("  MH  /  Market Health")
        brand.setObjectName("brand")
        sidebar.addWidget(brand)
        self.nav = QListWidget()
        self.nav.addItems(
            [
                "Dashboard",
                "Portfolio",
                "Trading List",
                "Buy Candidates",
                "Market Health",
                "History",
                "Policy",
                "Settings",
            ]
        )
        sidebar.addWidget(self.nav, 1)
        version = QLabel(f"   LOCAL PORTFOLIO\n   v{__version__}")
        version.setObjectName("muted")
        sidebar.addWidget(version)
        outer.addLayout(sidebar)
        content = QVBoxLayout()
        content.setContentsMargins(24, 22, 24, 20)
        header = QHBoxLayout()
        self.title = QLabel("Dashboard")
        self.title.setObjectName("title")
        header.addWidget(self.title, 1)
        self.refresh_button = QPushButton("Refresh Now")
        self.refresh_button.setObjectName("primary")
        self.refresh_button.clicked.connect(lambda: self.refresh())
        header.addWidget(self.refresh_button)
        content.addLayout(header)
        self.status_label = QLabel("")
        self.status_label.setObjectName("muted")
        self.status_label.setWordWrap(True)
        content.addWidget(self.status_label)
        self.pages = QStackedWidget()
        content.addWidget(self.pages, 1)
        outer.addLayout(content, 1)
        self.build_dashboard()
        self.build_table_page("Portfolio")
        self.build_table_page("Trading List")
        self.build_table_page("Buy Candidates")
        self.build_table_page("Market Health")
        self.build_history()
        policy = QTextBrowser()
        policy.setPlainText(policy_text())
        self.pages.addWidget(policy)
        self.build_settings()
        self.nav.currentRowChanged.connect(self.navigate)
        self.nav.setCurrentRow(0)
        self.timer = QTimer(self)
        self.timer.timeout.connect(lambda: self.refresh())
        self.setup_tray()
        self.load()
        self.configure_timer()
        self.freshness_timer = QTimer(self)
        self.freshness_timer.timeout.connect(self.check_staleness)
        self.freshness_timer.start(60000)
        QTimer.singleShot(0, self.deliver_notifications)

    def check_staleness(self):
        status = self.store.status()
        if status and status["status"] == "ok" and status["source"] == "live engine":
            refreshed = datetime.fromisoformat(
                status["timestamp"].replace("Z", "+00:00")
            )
            age = (datetime.now(timezone.utc) - refreshed).total_seconds()
            if age > self.store.settings()["interval"] * 60:
                self.status_label.setText(
                    "STALE · Last refresh: "
                    + status["timestamp"]
                    + " · Refresh Now to update"
                )

    def navigate(self, index):
        self.pages.setCurrentIndex(index)
        self.title.setText(self.nav.item(index).text())

    def build_dashboard(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        tagline = QLabel("Market scores. Clear decisions. Your local portfolio.")
        tagline.setObjectName("muted")
        layout.addWidget(tagline)
        for keys in (
            ("Owned positions", "BUY candidates", "HOLD", "WATCH"),
            ("SELL", "Rescue", "Cash", "Net Liq"),
        ):
            line = QHBoxLayout()
            for k in keys:
                card = QLabel(k + "\n—")
                card.setObjectName("card")
                self.cards[k] = card
                line.addWidget(card, 1)
            layout.addLayout(line)
        self.market_summary = QLabel("")
        self.market_summary.setWordWrap(True)
        layout.addWidget(self.market_summary)
        self.dashboard_audit = QTextBrowser()
        layout.addWidget(self.dashboard_audit, 1)
        self.pages.addWidget(page)

    def build_table_page(self, name):
        page = QWidget()
        layout = QVBoxLayout(page)
        bar = QHBoxLayout()
        search = QLineEdit()
        search.setPlaceholderText("Search symbol…")
        bar.addWidget(search, 1)
        if name in ("Portfolio", "Buy Candidates", "Market Health"):
            add = QPushButton("Mark Owned")
            add.clicked.connect(lambda: self.edit_holding())
            bar.addWidget(add)
        if name == "Portfolio":
            edit = QPushButton("Edit holding")
            edit.clicked.connect(self.edit_selected_holding)
            remove = QPushButton("Remove holding")
            remove.clicked.connect(self.remove_selected)
            bar.addWidget(edit)
            bar.addWidget(remove)
        layout.addLayout(bar)
        split = QSplitter(Qt.Orientation.Vertical)
        table = self.new_table()
        detail = QTextBrowser()
        detail.setPlainText(
            "Select a symbol to inspect its exact policy checks and position sizing."
        )
        split.addWidget(table)
        split.addWidget(detail)
        split.setSizes([420, 210])
        layout.addWidget(split)
        self.tables[name] = table
        self.searches[name] = search
        self.details[name] = detail
        search.textChanged.connect(lambda text: self.filter_table(table, text))
        table.itemSelectionChanged.connect(lambda: self.show_detail(name))
        if name == "Portfolio":
            table.cellDoubleClicked.connect(lambda *_: self.edit_selected_holding())
        self.pages.addWidget(page)

    @staticmethod
    def new_table():
        table = QTableWidget()
        table.setAlternatingRowColors(True)
        table.setSortingEnabled(True)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.verticalHeader().hide()
        table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        table.horizontalHeader().setStretchLastSection(True)
        return table

    def build_history(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        filters = QHBoxLayout()
        self.history_symbol = QLineEdit()
        self.history_symbol.setPlaceholderText("Symbol")
        self.history_date = QLineEdit()
        self.history_date.setPlaceholderText("Date · YYYY-MM-DD (UTC)")
        self.history_action = QComboBox()
        self.history_action.addItems(["All actions", *COLORS])
        self.history_account = QComboBox()
        self.history_account.addItems(["All accounts", *self.store.accounts()])
        for w in (
            self.history_symbol,
            self.history_date,
            self.history_action,
            self.history_account,
        ):
            filters.addWidget(w)
        layout.addLayout(filters)
        self.tables["History"] = self.new_table()
        self.details["History"] = QTextBrowser()
        split = QSplitter(Qt.Orientation.Vertical)
        split.addWidget(self.tables["History"])
        split.addWidget(self.details["History"])
        split.setSizes([450, 200])
        layout.addWidget(split)
        export = QPushButton("Export filtered history JSON")
        export.clicked.connect(self.export_history)
        layout.addWidget(export)
        for w in (self.history_symbol, self.history_date):
            w.textChanged.connect(self.load_history)
        for w in (self.history_action, self.history_account):
            w.currentIndexChanged.connect(self.load_history)
        self.tables["History"].itemSelectionChanged.connect(
            lambda: self.show_detail("History")
        )
        self.pages.addWidget(page)

    def build_settings(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        form = QFormLayout()
        settings = self.store.settings()
        self.net_liq = QLineEdit(
            "" if settings["net_liq"] is None else str(settings["net_liq"])
        )
        self.cash = QLineEdit("" if settings["cash"] is None else str(settings["cash"]))
        self.targets = QSpinBox()
        self.targets.setRange(1, 1000)
        self.targets.setValue(settings["target_positions"])
        self.interval = QComboBox()
        self.interval.addItems(["5", "10", "15", "30", "60"])
        self.interval.setCurrentText(str(settings["interval"]))
        for label, w in (
            ("Net Liquidation Value (manual)", self.net_liq),
            ("Cash available (optional)", self.cash),
            ("Target positions", self.targets),
            ("Refresh interval (minutes)", self.interval),
        ):
            form.addRow(label, w)
        layout.addLayout(form)
        self.toggles = {}
        for key, label in (
            ("background", "Enable Background Monitoring"),
            ("notify_sell", "Notify on SELL"),
            ("notify_watch", "Notify on WATCH"),
            ("notify_hold", "Notify on HOLD recovery"),
            ("notify_rescue", "Notify on rescue"),
            ("notify_buy", "Notify on new BUY candidates"),
        ):
            toggle = QCheckBox(label)
            toggle.setChecked(settings[key])
            self.toggles[key] = toggle
            layout.addWidget(toggle)
        dedupe = QCheckBox(
            "Suppress duplicate notifications · always enforced for unchanged states"
        )
        dedupe.setChecked(True)
        dedupe.setEnabled(False)
        layout.addWidget(dedupe)
        save = QPushButton("Save settings")
        save.setObjectName("primary")
        save.clicked.connect(self.save_settings)
        layout.addWidget(save)
        note = QLabel(
            "Portfolio and account labels are entered manually. Monitoring runs while this application is open or in the system tray."
        )
        note.setWordWrap(True)
        note.setObjectName("muted")
        layout.addWidget(note)
        layout.addStretch()
        self.pages.addWidget(page)

    def setup_tray(self):
        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip("Market Health")
        menu = QMenu()
        for text, fn in (
            ("Open Market Health", self.restore_window),
            ("Refresh Now", lambda: self.refresh()),
            ("Quit", self.quit_app),
        ):
            action = QAction(text, self)
            action.triggered.connect(fn)
            menu.addAction(action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda reason: (
                self.restore_window()
                if reason == QSystemTrayIcon.ActivationReason.Trigger
                else None
            )
        )
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()

    def restore_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def configure_timer(self):
        self.timer.stop()
        s = self.store.settings()
        if s["background"] and not self.snapshot:
            self.timer.start(s["interval"] * 60 * 1000)

    def save_settings(self):
        try:
            values = {k: v.isChecked() for k, v in self.toggles.items()}
            if values["background"] and not QSystemTrayIcon.isSystemTrayAvailable():
                QMessageBox.information(
                    self,
                    "Monitoring",
                    "No system tray is available. Monitoring can run while the main window remains open.",
                )
            values.update(
                net_liq=float(self.net_liq.text())
                if self.net_liq.text().strip()
                else None,
                cash=float(self.cash.text()) if self.cash.text().strip() else None,
                target_positions=self.targets.value(),
                interval=int(self.interval.currentText()),
            )
            self.store.save_settings(values)
            self.configure_timer()
            self.load()
            self.statusBar().showMessage("Settings saved", 4000)
        except Exception as exc:
            QMessageBox.warning(self, "Settings", str(exc))

    def refresh(self):
        if self.worker and self.worker.isRunning():
            return
        self.refresh_button.setEnabled(False)
        self.refresh_button.setText("Refreshing…")
        self.status_label.setText("Fetching market data and evaluating MH Policy…")
        self.worker = RefreshWorker(self.store, self.snapshot)
        self.worker.done.connect(self.refresh_done)
        self.worker.start()

    def refresh_done(self, error):
        self.refresh_button.setEnabled(True)
        self.refresh_button.setText("Refresh Now")
        self.load()
        self.deliver_notifications()
        if error:
            self.status_label.setText("STALE · Refresh failed: " + error)

    def deliver_notifications(self):
        available = (
            QSystemTrayIcon.isSystemTrayAvailable()
            and QSystemTrayIcon.supportsMessages()
        )
        for row in self.store.pending_notifications():
            # Claim before dispatch: OS APIs acknowledge submission, not display.
            self.store.mark_notification(
                row["id"],
                "submitted" if available else "unavailable",
                "" if available else "Desktop notifications unavailable",
            )
            if available:
                self.tray.showMessage(
                    row["title"],
                    row["body"],
                    QSystemTrayIcon.MessageIcon.Information,
                    15000,
                )
                logging.getLogger("market_health.desktop").info(
                    "notification_submitted"
                )

    def load(self):
        self.rows = self.store.latest()
        holdings = self.store.holdings()
        owned = {h["symbol"] for h in holdings}
        data = {r["symbol"]: r for r in self.rows}
        s = self.store.settings()
        status = self.store.status()
        status_text = "No scan yet · Refresh Now to load scores"
        if status:
            status_text = f"{status['status'].upper()} · {status['timestamp']} · {status['source']}"
            if status["status"] == "error":
                status_text = "STALE · " + status_text + " · " + status["error"]
            elif status["status"] == "partial":
                status_text = "STALE / PARTIAL · " + status_text
            if "historical" in status["source"]:
                status_text = "HISTORICAL SNAPSHOT · " + status_text
        self.status_label.setText(status_text)

        # A changed ownership period must await a new scan; never relabel an old
        # unowned BUY decision as an owned HOLD decision in the UI.
        def current(r):
            return r and r["owned"] == (r["symbol"] in owned)

        active = [r for r in self.rows if r["symbol"] in owned and current(r)]
        buys = [
            r
            for r in self.rows
            if r["symbol"] not in owned and r["result"]["buy_qualified"]
        ]
        counts = {name: sum(r["action"] == name for r in active) for name in COLORS}
        cards = {
            "Owned positions": len(owned),
            "BUY candidates": len(buys),
            "HOLD": counts["HOLD"],
            "WATCH": counts["WATCH"],
            "SELL": counts["SELL"],
            "Rescue": counts["HOLD — RESCUE"],
            "Cash": "—" if s["cash"] is None else f"{s['cash']:,.2f}",
            "Net Liq": "—" if s["net_liq"] is None else f"{s['net_liq']:,.2f}",
        }
        for k, v in cards.items():
            self.cards[k].setText(f"{k}\n{v}")
        cs = [r["scores"]["c"] for r in self.rows if r["scores"]["c"] is not None]
        self.market_summary.setText(
            f"Universe: {len(self.rows)} symbols · Mean C: {sum(cs) / len(cs):.1f}%"
            if cs
            else "Universe has not been refreshed."
        )
        alerts = [
            r
            for r in active
            if r["action"] in ("SELL", "WATCH", "HOLD — RESCUE", "DATA ERROR")
        ]
        self.dashboard_audit.setHtml(
            "<h3>Positions to review</h3>"
            + (
                "".join(
                    f"<p><b style='color:{COLORS[r['action']]}'>{html.escape(r['symbol'])} · {r['action']}</b><br>{html.escape(r['result']['human_explanation'])}</p>"
                    for r in alerts
                )
                or "<p>No owned positions currently require review.</p>"
            )
            + "<p>Open Trading List for exact rule checks.</p>"
        )
        portfolio = []
        trading = []
        for h in holdings:
            r = data.get(h["symbol"])
            valid = current(r)
            sc = r["scores"] if r else {}
            action = r["action"] if valid else "PENDING REFRESH"
            portfolio.append(
                (
                    [
                        h["symbol"],
                        h["account"],
                        h["shares"],
                        h["cost_basis"],
                        action,
                        *[sc.get(k) for k in ("blend", "c", "h1", "h5", "state")],
                        r["timestamp"] if r else "—",
                    ],
                    r,
                    h,
                )
            )
        for sym in sorted(owned):
            r = data.get(sym)
            valid = current(r)
            sc = r["scores"] if r else {}
            trading.append(
                (
                    [
                        sym,
                        sum(h["shares"] for h in holdings if h["symbol"] == sym),
                        *[sc.get(k) for k in ("blend", "c", "h1", "h5", "state")],
                        r["action"] if valid else "PENDING REFRESH",
                        r["result"]["human_explanation"]
                        if valid
                        else "Refresh after ownership changes",
                    ],
                    r,
                    None,
                )
            )
        self.populate(
            "Portfolio",
            [
                "Symbol",
                "Account",
                "Shares",
                "Cost / share",
                "Action",
                "Blend",
                "C",
                "H1",
                "H5",
                "State",
                "Updated",
            ],
            portfolio,
        )
        self.populate(
            "Trading List",
            ["Symbol", "Shares", "Blend", "C", "H1", "H5", "State", "Action", "Reason"],
            trading,
        )
        for name, rows in (("Buy Candidates", buys), ("Market Health", self.rows)):
            values = []
            for r in rows:
                sc = r["scores"]
                values.append(
                    (
                        [
                            r["symbol"],
                            *[
                                sc.get(k)
                                for k in (
                                    "blend",
                                    "c",
                                    "h1",
                                    "h5",
                                    "state",
                                    "stop",
                                    "buy",
                                    "price",
                                )
                            ],
                            r["action"] if current(r) else "PENDING REFRESH",
                            sc.get("asof", ""),
                        ],
                        r,
                        None,
                    )
                )
            self.populate(
                name,
                [
                    "Symbol",
                    "Blend",
                    "C",
                    "H1",
                    "H5",
                    "State",
                    "Stop",
                    "Buy",
                    "Price",
                    "Action",
                    "Price as of",
                ],
                values,
            )
        for name, search in self.searches.items():
            self.filter_table(self.tables[name], search.text())
        account = self.history_account.currentText()
        self.history_account.blockSignals(True)
        self.history_account.clear()
        self.history_account.addItems(["All accounts", *self.store.accounts()])
        self.history_account.setCurrentText(account)
        self.history_account.blockSignals(False)
        self.load_history()
        self.check_staleness()

    def populate(self, name, headers, rows):
        table = self.tables[name]
        table.setSortingEnabled(False)
        table.clear()
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setRowCount(len(rows))
        for i, (values, decision, holding) in enumerate(rows):
            for j, value in enumerate(values):
                item = QTableWidgetItem()
                if isinstance(value, (int, float)):
                    item.setData(Qt.ItemDataRole.DisplayRole, value)
                else:
                    item.setText("—" if value is None else str(value))
                item.setData(
                    Qt.ItemDataRole.UserRole, dict(decision=decision, holding=holding)
                )
                if str(value) in COLORS:
                    item.setForeground(QColor(COLORS[str(value)]))
                table.setItem(i, j, item)
        table.setSortingEnabled(True)
        table.sortItems(0)

    @staticmethod
    def filter_table(table, text):
        for row in range(table.rowCount()):
            table.setRowHidden(
                row, text.upper() not in table.item(row, 0).text().upper()
            )

    def selected(self, name):
        table = self.tables[name]
        items = table.selectedItems()
        return items[0].data(Qt.ItemDataRole.UserRole) if items else None

    def show_detail(self, name):
        selection = self.selected(name)
        if not selection or not selection["decision"]:
            self.details[name].setPlainText("Refresh to evaluate this holding.")
            return
        r = selection["decision"]
        d = r["result"]
        sc = r["scores"]
        e = html.escape
        parts = [
            f"<h2>{e(r['symbol'])} · {e(d['action'])}</h2><p>{e(d['human_explanation'])}</p>",
            f"<p>Decision: {e(r['timestamp'])} · Price data: {e(sc.get('asof', ''))}<br>Previous: {e(r['previous_action'] or '—')} · Rescue count: {d['rescue_count']} · Can add: {'YES' if d['can_add'] else 'NO'}</p>",
            "<table cellspacing='7'><tr><th>Rule</th><th>Exact comparison</th><th>Result</th></tr>",
        ]
        for check in d["checks"]:
            label = (
                ("PASS" if check["passed"] else "FAIL")
                if check["code"].startswith("BUY_")
                else ("TRUE" if check["passed"] else "FALSE")
            )
            parts.append(
                f"<tr><td>{e(check['rule'])}</td><td>{e(check['actual'])}</td><td>{label}</td></tr>"
            )
        parts.append("</table>")
        settings = self.store.settings()
        price = sc.get("price") or sc.get("buy")
        sizing = size_position(settings["net_liq"], settings["target_positions"], price)
        parts.append(
            "<h3>Position sizing</h3><p>"
            + e(
                sizing.explanation
                if sizing
                else "Enter Net Liq in Settings; a current price or Buy level is needed."
            )
            + "</p>"
        )
        if sc.get("glyph"):
            parts.append(
                "<h3>GlyphSpec check audit</h3><pre>" + e(sc["glyph"]) + "</pre>"
            )
        if selection["holding"] and selection["holding"].get("notes"):
            parts.append("<p>Notes: " + e(selection["holding"]["notes"]) + "</p>")
        self.details[name].setHtml("".join(parts))

    def edit_holding(self):
        name = self.nav.currentItem().text()
        selection = self.selected(name) if name in self.tables else None
        symbol = (
            selection["decision"]["symbol"]
            if selection and selection["decision"]
            else ""
        )
        if HoldingDialog(self.store, symbol=symbol, parent=self).exec():
            self.load()
            self.statusBar().showMessage(
                "Portfolio saved. Refresh to evaluate the updated ownership.", 6000
            )

    def edit_selected_holding(self):
        selected = self.selected("Portfolio")
        if selected and selected["holding"]:
            if HoldingDialog(self.store, selected["holding"], parent=self).exec():
                self.load()

    def remove_selected(self):
        selected = self.selected("Portfolio")
        if selected and selected["holding"]:
            h = selected["holding"]
            self.store.remove_holding(h["symbol"], h["account"])
            self.load()

    def load_history(self):
        action = self.history_action.currentText()
        account = self.history_account.currentText()
        self.filtered_history = self.store.history(
            self.history_symbol.text(),
            "" if action == "All actions" else action,
            "" if account == "All accounts" else account,
            self.history_date.text(),
        )
        values = []
        for r in self.filtered_history:
            sc = r["scores"]
            values.append(
                (
                    [
                        r["symbol"],
                        r["timestamp"],
                        ", ".join(r["accounts"]),
                        bool(r["owned"]),
                        *[sc.get(k) for k in ("blend", "c", "h1", "h5", "state")],
                        r["action"],
                        r["previous_action"],
                        r["result"]["rescue_count"],
                    ],
                    r,
                    None,
                )
            )
        self.populate(
            "History",
            [
                "Symbol",
                "Date (UTC)",
                "Accounts",
                "Owned",
                "Blend",
                "C",
                "H1",
                "H5",
                "State",
                "Action",
                "Previous",
                "Rescues",
            ],
            values,
        )

    def export_history(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export history", "market-health-history.json", "JSON (*.json)"
        )
        if path:
            try:
                Path(path).write_text(
                    json.dumps(self.filtered_history, indent=2) + "\n", encoding="utf-8"
                )
            except OSError as exc:
                QMessageBox.warning(self, "Export", str(exc))

    def closeEvent(self, event):
        if (
            self.store.settings()["background"]
            and QSystemTrayIcon.isSystemTrayAvailable()
        ):
            self.hide()
            event.ignore()
        elif self.worker and self.worker.isRunning():
            event.ignore()
            self.status_label.setText(
                "Refresh in progress. Close after it finishes, or use the tray while monitoring."
            )
        else:
            self.quit_app()
            event.accept()

    def quit_app(self):
        if self.worker and self.worker.isRunning():
            self.status_label.setText(
                "Refresh in progress; waiting to finish before quitting."
            )
            self.worker.finished.connect(QApplication.instance().quit)
            self.timer.stop()
            return
        QApplication.instance().quit()


def main():
    parser = argparse.ArgumentParser(description="Market Health desktop")
    parser.add_argument("--database", type=Path, help="Override local SQLite path")
    parser.add_argument(
        "--refresh", action="store_true", help="Refresh after opening the window"
    )
    parser.add_argument(
        "--snapshot",
        type=Path,
        help="Explicit historical local snapshot (no live refresh or notifications)",
    )
    parser.add_argument("--smoke-test", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Market Health")
    app.setOrganizationName("MarketHealth")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    app.setWindowIcon(app_icon())
    app.setQuitOnLastWindowClosed(False)
    try:
        store = Store(args.database)
        log = configure(store.path.parent / "logs")
        log.info("startup")
        if args.snapshot:
            RefreshService(store).refresh(args.snapshot)
        window = Window(store, args.snapshot)
        window.show()
        if args.refresh:

            def start_refresh():
                window.refresh()
                if args.smoke_test:
                    window.worker.finished.connect(
                        lambda: app.exit(1 if window.worker.error else 0)
                    )

            QTimer.singleShot(0, start_refresh)
        elif args.smoke_test:
            QTimer.singleShot(500, app.quit)
        app.aboutToQuit.connect(lambda: log.info("shutdown"))
        return app.exec()
    except Exception as exc:
        logging.getLogger("market_health.desktop").exception("startup_failed")
        if not args.smoke_test:
            QMessageBox.critical(None, "Market Health", str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
