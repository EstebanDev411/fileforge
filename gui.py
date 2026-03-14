"""
gui.py
-------
FileForge — Professional PySide6 GUI.

Architecture:
  MainWindow           – root window, holds the sidebar + stacked pages
  ├── ScanPage         – folder picker + live scan progress
  ├── OrganizePage     – organize options + dry-run preview table
  ├── DupesPage        – duplicate detection + resolution controls
  ├── AutoPage         – Smart Auto Organize one-click panel
  ├── HistoryPage      – scrollable history with undo buttons
  └── SettingsPage     – edit config.json visually

Worker threads (QThread):
  ScanWorker           – runs Scanner.scan()
  OrganizeWorker       – runs Classifier + Heuristics + Organizer
  DupesWorker          – runs DuplicateDetector.find() + resolve()
  AutoWorker           – runs full Smart Auto Organize pipeline

Signals flow:
  Worker.progress  → ProgressBar.setValue()
  Worker.log_line  → LogPanel.append()
  Worker.finished  → ResultPanel.show()
  Worker.error     → ErrorDialog.show()
"""

from __future__ import annotations

try:
    from PySide6.QtCore import (
        Qt, QThread, Signal, QSize, QTimer, QSettings
    )
    from PySide6.QtGui import (
        QIcon, QFont, QColor, QPalette, QAction,
        QTextCursor, QPixmap
    )
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QGridLayout, QLabel, QPushButton, QLineEdit, QFileDialog,
        QProgressBar, QTextEdit, QTableWidget, QTableWidgetItem,
        QStackedWidget, QFrame, QSplitter, QComboBox, QCheckBox,
        QSpinBox, QGroupBox, QScrollArea, QSizePolicy, QHeaderView,
        QMessageBox, QTabWidget, QDialog, QDialogButtonBox,
        QAbstractItemView, QStatusBar, QToolBar, QTreeWidget,
        QTreeWidgetItem
    )
    _PYSIDE6_AVAILABLE = True
except ImportError:
    _PYSIDE6_AVAILABLE = False


# ──────────────────────────────────────────────────────────────────────────────
#  Theme / style constants
# ──────────────────────────────────────────────────────────────────────────────

DARK_STYLE = """
/* ── Global ─────────────────────────────────────────────────────── */
QWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
    font-family: 'Segoe UI', sans-serif;
    font-size: 13px;
}
QMainWindow {
    background-color: #181825;
}

/* ── Sidebar ─────────────────────────────────────────────────────── */
#Sidebar {
    background-color: #11111b;
    border-right: 1px solid #313244;
    min-width: 200px;
    max-width: 200px;
}
#SidebarTitle {
    font-size: 18px;
    font-weight: bold;
    color: #cba6f7;
    padding: 20px 16px 8px 16px;
}
#SidebarVersion {
    font-size: 10px;
    color: #6c7086;
    padding: 0px 16px 16px 16px;
}
#NavButton {
    background-color: transparent;
    border: none;
    border-radius: 8px;
    padding: 10px 16px;
    text-align: left;
    font-size: 13px;
    color: #a6adc8;
    margin: 2px 8px;
}
#NavButton:hover {
    background-color: #313244;
    color: #cdd6f4;
}
#NavButton[active="true"] {
    background-color: #45475a;
    color: #cba6f7;
    font-weight: bold;
}

/* ── Pages ───────────────────────────────────────────────────────── */
#PageTitle {
    font-size: 20px;
    font-weight: bold;
    color: #cdd6f4;
    padding-bottom: 4px;
}
#PageSubtitle {
    font-size: 12px;
    color: #6c7086;
    padding-bottom: 16px;
}

/* ── Cards ───────────────────────────────────────────────────────── */
#Card {
    background-color: #181825;
    border: 1px solid #313244;
    border-radius: 10px;
    padding: 16px;
}

/* ── Inputs ──────────────────────────────────────────────────────── */
QLineEdit {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 8px 12px;
    color: #cdd6f4;
    selection-background-color: #cba6f7;
}
QLineEdit:focus {
    border-color: #cba6f7;
}
QComboBox {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 6px 12px;
    color: #cdd6f4;
    min-width: 120px;
}
QComboBox::drop-down { border: none; }
QComboBox QAbstractItemView {
    background-color: #313244;
    border: 1px solid #45475a;
    color: #cdd6f4;
    selection-background-color: #45475a;
}
QSpinBox {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 6px 10px;
    color: #cdd6f4;
}
QCheckBox {
    color: #cdd6f4;
    spacing: 8px;
}
QCheckBox::indicator {
    width: 16px; height: 16px;
    border: 2px solid #45475a;
    border-radius: 4px;
    background-color: #313244;
}
QCheckBox::indicator:checked {
    background-color: #cba6f7;
    border-color: #cba6f7;
}

/* ── Buttons ─────────────────────────────────────────────────────── */
QPushButton {
    background-color: #45475a;
    border: none;
    border-radius: 7px;
    padding: 9px 20px;
    color: #cdd6f4;
    font-weight: 500;
}
QPushButton:hover  { background-color: #585b70; }
QPushButton:pressed { background-color: #313244; }
QPushButton:disabled { color: #6c7086; background-color: #2a2a3d; }

#PrimaryButton {
    background-color: #cba6f7;
    color: #1e1e2e;
    font-weight: bold;
    font-size: 14px;
    padding: 11px 28px;
}
#PrimaryButton:hover  { background-color: #d9b8ff; }
#PrimaryButton:pressed { background-color: #b89de4; }
#PrimaryButton:disabled { background-color: #45475a; color: #6c7086; }

#DangerButton {
    background-color: #f38ba8;
    color: #1e1e2e;
    font-weight: bold;
}
#DangerButton:hover { background-color: #ff9fbc; }

#SuccessButton {
    background-color: #a6e3a1;
    color: #1e1e2e;
    font-weight: bold;
}
#SuccessButton:hover { background-color: #b8ffb2; }

/* ── Progress bar ────────────────────────────────────────────────── */
QProgressBar {
    background-color: #313244;
    border: none;
    border-radius: 5px;
    height: 10px;
    text-align: center;
    color: transparent;
}
QProgressBar::chunk {
    background-color: #cba6f7;
    border-radius: 5px;
}

/* ── Table ───────────────────────────────────────────────────────── */
QTableWidget {
    background-color: #181825;
    border: 1px solid #313244;
    border-radius: 8px;
    gridline-color: #313244;
    color: #cdd6f4;
    selection-background-color: #45475a;
}
QTableWidget::item { padding: 6px 10px; }
QTableWidget::item:selected { background-color: #45475a; }
QHeaderView::section {
    background-color: #11111b;
    color: #a6adc8;
    padding: 8px 10px;
    border: none;
    border-bottom: 1px solid #313244;
    font-weight: bold;
    font-size: 11px;
    text-transform: uppercase;
}

/* ── Log panel ───────────────────────────────────────────────────── */
QTextEdit {
    background-color: #11111b;
    border: 1px solid #313244;
    border-radius: 8px;
    color: #a6e3a1;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 12px;
    padding: 8px;
}

/* ── Scrollbar ───────────────────────────────────────────────────── */
QScrollBar:vertical {
    background: #1e1e2e;
    width: 8px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #45475a;
    border-radius: 4px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover { background: #585b70; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }

/* ── Group box ───────────────────────────────────────────────────── */
QGroupBox {
    border: 1px solid #313244;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 8px;
    font-weight: bold;
    color: #a6adc8;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    top: -6px;
    padding: 0 6px;
    background-color: #1e1e2e;
    color: #cba6f7;
}

/* ── Status bar ──────────────────────────────────────────────────── */
QStatusBar {
    background-color: #11111b;
    color: #6c7086;
    border-top: 1px solid #313244;
    font-size: 11px;
    padding: 2px 8px;
}

/* ── Tabs ────────────────────────────────────────────────────────── */
QTabWidget::pane {
    border: 1px solid #313244;
    border-radius: 8px;
    background-color: #181825;
}
QTabBar::tab {
    background-color: #11111b;
    color: #6c7086;
    padding: 8px 18px;
    border-bottom: 2px solid transparent;
}
QTabBar::tab:selected {
    color: #cba6f7;
    border-bottom: 2px solid #cba6f7;
}
QTabBar::tab:hover { color: #cdd6f4; }

/* ── Divider ─────────────────────────────────────────────────────── */
#Divider {
    background-color: #313244;
    max-height: 1px;
    min-height: 1px;
}
"""


# ──────────────────────────────────────────────────────────────────────────────
#  Worker threads
# ──────────────────────────────────────────────────────────────────────────────

if _PYSIDE6_AVAILABLE:

    class ScanWorker(QThread):
        progress   = Signal(int, str)       # (files_found, current_path)
        finished   = Signal(list)           # list[FileEntry]
        error      = Signal(str)

        def __init__(self, path: str):
            super().__init__()
            self.path = path
            self._scanner = None

        def run(self):
            try:
                from core.scanner import Scanner
                self._scanner = Scanner(
                    progress_callback=lambda n, p: self.progress.emit(n, p),
                    progress_interval=200,
                )
                entries = self._scanner.scan(self.path)
                self.finished.emit(entries)
            except Exception as exc:
                self.error.emit(str(exc))

        def cancel(self):
            if self._scanner:
                self._scanner.cancel()


    class OrganizeWorker(QThread):
        progress  = Signal(int, int, str)   # (done, total, current)
        log_line  = Signal(str)
        finished  = Signal(object)          # OrganizeResult
        error     = Signal(str)

        def __init__(self, entries: list, dest: str, mode: str,
                     dry_run: bool, conflict: str, source: str):
            super().__init__()
            self.entries  = entries
            self.dest     = dest
            self.mode     = mode
            self.dry_run  = dry_run
            self.conflict = conflict
            self.source   = source
            self._org     = None

        def run(self):
            try:
                from core.classifier import Classifier
                from core.heuristics import Heuristics
                from core.organizer import Organizer
                from core.rules import RulesEngine

                self.log_line.emit("Applying custom rules…")
                engine = RulesEngine()
                stats = engine.apply_all(self.entries)
                if stats["matched"] > 0:
                    self.log_line.emit(
                        f"  {stats['matched']} files matched custom rules"
                    )

                self.log_line.emit("Classifying files…")
                clf = Classifier()
                clf.classify_all(self.entries)

                self.log_line.emit("Applying heuristics…")
                Heuristics().apply_all(self.entries)

                # Filter out files marked skip by rules
                entries_to_organize = [
                    e for e in self.entries
                    if getattr(e, "sub_category", "") != "__SKIP__"
                ]
                skipped_by_rules = len(self.entries) - len(entries_to_organize)
                if skipped_by_rules:
                    self.log_line.emit(f"  {skipped_by_rules} files skipped by rules")

                self.log_line.emit(f"Organizing {len(entries_to_organize):,} files…")
                self._org = Organizer(
                    destination=self.dest,
                    mode=self.mode,
                    dry_run=self.dry_run,
                    conflict=self.conflict,
                    progress_callback=lambda d, t, p: self.progress.emit(d, t, p),
                )
                result = self._org.organize(entries_to_organize, source_root=self.source)
                self.log_line.emit(str(result))
                self.finished.emit(result)
            except Exception as exc:
                self.error.emit(str(exc))

        def cancel(self):
            if self._org:
                self._org.cancel()


    class DupesWorker(QThread):
        progress  = Signal(int, int, str)
        log_line  = Signal(str)
        finished  = Signal(list)            # list[DuplicateGroup]
        error     = Signal(str)

        def __init__(self, entries: list):
            super().__init__()
            self.entries   = entries
            self._detector = None

        def run(self):
            try:
                from core.duplicates import DuplicateDetector
                self._detector = DuplicateDetector(
                    progress_callback=lambda d, t, p: self.progress.emit(d, t, p)
                )
                self.log_line.emit("Hashing candidates…")
                groups = self._detector.find(self.entries)
                self.log_line.emit(f"Found {len(groups)} duplicate groups")
                self.finished.emit(groups)
            except Exception as exc:
                self.error.emit(str(exc))

        def cancel(self):
            if self._detector:
                self._detector.cancel()


    class ResolveWorker(QThread):
        log_line  = Signal(str)
        finished  = Signal(object)          # DuplicateResult
        error     = Signal(str)

        def __init__(self, groups: list, dest: str, strategy: str, keep: str):
            super().__init__()
            self.groups   = groups
            self.dest     = dest
            self.strategy = strategy
            self.keep     = keep

        def run(self):
            try:
                from core.duplicates import DuplicateDetector
                det = DuplicateDetector()
                result = det.resolve(
                    self.groups,
                    destination=self.dest,
                    strategy=self.strategy,
                    keep=self.keep,
                    confirmed=True,
                )
                self.log_line.emit(str(result))
                self.finished.emit(result)
            except Exception as exc:
                self.error.emit(str(exc))


    class AutoWorker(QThread):
        stage     = Signal(str)             # stage description
        progress  = Signal(int, int, str)
        log_line  = Signal(str)
        finished  = Signal(dict)            # summary dict
        error     = Signal(str)

        def __init__(self, path: str, dest: str, dry_run: bool):
            super().__init__()
            self.path    = path
            self.dest    = dest
            self.dry_run = dry_run
            self._scanner = None
            self._org     = None

        def run(self):
            try:
                from core.scanner import Scanner
                from core.classifier import Classifier
                from core.heuristics import Heuristics
                from core.duplicates import DuplicateDetector
                from core.organizer import Organizer
                from system.config import Config

                # Stage 1: Scan
                self.stage.emit("Scanning…")
                self.log_line.emit(f"Scanning: {self.path}")
                self._scanner = Scanner(
                    progress_callback=lambda n, p: self.progress.emit(n, 0, p),
                    progress_interval=300,
                )
                entries = self._scanner.scan(self.path)
                self.log_line.emit(f"  {len(entries):,} files found")

                # Stage 2: Rules + Classify
                self.stage.emit("Applying rules…")
                self.log_line.emit("Applying custom rules…")
                from core.rules import RulesEngine
                rule_stats = RulesEngine().apply_all(entries)
                if rule_stats["matched"]:
                    self.log_line.emit(f"  {rule_stats['matched']} files matched rules")

                self.stage.emit("Classifying…")
                self.log_line.emit("Classifying + applying heuristics…")
                Classifier().classify_all(entries)
                stats = Heuristics().apply_all(entries) or {}
                self.log_line.emit("  Heuristics applied")

                # Stage 3: Duplicates
                dup_groups = []
                if Config.get("duplicates.enabled", True):
                    self.stage.emit("Detecting duplicates…")
                    self.log_line.emit("Detecting duplicates…")
                    det = DuplicateDetector(
                        progress_callback=lambda d, t, p: self.progress.emit(d, t, p)
                    )
                    dup_groups = det.find(entries)
                    self.log_line.emit(f"  {len(dup_groups)} duplicate groups")

                # Stage 4: Organize
                self.stage.emit("Organizing…")
                self.log_line.emit(f"Organizing → {self.dest}")
                self._org = Organizer(
                    destination=self.dest,
                    dry_run=self.dry_run,
                    progress_callback=lambda d, t, p: self.progress.emit(d, t, p),
                )
                org_result = self._org.organize(entries, source_root=self.path)

                # Stage 5: Resolve dupes
                freed_mb = 0.0
                if dup_groups and not self.dry_run:
                    strategy = Config.get("duplicates.strategy", "move_to_folder")
                    keep     = Config.get("duplicates.keep", "newest")
                    dup_result = det.resolve(
                        dup_groups, destination=self.dest,
                        strategy=strategy, keep=keep, confirmed=True,
                    )
                    freed_mb = dup_result.mb_freed()

                summary = {
                    "total":      len(entries),
                    "organized":  org_result.moved + org_result.copied,
                    "dup_groups": len(dup_groups),
                    "freed_mb":   freed_mb,
                    "errors":     org_result.errors,
                    "dry_run":    self.dry_run,
                }
                self.log_line.emit(f"Done. {summary['organized']:,} files organized.")
                self.finished.emit(summary)

            except Exception as exc:
                self.error.emit(str(exc))


# ──────────────────────────────────────────────────────────────────────────────
#  Reusable widgets
# ──────────────────────────────────────────────────────────────────────────────

if _PYSIDE6_AVAILABLE:

    def make_card(parent=None) -> QFrame:
        card = QFrame(parent)
        card.setObjectName("Card")
        return card

    def make_divider(parent=None) -> QFrame:
        div = QFrame(parent)
        div.setObjectName("Divider")
        div.setFrameShape(QFrame.HLine)
        return div

    def make_label(text: str, object_name: str = "", parent=None) -> QLabel:
        lbl = QLabel(text, parent)
        if object_name:
            lbl.setObjectName(object_name)
        return lbl

    def make_primary_btn(text: str, parent=None) -> QPushButton:
        btn = QPushButton(text, parent)
        btn.setObjectName("PrimaryButton")
        return btn

    def make_danger_btn(text: str, parent=None) -> QPushButton:
        btn = QPushButton(text, parent)
        btn.setObjectName("DangerButton")
        return btn

    def make_success_btn(text: str, parent=None) -> QPushButton:
        btn = QPushButton(text, parent)
        btn.setObjectName("SuccessButton")
        return btn

    class FolderPicker(QWidget):
        """Compact folder picker: [path input] [Browse] [Clear]"""
        path_changed = Signal(str)

        def __init__(self, placeholder="Select a folder…", parent=None):
            super().__init__(parent)
            layout = QHBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(8)

            self.edit = QLineEdit()
            self.edit.setPlaceholderText(placeholder)
            self.edit.textChanged.connect(self.path_changed)

            btn_browse = QPushButton("Browse…")
            btn_browse.setFixedWidth(90)
            btn_browse.clicked.connect(self._browse)

            btn_clear = QPushButton("✕")
            btn_clear.setFixedWidth(34)
            btn_clear.clicked.connect(self.edit.clear)

            layout.addWidget(self.edit)
            layout.addWidget(btn_browse)
            layout.addWidget(btn_clear)

        def _browse(self):
            path = QFileDialog.getExistingDirectory(self, "Select Folder", self.edit.text())
            if path:
                self.edit.setText(path)

        def path(self) -> str:
            return self.edit.text().strip()

        def set_path(self, p: str):
            self.edit.setText(p)

    class LogPanel(QTextEdit):
        """Auto-scrolling monospace log output panel."""

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setReadOnly(True)
            self.setMaximumHeight(200)

        def append_log(self, text: str, color: str = "#a6e3a1"):
            self.moveCursor(QTextCursor.End)
            self.insertHtml(
                f'<span style="color:{color};">▶ {text}</span><br>'
            )
            self.moveCursor(QTextCursor.End)

        def append_error(self, text: str):
            self.append_log(text, color="#f38ba8")

        def append_info(self, text: str):
            self.append_log(text, color="#89b4fa")

        def clear_log(self):
            self.clear()

    class StatCard(QFrame):
        """Small stat display: big number + label."""

        def __init__(self, label: str, value: str = "—", color: str = "#cba6f7", parent=None):
            super().__init__(parent)
            self.setObjectName("Card")
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

            layout = QVBoxLayout(self)
            layout.setContentsMargins(16, 14, 16, 14)
            layout.setSpacing(4)

            self._value_lbl = QLabel(value)
            self._value_lbl.setAlignment(Qt.AlignCenter)
            font = QFont()
            font.setPointSize(24)
            font.setBold(True)
            self._value_lbl.setFont(font)
            self._value_lbl.setStyleSheet(f"color: {color};")

            self._label_lbl = QLabel(label)
            self._label_lbl.setAlignment(Qt.AlignCenter)
            self._label_lbl.setStyleSheet("color: #6c7086; font-size: 11px;")

            layout.addWidget(self._value_lbl)
            layout.addWidget(self._label_lbl)

        def set_value(self, v: str):
            self._value_lbl.setText(v)


# ──────────────────────────────────────────────────────────────────────────────
#  Pages
# ──────────────────────────────────────────────────────────────────────────────

if _PYSIDE6_AVAILABLE:

    class ScanPage(QWidget):
        """Page 1 — Scan a directory and view results."""

        scan_complete = Signal(list)   # emits entries for use by other pages

        def __init__(self, parent=None):
            super().__init__(parent)
            self._worker = None
            self._entries = []
            self._build_ui()

        def _build_ui(self):
            root = QVBoxLayout(self)
            root.setContentsMargins(28, 24, 28, 24)
            root.setSpacing(16)

            # Header
            root.addWidget(make_label("Scan", "PageTitle"))
            root.addWidget(make_label("Scan any folder and view file statistics", "PageSubtitle"))

            # Folder picker card
            card_pick = make_card()
            cl = QVBoxLayout(card_pick)
            cl.addWidget(QLabel("Source folder"))
            self.picker = FolderPicker("C:\\Users\\…  or  /home/user/…")
            cl.addWidget(self.picker)
            root.addWidget(card_pick)

            # Controls row
            row = QHBoxLayout()
            self.btn_scan   = make_primary_btn("▶  Start Scan")
            self.btn_cancel = QPushButton("■  Cancel")
            self.btn_cancel.setEnabled(False)
            row.addWidget(self.btn_scan)
            row.addWidget(self.btn_cancel)
            row.addStretch()
            root.addLayout(row)

            # Progress
            self.progress = QProgressBar()
            self.progress.setRange(0, 0)   # indeterminate
            self.progress.setVisible(False)
            self.progress_label = QLabel("")
            self.progress_label.setStyleSheet("color: #6c7086; font-size: 11px;")
            root.addWidget(self.progress)
            root.addWidget(self.progress_label)

            # Stat cards row
            stat_row = QHBoxLayout()
            self.stat_files = StatCard("Files found", "—", "#cba6f7")
            self.stat_size  = StatCard("Total size",  "—", "#89b4fa")
            self.stat_cats  = StatCard("Categories",  "—", "#a6e3a1")
            stat_row.addWidget(self.stat_files)
            stat_row.addWidget(self.stat_size)
            stat_row.addWidget(self.stat_cats)
            root.addLayout(stat_row)

            # Category table
            cat_grp = QGroupBox("Files by Category")
            cgl = QVBoxLayout(cat_grp)
            self.cat_table = QTableWidget(0, 3)
            self.cat_table.setHorizontalHeaderLabels(["Category", "Files", "Size"])
            self.cat_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
            self.cat_table.setSelectionBehavior(QAbstractItemView.SelectRows)
            self.cat_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            self.cat_table.verticalHeader().hide()
            cgl.addWidget(self.cat_table)
            root.addWidget(cat_grp)

            # Log
            root.addWidget(make_label("Log", ""))
            self.log = LogPanel()
            root.addWidget(self.log)

            # Wiring
            self.btn_scan.clicked.connect(self._start_scan)
            self.btn_cancel.clicked.connect(self._cancel)

        def _start_scan(self):
            path = self.picker.path()
            if not path:
                QMessageBox.warning(self, "FileForge", "Please select a folder first.")
                return

            self.btn_scan.setEnabled(False)
            self.btn_cancel.setEnabled(True)
            self.progress.setVisible(True)
            self.progress.setRange(0, 0)
            self.cat_table.setRowCount(0)
            self.log.clear_log()
            self.log.append_info(f"Scanning: {path}")

            self._worker = ScanWorker(path)
            self._worker.progress.connect(self._on_progress)
            self._worker.finished.connect(self._on_finished)
            self._worker.error.connect(self._on_error)
            self._worker.start()

        def _cancel(self):
            if self._worker:
                self._worker.cancel()
            self.log.append_error("Scan cancelled by user")
            self._reset_ui()

        def _on_progress(self, n: int, path: str):
            self.progress_label.setText(
                f"{n:,} files found  ·  {path[-60:]}"
            )

        def _on_finished(self, entries: list):
            self._entries = entries
            self._reset_ui()

            if not entries:
                self.log.append_info("No files found.")
                return

            from collections import Counter
            from core.classifier import Classifier

            clf = Classifier()
            clf.classify_all(entries)

            total_size = sum(e.size for e in entries)
            cats = Counter(e.category for e in entries)

            self.stat_files.set_value(f"{len(entries):,}")
            self.stat_size.set_value(f"{total_size/(1024**3):.2f} GB")
            self.stat_cats.set_value(str(len(cats)))

            self.cat_table.setRowCount(len(cats))
            for row, (cat, count) in enumerate(
                sorted(cats.items(), key=lambda x: -x[1])
            ):
                cat_size = sum(e.size for e in entries if e.category == cat)
                self.cat_table.setItem(row, 0, QTableWidgetItem(cat))
                self.cat_table.setItem(row, 1, QTableWidgetItem(f"{count:,}"))
                self.cat_table.setItem(row, 2, QTableWidgetItem(
                    f"{cat_size/(1024**2):.1f} MB"
                ))

            self.log.append_info(
                f"Scan complete: {len(entries):,} files, "
                f"{total_size/(1024**3):.2f} GB, {len(cats)} categories"
            )
            self.scan_complete.emit(entries)

        def _on_error(self, msg: str):
            self.log.append_error(f"Error: {msg}")
            self._reset_ui()

        def _reset_ui(self):
            self.btn_scan.setEnabled(True)
            self.btn_cancel.setEnabled(False)
            self.progress.setVisible(False)
            self.progress_label.setText("")


    class OrganizePage(QWidget):
        """
        Page 2 — Classify, preview and organize files.

        Flow:
          1. User picks source + options
          2. Clicks "Preview" → table shows every file with its destination
          3. User reviews, filters, optionally excludes files
          4. Clicks "Organize Now" → executes only the previewed files
        """

        def __init__(self, parent=None):
            super().__init__(parent)
            self._entries        = []       # FileEntry list from scan/load
            self._preview_rows   = []       # list of dicts built during preview
            self._worker         = None
            self._preview_worker = None
            self._build_ui()

        def load_entries(self, entries: list):
            """Called when ScanPage finishes — pre-loads entries."""
            self._entries = entries
            self.stat_loaded.set_value(str(len(entries)))
            self.log.append_info(f"Loaded {len(entries):,} files from Scan page")
            self.btn_preview.setEnabled(True)

        # ── UI construction ────────────────────────────────────────────

        def _build_ui(self):
            root = QVBoxLayout(self)
            root.setContentsMargins(28, 24, 28, 24)
            root.setSpacing(14)

            root.addWidget(make_label("Organize", "PageTitle"))
            root.addWidget(make_label(
                "Preview exactly where every file will go, then execute with one click",
                "PageSubtitle"
            ))

            # ── Options card ───────────────────────────────────────────
            card = make_card()
            gl = QGridLayout(card)
            gl.setColumnStretch(1, 1)
            gl.setSpacing(10)

            gl.addWidget(QLabel("Source folder"), 0, 0)
            self.src_picker = FolderPicker()
            gl.addWidget(self.src_picker, 0, 1, 1, 2)

            gl.addWidget(QLabel("Destination folder"), 1, 0)
            self.dst_picker = FolderPicker("Leave empty → <source>/_Organized")
            gl.addWidget(self.dst_picker, 1, 1, 1, 2)

            gl.addWidget(QLabel("Mode"), 2, 0)
            self.combo_mode = QComboBox()
            self.combo_mode.addItems(["move", "copy"])
            gl.addWidget(self.combo_mode, 2, 1)

            gl.addWidget(QLabel("Conflict"), 3, 0)
            self.combo_conflict = QComboBox()
            self.combo_conflict.addItems(["rename", "skip", "overwrite"])
            gl.addWidget(self.combo_conflict, 3, 1)

            root.addWidget(card)

            # ── Stat cards ─────────────────────────────────────────────
            stat_row = QHBoxLayout()
            self.stat_loaded  = StatCard("Files loaded",   "0", "#cba6f7")
            self.stat_moved   = StatCard("Organized",      "—", "#a6e3a1")
            self.stat_skipped = StatCard("Skipped",        "—", "#f9e2af")
            self.stat_errors  = StatCard("Errors",         "—", "#f38ba8")
            for s in (self.stat_loaded, self.stat_moved, self.stat_skipped, self.stat_errors):
                stat_row.addWidget(s)
            root.addLayout(stat_row)

            # ── Preview table ──────────────────────────────────────────
            prev_grp = QGroupBox("Preview  —  files to organize")
            pgl = QVBoxLayout(prev_grp)
            pgl.setSpacing(8)

            # Filter row
            filter_row = QHBoxLayout()
            filter_row.addWidget(QLabel("Filter:"))
            self.filter_edit = QLineEdit()
            self.filter_edit.setPlaceholderText("Search by filename or category…")
            self.filter_edit.textChanged.connect(self._apply_filter)
            filter_row.addWidget(self.filter_edit)

            self.combo_cat_filter = QComboBox()
            self.combo_cat_filter.addItem("All categories")
            self.combo_cat_filter.currentTextChanged.connect(self._apply_filter)
            filter_row.addWidget(self.combo_cat_filter)

            self.chk_exclude_selected = QCheckBox("Exclude selected rows from organize")
            filter_row.addWidget(self.chk_exclude_selected)
            pgl.addLayout(filter_row)

            # Table
            self.preview_table = QTableWidget(0, 5)
            self.preview_table.setHorizontalHeaderLabels([
                "File", "Category", "Sub-category", "Destination", "Size"
            ])
            self.preview_table.horizontalHeader().setSectionResizeMode(
                3, QHeaderView.Stretch
            )
            self.preview_table.horizontalHeader().setSectionResizeMode(
                0, QHeaderView.ResizeToContents
            )
            self.preview_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            self.preview_table.setSelectionBehavior(QAbstractItemView.SelectRows)
            self.preview_table.verticalHeader().hide()
            self.preview_table.setAlternatingRowColors(True)
            self.preview_table.setStyleSheet(
                "QTableWidget { alternate-background-color: #1a1a2e; }"
            )
            pgl.addWidget(self.preview_table)

            # Preview footer
            self.preview_footer = QLabel("")
            self.preview_footer.setStyleSheet("color: #6c7086; font-size: 11px;")
            pgl.addWidget(self.preview_footer)
            root.addWidget(prev_grp)

            # ── Progress ───────────────────────────────────────────────
            self.progress = QProgressBar()
            self.progress.setVisible(False)
            self.progress_lbl = QLabel("")
            self.progress_lbl.setStyleSheet("color: #6c7086; font-size: 11px;")
            root.addWidget(self.progress)
            root.addWidget(self.progress_lbl)

            # ── Buttons ────────────────────────────────────────────────
            btn_row = QHBoxLayout()
            self.btn_preview  = QPushButton("🔍  Preview")
            self.btn_organize = make_primary_btn("▶  Organize Now")
            self.btn_organize.setEnabled(False)
            self.btn_cancel   = QPushButton("■  Cancel")
            self.btn_cancel.setEnabled(False)
            btn_row.addWidget(self.btn_preview)
            btn_row.addWidget(self.btn_organize)
            btn_row.addWidget(self.btn_cancel)
            btn_row.addStretch()
            root.addLayout(btn_row)

            # ── Log ────────────────────────────────────────────────────
            self.log = LogPanel()
            root.addWidget(self.log)

            # Wiring
            self.btn_preview.clicked.connect(self._run_preview)
            self.btn_organize.clicked.connect(self._start_organize)
            self.btn_cancel.clicked.connect(self._cancel)

        # ── Preview ────────────────────────────────────────────────────

        def _run_preview(self):
            src = self.src_picker.path()
            if not src and not self._entries:
                QMessageBox.warning(self, "FileForge",
                    "Select a source folder or load files from the Scan page.")
                return

            self.btn_preview.setEnabled(False)
            self.btn_organize.setEnabled(False)
            self.btn_cancel.setEnabled(True)
            self.progress.setVisible(True)
            self.progress.setRange(0, 0)
            self.preview_table.setRowCount(0)
            self.preview_footer.setText("")
            self.log.clear_log()
            self._preview_rows = []

            self._preview_worker = _PreviewWorker(
                src=src,
                dest=self._resolve_dest(src),
                existing_entries=self._entries,
            )
            self._preview_worker.progress.connect(self._on_preview_progress)
            self._preview_worker.finished.connect(self._on_preview_done)
            self._preview_worker.error.connect(self._on_error)
            self._preview_worker.start()

        def _on_preview_progress(self, done: int, total: int, current: str):
            self.progress.setRange(0, max(total, 1))
            self.progress.setValue(done)
            self.progress_lbl.setText(
                f"Classifying {done:,}/{total:,}  ·  "
                f"{__import__('pathlib').Path(current).name[:50]}"
            )

        def _on_preview_done(self, rows: list):
            self._preview_rows = rows
            self.progress.setVisible(False)
            self.progress_lbl.setText("")
            self.btn_preview.setEnabled(True)
            self.btn_cancel.setEnabled(False)

            if not rows:
                self.log.append_info("No files to organize.")
                return

            # Populate category filter
            cats = sorted({r["category"] for r in rows})
            self.combo_cat_filter.blockSignals(True)
            self.combo_cat_filter.clear()
            self.combo_cat_filter.addItem("All categories")
            for c in cats:
                self.combo_cat_filter.addItem(c)
            self.combo_cat_filter.blockSignals(False)

            self._populate_table(rows)
            self.stat_loaded.set_value(str(len(rows)))
            self.btn_organize.setEnabled(True)

            # Category breakdown log
            from collections import Counter
            cat_counts = Counter(r["category"] for r in rows)
            self.log.append_info(f"Preview ready — {len(rows):,} files:")
            for cat, count in sorted(cat_counts.items(), key=lambda x: -x[1])[:8]:
                self.log.append_info(f"  {cat:<22} {count:>6,}")
            if len(cat_counts) > 8:
                self.log.append_info(f"  … and {len(cat_counts)-8} more categories")

        def _populate_table(self, rows: list):
            """Fill the preview table from a list of row dicts."""
            self.preview_table.setRowCount(len(rows))
            for i, r in enumerate(rows):
                self.preview_table.setItem(i, 0, QTableWidgetItem(r["name"]))
                self.preview_table.setItem(i, 1, QTableWidgetItem(r["category"]))
                self.preview_table.setItem(i, 2, QTableWidgetItem(r["sub_category"]))
                self.preview_table.setItem(i, 3, QTableWidgetItem(r["destination"]))
                self.preview_table.setItem(i, 4, QTableWidgetItem(r["size_str"]))

                # Color-code by category
                color = _CATEGORY_COLORS.get(r["category"], "#45475a")
                cat_item = self.preview_table.item(i, 1)
                if cat_item:
                    cat_item.setForeground(
                        __import__('PySide6.QtGui', fromlist=['QColor']).QColor(color)
                    )

            total_size = sum(r["size"] for r in rows)
            self.preview_footer.setText(
                f"{len(rows):,} files  ·  "
                f"{total_size / (1024**3):.2f} GB total  ·  "
                f"{len({r['category'] for r in rows})} categories"
            )

        def _apply_filter(self):
            """Filter table rows by search text and/or category."""
            text    = self.filter_edit.text().lower()
            cat     = self.combo_cat_filter.currentText()
            show_all_cats = (cat == "All categories")

            filtered = [
                r for r in self._preview_rows
                if (show_all_cats or r["category"] == cat)
                and (not text or text in r["name"].lower()
                     or text in r["category"].lower()
                     or text in r["destination"].lower())
            ]
            self._populate_table(filtered)

        # ── Organize ───────────────────────────────────────────────────

        def _start_organize(self):
            if not self._preview_rows:
                QMessageBox.warning(self, "FileForge", "Run a preview first.")
                return

            # Collect entries — respect excluded selection
            excluded_names: set[str] = set()
            if self.chk_exclude_selected.isChecked():
                for idx in self.preview_table.selectedIndexes():
                    row = idx.row()
                    item = self.preview_table.item(row, 0)
                    if item:
                        excluded_names.add(item.text())

            # Get the real FileEntry objects for non-excluded files
            entries_to_organize = [
                e for e in self._entries
                if e.name not in excluded_names
            ]

            if not entries_to_organize:
                QMessageBox.warning(self, "FileForge",
                    "All files are excluded. Unselect rows or uncheck the exclude option.")
                return

            if excluded_names:
                self.log.append_info(
                    f"Excluding {len(excluded_names)} selected files — "
                    f"organizing {len(entries_to_organize):,} files"
                )

            src  = self.src_picker.path()
            dest = self._resolve_dest(src)

            self.btn_organize.setEnabled(False)
            self.btn_preview.setEnabled(False)
            self.btn_cancel.setEnabled(True)
            self.progress.setVisible(True)
            self.progress.setRange(0, len(entries_to_organize))
            self.progress.setValue(0)

            self._worker = OrganizeWorker(
                entries=entries_to_organize,
                dest=dest,
                mode=self.combo_mode.currentText(),
                dry_run=False,
                conflict=self.combo_conflict.currentText(),
                source=src,
            )
            self._worker.progress.connect(self._on_org_progress)
            self._worker.log_line.connect(self.log.append_info)
            self._worker.finished.connect(self._on_org_finished)
            self._worker.error.connect(self._on_error)
            self._worker.start()

        def _cancel(self):
            if self._worker:
                self._worker.cancel()
            if self._preview_worker:
                self._preview_worker.terminate()
            self._reset_ui()

        def _on_org_progress(self, done: int, total: int, current: str):
            self.progress.setMaximum(max(total, 1))
            self.progress.setValue(done)
            self.progress_lbl.setText(
                f"{done:,} / {total:,}  ·  "
                f"{__import__('pathlib').Path(current).name[:50]}"
            )

        def _on_org_finished(self, result):
            self.stat_moved.set_value(str(result.moved + result.copied))
            self.stat_skipped.set_value(str(result.skipped))
            self.stat_errors.set_value(str(result.errors))
            self.log.append_info(
                f"Done: {result.moved + result.copied:,} files organized, "
                f"{result.skipped} skipped, {result.errors} errors"
            )
            self._reset_ui()
            self.btn_organize.setEnabled(False)   # need new preview for next run

        def _on_error(self, msg: str):
            self.log.append_error(msg)
            self._reset_ui()

        def _reset_ui(self):
            self.btn_preview.setEnabled(True)
            self.btn_cancel.setEnabled(False)
            self.progress.setVisible(False)
            self.progress_lbl.setText("")

        def _resolve_dest(self, src: str) -> str:
            from system.config import Config
            import pathlib
            d = self.dst_picker.path()
            if d:
                return d
            base = pathlib.Path(src) if src else (
                pathlib.Path(self._entries[0].path).parent if self._entries else pathlib.Path(".")
            )
            return str(base / Config.get("organize.output_folder_name", "_Organized"))


    # Category → accent color for preview table
    _CATEGORY_COLORS = {
        "Images":        "#89b4fa",
        "Videos":        "#f38ba8",
        "Music":         "#a6e3a1",
        "Documents":     "#f9e2af",
        "Spreadsheets":  "#fab387",
        "Presentations": "#fab387",
        "Archives":      "#cba6f7",
        "Code":          "#94e2d5",
        "Executables":   "#f38ba8",
        "Fonts":         "#b4befe",
        "Other":         "#6c7086",
    }


    class _PreviewWorker(QThread):
        """
        Background worker that scans + classifies + applies heuristics
        and returns a list of preview row dicts — never touches the filesystem.
        """
        progress = Signal(int, int, str)
        finished = Signal(list)
        error    = Signal(str)

        def __init__(self, src: str, dest: str, existing_entries: list):
            super().__init__()
            self.src              = src
            self.dest             = dest
            self.existing_entries = existing_entries

        def run(self):
            try:
                import pathlib

                from core.scanner import Scanner
                from core.classifier import Classifier
                from core.heuristics import Heuristics

                # Step 1: get entries
                if self.existing_entries:
                    entries = self.existing_entries
                else:
                    scanner = Scanner(
                        progress_callback=lambda n, p: self.progress.emit(n, 0, p),
                        progress_interval=300,
                    )
                    entries = scanner.scan(self.src)

                # Step 2: classify + heuristics
                clf = Classifier()
                h   = Heuristics()
                total = len(entries)

                for i, entry in enumerate(entries):
                    clf.classify(entry)
                    h.apply(entry)
                    if i % 200 == 0:
                        self.progress.emit(i, total, entry.path)

                # Step 3: build preview rows (pure data, no I/O)
                rows = []
                dest_base = pathlib.Path(self.dest)

                for entry in entries:
                    # Compute destination path same way Organizer does
                    if entry.sub_category:
                        parts = entry.sub_category.split("/")
                        dest_folder = dest_base.joinpath(*parts)
                    else:
                        dest_folder = dest_base / entry.category

                    dest_file = dest_folder / entry.name
                    size = entry.size
                    if size < 1024:
                        size_str = f"{size} B"
                    elif size < 1024**2:
                        size_str = f"{size/1024:.1f} KB"
                    elif size < 1024**3:
                        size_str = f"{size/(1024**2):.1f} MB"
                    else:
                        size_str = f"{size/(1024**3):.2f} GB"

                    rows.append({
                        "name":        entry.name,
                        "path":        entry.path,
                        "category":    entry.category or "Other",
                        "sub_category": entry.sub_category,
                        "destination": str(dest_file),
                        "size":        size,
                        "size_str":    size_str,
                    })

                self.finished.emit(rows)

            except Exception as exc:
                self.error.emit(str(exc))




    class DupesPage(QWidget):
        """Page 3 — Find and resolve duplicate files."""

        def __init__(self, parent=None):
            super().__init__(parent)
            self._entries = []
            self._groups  = []
            self._scan_worker  = None
            self._dupes_worker = None
            self._resolve_worker = None
            self._build_ui()

        def _build_ui(self):
            root = QVBoxLayout(self)
            root.setContentsMargins(28, 24, 28, 24)
            root.setSpacing(16)

            root.addWidget(make_label("Duplicates", "PageTitle"))
            root.addWidget(make_label(
                "Find exact duplicates using SHA-256 hashing", "PageSubtitle"
            ))

            # Source card
            card = make_card()
            cl = QVBoxLayout(card)
            cl.addWidget(QLabel("Folder to check"))
            self.picker = FolderPicker()
            cl.addWidget(self.picker)
            root.addWidget(card)

            # Resolution options
            opts = make_card()
            ol = QGridLayout(opts)
            ol.setSpacing(12)

            ol.addWidget(QLabel("Strategy"), 0, 0)
            self.combo_strategy = QComboBox()
            self.combo_strategy.addItems(["move_to_folder", "delete"])
            ol.addWidget(self.combo_strategy, 0, 1)

            ol.addWidget(QLabel("Keep"), 1, 0)
            self.combo_keep = QComboBox()
            self.combo_keep.addItems(["newest", "oldest"])
            ol.addWidget(self.combo_keep, 1, 1)

            ol.addWidget(QLabel("Duplicates folder"), 2, 0)
            self.dst_picker = FolderPicker("Default: source/_Duplicates")
            ol.addWidget(self.dst_picker, 2, 1)
            root.addWidget(opts)

            # Stat row
            stat_row = QHBoxLayout()
            self.stat_groups = StatCard("Groups",       "—", "#cba6f7")
            self.stat_dupes  = StatCard("Dup files",    "—", "#f38ba8")
            self.stat_wasted = StatCard("Space wasted", "—", "#fab387")
            stat_row.addWidget(self.stat_groups)
            stat_row.addWidget(self.stat_dupes)
            stat_row.addWidget(self.stat_wasted)
            root.addLayout(stat_row)

            # Progress + buttons
            self.progress = QProgressBar()
            self.progress.setVisible(False)
            root.addWidget(self.progress)

            btn_row = QHBoxLayout()
            self.btn_find    = make_primary_btn("🔍  Find Duplicates")
            self.btn_resolve = make_danger_btn("⚡  Resolve")
            self.btn_resolve.setEnabled(False)
            self.btn_cancel  = QPushButton("■  Cancel")
            self.btn_cancel.setEnabled(False)
            btn_row.addWidget(self.btn_find)
            btn_row.addWidget(self.btn_resolve)
            btn_row.addWidget(self.btn_cancel)
            btn_row.addStretch()
            root.addLayout(btn_row)

            # Results table
            self.table = QTableWidget(0, 4)
            self.table.setHorizontalHeaderLabels(["Hash", "Files", "Wasted MB", "Sample"])
            self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
            self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            self.table.verticalHeader().hide()
            self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
            root.addWidget(self.table)

            self.log = LogPanel()
            root.addWidget(self.log)

            # Wiring
            self.btn_find.clicked.connect(self._find)
            self.btn_resolve.clicked.connect(self._resolve)
            self.btn_cancel.clicked.connect(self._cancel)

        def _find(self):
            path = self.picker.path()
            if not path:
                QMessageBox.warning(self, "FileForge", "Select a folder first.")
                return

            self.btn_find.setEnabled(False)
            self.btn_resolve.setEnabled(False)
            self.btn_cancel.setEnabled(True)
            self.progress.setVisible(True)
            self.progress.setRange(0, 0)
            self.table.setRowCount(0)
            self.log.clear_log()
            self._groups = []

            # Scan first
            self.log.append_info(f"Scanning: {path}")
            self._scan_worker = ScanWorker(path)
            self._scan_worker.finished.connect(self._on_scan_done)
            self._scan_worker.error.connect(self._on_error)
            self._scan_worker.start()

        def _on_scan_done(self, entries: list):
            from core.classifier import Classifier
            Classifier().classify_all(entries)
            self._entries = entries
            self.log.append_info(f"  {len(entries):,} files — hashing…")
            self.progress.setRange(0, len(entries))
            self._dupes_worker = DupesWorker(entries)
            self._dupes_worker.progress.connect(
                lambda d, t, p: self.progress.setValue(d)
            )
            self._dupes_worker.log_line.connect(self.log.append_info)
            self._dupes_worker.finished.connect(self._on_dupes_done)
            self._dupes_worker.error.connect(self._on_error)
            self._dupes_worker.start()

        def _on_dupes_done(self, groups: list):
            self._groups = groups
            self.progress.setVisible(False)
            self.btn_find.setEnabled(True)
            self.btn_cancel.setEnabled(False)

            if not groups:
                self.log.append_info("No duplicates found ✓")
                self.stat_groups.set_value("0")
                self.stat_dupes.set_value("0")
                self.stat_wasted.set_value("0 MB")
                return

            dup_count   = sum(len(g.files) - 1 for g in groups)
            wasted_mb   = sum(g.wasted_bytes for g in groups) / (1024**2)

            self.stat_groups.set_value(str(len(groups)))
            self.stat_dupes.set_value(str(dup_count))
            self.stat_wasted.set_value(f"{wasted_mb:.1f} MB")
            self.btn_resolve.setEnabled(True)

            # Populate table
            self.table.setRowCount(len(groups))
            for row, g in enumerate(
                sorted(groups, key=lambda x: -x.wasted_bytes)
            ):
                self.table.setItem(row, 0, QTableWidgetItem(g.hash[:16]))
                self.table.setItem(row, 1, QTableWidgetItem(str(len(g.files))))
                self.table.setItem(row, 2, QTableWidgetItem(f"{g.wasted_mb():.2f}"))
                self.table.setItem(row, 3, QTableWidgetItem(g.files[0].name))

        def _resolve(self):
            if not self._groups:
                return
            strategy = self.combo_strategy.currentText()
            if strategy == "delete":
                ans = QMessageBox.warning(
                    self, "Confirm Delete",
                    f"This will permanently delete {sum(len(g.files)-1 for g in self._groups)} "
                    "duplicate files.\n\nThis cannot be undone. Continue?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if ans != QMessageBox.Yes:
                    return

            dest = self.dst_picker.path() or self.picker.path()
            self.btn_resolve.setEnabled(False)
            self.btn_cancel.setEnabled(True)
            self.progress.setVisible(True)
            self.progress.setRange(0, 0)

            self._resolve_worker = ResolveWorker(
                groups=self._groups,
                dest=dest,
                strategy=strategy,
                keep=self.combo_keep.currentText(),
            )
            self._resolve_worker.log_line.connect(self.log.append_info)
            self._resolve_worker.finished.connect(self._on_resolved)
            self._resolve_worker.error.connect(self._on_error)
            self._resolve_worker.start()

        def _on_resolved(self, result):
            self.progress.setVisible(False)
            self.btn_cancel.setEnabled(False)
            self.log.append_info(
                f"Resolved: {result.files_processed} duplicates, "
                f"{result.mb_freed():.1f} MB freed"
            )
            self._groups = []
            self.btn_resolve.setEnabled(False)

        def _cancel(self):
            for w in (self._scan_worker, self._dupes_worker):
                if w:
                    try: w.cancel()
                    except: pass
            self._reset_ui()

        def _on_error(self, msg: str):
            self.log.append_error(msg)
            self._reset_ui()

        def _reset_ui(self):
            self.btn_find.setEnabled(True)
            self.btn_resolve.setEnabled(bool(self._groups))
            self.btn_cancel.setEnabled(False)
            self.progress.setVisible(False)


    class AutoPage(QWidget):
        """Page 4 — Smart Auto Organize."""

        def __init__(self, parent=None):
            super().__init__(parent)
            self._worker = None
            self._build_ui()

        def _build_ui(self):
            root = QVBoxLayout(self)
            root.setContentsMargins(28, 24, 28, 24)
            root.setSpacing(16)

            root.addWidget(make_label("Smart Auto Organize", "PageTitle"))
            root.addWidget(make_label(
                "One click: scan → classify → heuristics → duplicates → organize",
                "PageSubtitle"
            ))

            # Source / dest card
            card = make_card()
            gl = QGridLayout(card)
            gl.setSpacing(12)
            gl.addWidget(QLabel("Source folder"), 0, 0)
            self.src = FolderPicker()
            gl.addWidget(self.src, 0, 1)
            gl.addWidget(QLabel("Destination folder"), 1, 0)
            self.dst = FolderPicker("Leave empty → <source>/_Organized")
            gl.addWidget(self.dst, 1, 1)
            self.chk_dry = QCheckBox("Dry-run (preview without moving files)")
            gl.addWidget(self.chk_dry, 2, 0, 1, 2)
            root.addWidget(card)

            # Stage indicator
            self.stage_lbl = QLabel("")
            self.stage_lbl.setAlignment(Qt.AlignCenter)
            self.stage_lbl.setStyleSheet(
                "font-size: 15px; color: #cba6f7; font-weight: bold; padding: 8px;"
            )
            root.addWidget(self.stage_lbl)

            # Progress
            self.progress = QProgressBar()
            self.progress.setRange(0, 0)
            self.progress.setVisible(False)
            root.addWidget(self.progress)

            # Big START button
            self.btn_start  = make_primary_btn("⚡  Smart Auto Organize")
            self.btn_start.setMinimumHeight(54)
            self.btn_cancel = QPushButton("■  Cancel")
            self.btn_cancel.setEnabled(False)
            btn_row = QHBoxLayout()
            btn_row.addWidget(self.btn_start)
            btn_row.addWidget(self.btn_cancel)
            root.addLayout(btn_row)

            # Result stats
            stat_row = QHBoxLayout()
            self.stat_total   = StatCard("Total files",  "—", "#cba6f7")
            self.stat_org     = StatCard("Organized",    "—", "#a6e3a1")
            self.stat_dupes   = StatCard("Dup groups",   "—", "#f38ba8")
            self.stat_freed   = StatCard("Space freed",  "—", "#fab387")
            stat_row.addWidget(self.stat_total)
            stat_row.addWidget(self.stat_org)
            stat_row.addWidget(self.stat_dupes)
            stat_row.addWidget(self.stat_freed)
            root.addLayout(stat_row)

            self.log = LogPanel()
            self.log.setMaximumHeight(240)
            root.addWidget(self.log)
            root.addStretch()

            # Wiring
            self.btn_start.clicked.connect(self._start)
            self.btn_cancel.clicked.connect(self._cancel)

        def _start(self):
            src = self.src.path()
            if not src:
                QMessageBox.warning(self, "FileForge", "Select a source folder.")
                return

            from system.config import Config
            dest = self.dst.path() or str(
                __import__('pathlib').Path(src) /
                Config.get("organize.output_folder_name", "_Organized")
            )

            self.btn_start.setEnabled(False)
            self.btn_cancel.setEnabled(True)
            self.progress.setVisible(True)
            self.log.clear_log()
            self.stage_lbl.setText("Starting…")

            for s in (self.stat_total, self.stat_org, self.stat_dupes, self.stat_freed):
                s.set_value("…")

            self._worker = AutoWorker(
                path=src, dest=dest, dry_run=self.chk_dry.isChecked()
            )
            self._worker.stage.connect(self.stage_lbl.setText)
            self._worker.progress.connect(
                lambda d, t, p: self.progress.setValue(d) if t > 0 else None
            )
            self._worker.log_line.connect(self.log.append_info)
            self._worker.finished.connect(self._on_finished)
            self._worker.error.connect(self._on_error)
            self._worker.start()

        def _cancel(self):
            if self._worker:
                try: self._worker._scanner and self._worker._scanner.cancel()
                except: pass
            self.stage_lbl.setText("Cancelled")
            self._reset_ui()

        def _on_finished(self, summary: dict):
            dr = " (dry-run)" if summary.get("dry_run") else ""
            self.stage_lbl.setText(f"Complete{dr} ✓")
            self.stat_total.set_value(f"{summary['total']:,}")
            self.stat_org.set_value(f"{summary['organized']:,}")
            self.stat_dupes.set_value(str(summary['dup_groups']))
            self.stat_freed.set_value(f"{summary['freed_mb']:.1f} MB")
            self._reset_ui()

        def _on_error(self, msg: str):
            self.log.append_error(msg)
            self.stage_lbl.setText("Error ✗")
            self._reset_ui()

        def _reset_ui(self):
            self.btn_start.setEnabled(True)
            self.btn_cancel.setEnabled(False)
            self.progress.setVisible(False)


    class HistoryPage(QWidget):
        """Page 5 — Operation history + undo."""

        def __init__(self, parent=None):
            super().__init__(parent)
            self._build_ui()

        def _build_ui(self):
            root = QVBoxLayout(self)
            root.setContentsMargins(28, 24, 28, 24)
            root.setSpacing(16)

            root.addWidget(make_label("History", "PageTitle"))
            root.addWidget(make_label("All FileForge operations with undo support", "PageSubtitle"))

            btn_row = QHBoxLayout()
            btn_refresh = QPushButton("↻  Refresh")
            btn_clear   = make_danger_btn("🗑  Clear History")
            btn_row.addWidget(btn_refresh)
            btn_row.addStretch()
            btn_row.addWidget(btn_clear)
            root.addLayout(btn_row)

            self.table = QTableWidget(0, 6)
            self.table.setHorizontalHeaderLabels(
                ["Date", "Action", "Files", "Errors", "Source", ""]
            )
            self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
            self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            self.table.verticalHeader().hide()
            self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
            root.addWidget(self.table)

            self.log = LogPanel()
            root.addWidget(self.log)

            btn_refresh.clicked.connect(self.refresh)
            btn_clear.clicked.connect(self._clear)

            self.refresh()

        def refresh(self):
            from system.history import History
            entries = History.get_all()
            self.table.setRowCount(len(entries))
            for row, e in enumerate(entries):
                self.table.setItem(row, 0, QTableWidgetItem(e.get("timestamp", "")[:19]))
                self.table.setItem(row, 1, QTableWidgetItem(e.get("action", "")))
                self.table.setItem(row, 2, QTableWidgetItem(str(e.get("files_affected", 0))))
                self.table.setItem(row, 3, QTableWidgetItem(str(e.get("errors", 0))))
                self.table.setItem(row, 4, QTableWidgetItem(e.get("source", "")[-50:]))

                if e.get("action") in ("organize", "move"):
                    btn = QPushButton("Undo")
                    btn.setObjectName("SuccessButton" if True else "")
                    btn.setFixedWidth(60)
                    entry_id = e["id"]
                    btn.clicked.connect(lambda _, eid=entry_id: self._undo(eid))
                    self.table.setCellWidget(row, 5, btn)

        def _undo(self, entry_id: str):
            ans = QMessageBox.question(
                self, "Undo operation",
                "This will move files back to their original locations.\nContinue?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if ans != QMessageBox.Yes:
                return
            from system.history import History
            count, errors = History.undo(entry_id)
            if errors:
                QMessageBox.warning(self, "Undo", f"Reversed {count} files. {len(errors)} errors.")
            else:
                QMessageBox.information(self, "Undo", f"Successfully reversed {count} files.")
            self.refresh()

        def _clear(self):
            ans = QMessageBox.warning(
                self, "Clear History",
                "Delete all history entries? This does not affect your files.",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if ans == QMessageBox.Yes:
                from system.history import History
                History.clear()
                self.refresh()


    class SchedulerPage(QWidget):
        """Page — Scheduled Auto Organize tasks."""

        def __init__(self, parent=None):
            super().__init__(parent)
            from core.scheduler import Scheduler
            self._scheduler = Scheduler(
                on_run=self._on_task_done,
                on_log=self._append_log,
                tick_interval=30,
            )
            self._editing_id = ""
            self._build_ui()
            self._refresh_table()

        def _build_ui(self):
            root = QVBoxLayout(self)
            root.setContentsMargins(28, 24, 28, 24)
            root.setSpacing(14)

            root.addWidget(make_label("Scheduler", "PageTitle"))
            root.addWidget(make_label(
                "Auto Organize runs automatically — daily, hourly, or on startup",
                "PageSubtitle"
            ))

            splitter = QSplitter(Qt.Horizontal)

            # ── LEFT: schedule list ────────────────────────────────────
            left = QWidget()
            ll = QVBoxLayout(left)
            ll.setContentsMargins(0, 0, 8, 0)

            btn_row = QHBoxLayout()
            btn_new = make_primary_btn("＋  New schedule")
            self.btn_start_all = QPushButton("▶  Start scheduler")
            self.btn_stop_all  = QPushButton("■  Stop")
            self.btn_stop_all.setEnabled(False)
            btn_row.addWidget(btn_new)
            btn_row.addWidget(self.btn_start_all)
            btn_row.addWidget(self.btn_stop_all)
            ll.addLayout(btn_row)

            # Status dot
            self.status_lbl = QLabel("⬤  Stopped")
            self.status_lbl.setStyleSheet("color: #45475a; font-size: 12px;")
            ll.addWidget(self.status_lbl)

            self.sched_table = QTableWidget(0, 5)
            self.sched_table.setHorizontalHeaderLabels(
                ["Name", "Interval", "Next run", "Last run", "Status"]
            )
            self.sched_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
            self.sched_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            self.sched_table.setSelectionBehavior(QAbstractItemView.SelectRows)
            self.sched_table.verticalHeader().hide()
            self.sched_table.itemSelectionChanged.connect(self._on_selected)
            ll.addWidget(self.sched_table)

            tbl_btns = QHBoxLayout()
            self.btn_run_now = QPushButton("⚡  Run now")
            self.btn_delete  = QPushButton("🗑  Delete")
            self.btn_run_now.setEnabled(False)
            self.btn_delete.setEnabled(False)
            tbl_btns.addWidget(self.btn_run_now)
            tbl_btns.addWidget(self.btn_delete)
            tbl_btns.addStretch()
            ll.addLayout(tbl_btns)

            splitter.addWidget(left)

            # ── RIGHT: schedule editor ─────────────────────────────────
            right = QWidget()
            rl = QVBoxLayout(right)
            rl.setContentsMargins(8, 0, 0, 0)
            rl.setSpacing(12)

            rl.addWidget(make_label("Schedule editor", ""))

            gl = QGridLayout()
            gl.setSpacing(10)

            gl.addWidget(QLabel("Name"), 0, 0)
            self.edit_name = QLineEdit()
            self.edit_name.setPlaceholderText("e.g. Daily Downloads cleanup")
            gl.addWidget(self.edit_name, 0, 1)

            gl.addWidget(QLabel("Source folder"), 1, 0)
            self.src_picker = FolderPicker()
            gl.addWidget(self.src_picker, 1, 1)

            gl.addWidget(QLabel("Destination"), 2, 0)
            self.dst_picker = FolderPicker("Leave empty → <source>/_Organized")
            gl.addWidget(self.dst_picker, 2, 1)

            gl.addWidget(QLabel("Interval"), 3, 0)
            self.combo_interval = QComboBox()
            self.combo_interval.addItems([
                "on_startup", "minutes", "hourly", "daily", "weekly"
            ])
            self.combo_interval.currentTextChanged.connect(self._on_interval_changed)
            gl.addWidget(self.combo_interval, 3, 1)

            # Every N (minutes/hourly)
            self.every_row = QWidget()
            er = QHBoxLayout(self.every_row)
            er.setContentsMargins(0, 0, 0, 0)
            er.addWidget(QLabel("Every"))
            self.spn_every = QSpinBox()
            self.spn_every.setRange(5, 9999)
            self.spn_every.setValue(60)
            er.addWidget(self.spn_every)
            self.every_unit_lbl = QLabel("minutes")
            er.addWidget(self.every_unit_lbl)
            er.addStretch()
            gl.addWidget(QLabel(""), 4, 0)
            gl.addWidget(self.every_row, 4, 1)

            # At time (daily/weekly)
            self.time_row = QWidget()
            tr = QHBoxLayout(self.time_row)
            tr.setContentsMargins(0, 0, 0, 0)
            tr.addWidget(QLabel("At"))
            self.edit_time = QLineEdit("02:00")
            self.edit_time.setFixedWidth(70)
            tr.addWidget(self.edit_time)
            self.combo_weekday = QComboBox()
            self.combo_weekday.addItems([
                "Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"
            ])
            tr.addWidget(self.combo_weekday)
            tr.addStretch()
            gl.addWidget(QLabel(""), 5, 0)
            gl.addWidget(self.time_row, 5, 1)

            self.chk_enabled  = QCheckBox("Enabled")
            self.chk_enabled.setChecked(True)
            self.chk_dry_run  = QCheckBox("Dry-run (preview only)")
            gl.addWidget(self.chk_enabled,  6, 0, 1, 2)
            gl.addWidget(self.chk_dry_run,  7, 0, 1, 2)

            rl.addLayout(gl)
            rl.addStretch()

            save_row = QHBoxLayout()
            self.btn_save   = make_primary_btn("💾  Save schedule")
            self.btn_cancel = QPushButton("Cancel")
            save_row.addWidget(self.btn_save)
            save_row.addWidget(self.btn_cancel)
            save_row.addStretch()
            rl.addLayout(save_row)

            splitter.addWidget(right)
            splitter.setSizes([380, 360])
            root.addWidget(splitter)

            # Stats row
            stat_row = QHBoxLayout()
            self.stat_schedules = StatCard("Schedules",    "0", "#cba6f7")
            self.stat_runs      = StatCard("Total runs",   "0", "#89b4fa")
            self.stat_organized = StatCard("Files organized", "0", "#a6e3a1")
            stat_row.addWidget(self.stat_schedules)
            stat_row.addWidget(self.stat_runs)
            stat_row.addWidget(self.stat_organized)
            root.addLayout(stat_row)

            self.log = LogPanel()
            self.log.setMaximumHeight(120)
            root.addWidget(self.log)

            # Refresh timer
            self._timer = QTimer()
            self._timer.setInterval(10000)   # refresh table every 10s
            self._timer.timeout.connect(self._refresh_table)

            self._total_organized = 0
            self._total_runs      = 0

            # Update visibility for default interval
            self._on_interval_changed("on_startup")

            # Wiring
            btn_new.clicked.connect(self._new_schedule)
            self.btn_start_all.clicked.connect(self._start_scheduler)
            self.btn_stop_all.clicked.connect(self._stop_scheduler)
            self.btn_run_now.clicked.connect(self._run_now)
            self.btn_delete.clicked.connect(self._delete_schedule)
            self.btn_save.clicked.connect(self._save_schedule)
            self.btn_cancel.clicked.connect(self._clear_editor)

        # ── Table ──────────────────────────────────────────────────────

        def _refresh_table(self):
            schedules = self._scheduler.all_schedules()
            self.sched_table.setRowCount(len(schedules))

            total_runs = 0
            for i, s in enumerate(schedules):
                self.sched_table.setItem(i, 0, QTableWidgetItem(s.name))

                interval_str = {
                    "on_startup": "On startup",
                    "minutes":    f"Every {s.every_n} min",
                    "hourly":     f"Every {s.every_n}h",
                    "daily":      f"Daily {s.at_time}",
                    "weekly":     f"Weekly {['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][s.weekday]} {s.at_time}",
                }.get(s.interval, s.interval)
                self.sched_table.setItem(i, 1, QTableWidgetItem(interval_str))

                next_r = s.next_run[:16].replace("T", " ") if s.next_run else "—"
                last_r = s.last_run[:16].replace("T", " ") if s.last_run else "Never"
                self.sched_table.setItem(i, 2, QTableWidgetItem(next_r))
                self.sched_table.setItem(i, 3, QTableWidgetItem(last_r))

                status_map = {"ok": "✓ OK", "error": "✗ Error",
                               "running": "⟳ Running", "": "—"}
                status_item = QTableWidgetItem(status_map.get(s.last_status, s.last_status))
                if s.last_status == "ok":
                    status_item.setForeground(
                        __import__('PySide6.QtGui', fromlist=['QColor']).QColor("#a6e3a1")
                    )
                elif s.last_status == "error":
                    status_item.setForeground(
                        __import__('PySide6.QtGui', fromlist=['QColor']).QColor("#f38ba8")
                    )
                self.sched_table.setItem(i, 4, status_item)
                total_runs += s.run_count

            self.stat_schedules.set_value(str(len(schedules)))
            self.stat_runs.set_value(str(total_runs))
            self.stat_organized.set_value(str(self._total_organized))

        def _on_selected(self):
            row = self.sched_table.currentRow()
            schedules = self._scheduler.all_schedules()
            has = 0 <= row < len(schedules)
            self.btn_run_now.setEnabled(has)
            self.btn_delete.setEnabled(has)
            if has:
                self._load_into_editor(schedules[row])

        # ── Scheduler controls ─────────────────────────────────────────

        def _start_scheduler(self):
            self._scheduler.start()
            self.btn_start_all.setEnabled(False)
            self.btn_stop_all.setEnabled(True)
            self.status_lbl.setText("⬤  Running")
            self.status_lbl.setStyleSheet("color: #a6e3a1; font-size: 12px;")
            self._timer.start()

        def _stop_scheduler(self):
            self._scheduler.stop()
            self.btn_start_all.setEnabled(True)
            self.btn_stop_all.setEnabled(False)
            self.status_lbl.setText("⬤  Stopped")
            self.status_lbl.setStyleSheet("color: #45475a; font-size: 12px;")
            self._timer.stop()

        def _run_now(self):
            row = self.sched_table.currentRow()
            schedules = self._scheduler.all_schedules()
            if 0 <= row < len(schedules):
                s = schedules[row]
                self.log.append_info(f"Manual run: {s.name}")
                self._scheduler.run_now(s.id)

        def _on_task_done(self, schedule, result):
            self._total_runs      += 1
            self._total_organized += result.get("organized", 0)
            self._refresh_table()

        # ── Editor ─────────────────────────────────────────────────────

        def _new_schedule(self):
            self._editing_id = ""
            self.edit_name.clear()
            self.src_picker.set_path("")
            self.dst_picker.set_path("")
            self.combo_interval.setCurrentIndex(3)   # daily
            self.spn_every.setValue(60)
            self.edit_time.setText("02:00")
            self.combo_weekday.setCurrentIndex(0)
            self.chk_enabled.setChecked(True)
            self.chk_dry_run.setChecked(False)

        def _load_into_editor(self, s):
            self._editing_id = s.id
            self.edit_name.setText(s.name)
            self.src_picker.set_path(s.path)
            self.dst_picker.set_path(s.destination)
            idx = self.combo_interval.findText(s.interval)
            self.combo_interval.setCurrentIndex(max(idx, 0))
            self.spn_every.setValue(s.every_n)
            self.edit_time.setText(s.at_time)
            self.combo_weekday.setCurrentIndex(s.weekday)
            self.chk_enabled.setChecked(s.enabled)
            self.chk_dry_run.setChecked(s.dry_run)

        def _on_interval_changed(self, interval: str):
            show_every = interval in ("minutes", "hourly")
            show_time  = interval in ("daily", "weekly")
            show_day   = interval == "weekly"
            self.every_row.setVisible(show_every)
            self.time_row.setVisible(show_time)
            self.combo_weekday.setVisible(show_day)
            unit = "minutes" if interval == "minutes" else "hours"
            self.every_unit_lbl.setText(unit)

        def _save_schedule(self):
            name = self.edit_name.text().strip()
            src  = self.src_picker.path()
            if not name:
                QMessageBox.warning(self, "FileForge", "Schedule name cannot be empty.")
                return
            if not src:
                QMessageBox.warning(self, "FileForge", "Select a source folder.")
                return

            from core.scheduler import Schedule
            interval = self.combo_interval.currentText()

            s = Schedule(
                id=self._editing_id or "",
                name=name,
                path=src,
                destination=self.dst_picker.path(),
                interval=interval,
                every_n=self.spn_every.value(),
                at_time=self.edit_time.text().strip() or "02:00",
                weekday=self.combo_weekday.currentIndex(),
                enabled=self.chk_enabled.isChecked(),
                dry_run=self.chk_dry_run.isChecked(),
            )

            if self._editing_id:
                # Preserve stats from existing
                existing = self._scheduler.get(self._editing_id)
                if existing:
                    s.last_run    = existing.last_run
                    s.run_count   = existing.run_count
                    s.last_status = existing.last_status
                self._scheduler.update(s)
            else:
                self._scheduler.add(s)

            self._scheduler.save()
            self._refresh_table()
            self.log.append_info(f"Schedule saved: {name} ({interval})")
            self._clear_editor()

        def _delete_schedule(self):
            row = self.sched_table.currentRow()
            schedules = self._scheduler.all_schedules()
            if 0 <= row < len(schedules):
                s = schedules[row]
                ans = QMessageBox.question(
                    self, "Delete schedule",
                    f"Delete schedule '{s.name}'?",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No
                )
                if ans == QMessageBox.Yes:
                    self._scheduler.remove(s.id)
                    self._refresh_table()
                    self._clear_editor()

        def _clear_editor(self):
            self._editing_id = ""
            self.edit_name.clear()
            self.src_picker.set_path("")

        def _append_log(self, msg: str):
            self.log.append_info(msg)

    class RulesPage(QWidget):
        """Page — Custom rules editor."""

        def __init__(self, parent=None):
            super().__init__(parent)
            from core.rules import RulesEngine
            self._engine = RulesEngine()
            self._editing_id: str = ""
            self._build_ui()
            self._refresh_rules()

        def _build_ui(self):
            root = QVBoxLayout(self)
            root.setContentsMargins(28, 24, 28, 24)
            root.setSpacing(14)

            root.addWidget(make_label("Custom Rules", "PageTitle"))
            root.addWidget(make_label(
                "Define conditions to route files to specific folders before auto-classification",
                "PageSubtitle"
            ))

            splitter = QSplitter(Qt.Horizontal)

            # ── LEFT: rules list ───────────────────────────────────────
            left = QWidget()
            ll = QVBoxLayout(left)
            ll.setContentsMargins(0, 0, 8, 0)

            btn_row = QHBoxLayout()
            btn_new      = make_primary_btn("＋  New rule")
            btn_template = QPushButton("📋  From template")
            btn_row.addWidget(btn_new)
            btn_row.addWidget(btn_template)
            ll.addLayout(btn_row)

            self.rules_table = QTableWidget(0, 4)
            self.rules_table.setHorizontalHeaderLabels(["Name", "Conditions", "Action", "On"])
            self.rules_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
            self.rules_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            self.rules_table.setSelectionBehavior(QAbstractItemView.SelectRows)
            self.rules_table.verticalHeader().hide()
            self.rules_table.itemSelectionChanged.connect(self._on_rule_selected)
            ll.addWidget(self.rules_table)

            left_btn_row = QHBoxLayout()
            self.btn_delete   = QPushButton("🗑  Delete")
            self.btn_move_up  = QPushButton("↑")
            self.btn_move_dn  = QPushButton("↓")
            self.btn_delete.setEnabled(False)
            self.btn_move_up.setFixedWidth(36)
            self.btn_move_dn.setFixedWidth(36)
            left_btn_row.addWidget(self.btn_delete)
            left_btn_row.addStretch()
            left_btn_row.addWidget(self.btn_move_up)
            left_btn_row.addWidget(self.btn_move_dn)
            ll.addLayout(left_btn_row)

            splitter.addWidget(left)

            # ── RIGHT: rule editor ─────────────────────────────────────
            right = QWidget()
            rl = QVBoxLayout(right)
            rl.setContentsMargins(8, 0, 0, 0)
            rl.setSpacing(12)

            rl.addWidget(make_label("Rule editor", ""))

            # Name + priority
            ng = QGridLayout()
            ng.addWidget(QLabel("Name"), 0, 0)
            self.edit_name = QLineEdit()
            self.edit_name.setPlaceholderText("e.g. Invoices to Accounting")
            ng.addWidget(self.edit_name, 0, 1)
            ng.addWidget(QLabel("Priority"), 1, 0)
            self.spn_priority = QSpinBox()
            self.spn_priority.setRange(1, 999)
            self.spn_priority.setValue(50)
            self.spn_priority.setToolTip("Lower = higher priority. Runs before other rules.")
            ng.addWidget(self.spn_priority, 1, 1)
            self.chk_enabled = QCheckBox("Enabled")
            self.chk_enabled.setChecked(True)
            ng.addWidget(self.chk_enabled, 2, 0, 1, 2)
            rl.addLayout(ng)

            rl.addWidget(make_divider())

            # Conditions
            cond_hdr = QHBoxLayout()
            cond_hdr.addWidget(QLabel("Conditions"))
            self.combo_logic = QComboBox()
            self.combo_logic.addItems(["ALL must match", "ANY must match"])
            cond_hdr.addWidget(self.combo_logic)
            cond_hdr.addStretch()
            btn_add_cond = QPushButton("＋ Add condition")
            btn_add_cond.clicked.connect(self._add_condition_row)
            cond_hdr.addWidget(btn_add_cond)
            rl.addLayout(cond_hdr)

            self.cond_table = QTableWidget(0, 4)
            self.cond_table.setHorizontalHeaderLabels(["Field", "Operator", "Value", ""])
            self.cond_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
            self.cond_table.verticalHeader().hide()
            self.cond_table.setMaximumHeight(180)
            rl.addWidget(self.cond_table)

            rl.addWidget(make_divider())

            # Action
            rl.addWidget(QLabel("Action"))
            act_row = QHBoxLayout()
            self.combo_action = QComboBox()
            self.combo_action.addItems(["move_to", "skip", "rename_prefix", "rename_suffix"])
            self.combo_action.currentTextChanged.connect(self._on_action_changed)
            act_row.addWidget(self.combo_action)
            self.edit_dest = QLineEdit()
            self.edit_dest.setPlaceholderText("e.g. Documents/Invoices")
            act_row.addWidget(self.edit_dest)
            rl.addLayout(act_row)

            # Test rule
            test_row = QHBoxLayout()
            btn_test = QPushButton("🧪  Test rule")
            btn_test.clicked.connect(self._test_rule)
            self.test_picker = FolderPicker("Folder to test against…")
            test_row.addWidget(btn_test)
            test_row.addWidget(self.test_picker)
            rl.addLayout(test_row)

            self.test_result = QLabel("")
            self.test_result.setStyleSheet("color: #a6e3a1; font-size: 11px;")
            self.test_result.setWordWrap(True)
            rl.addWidget(self.test_result)

            rl.addStretch()

            # Save / cancel buttons
            save_row = QHBoxLayout()
            self.btn_save_rule   = make_primary_btn("💾  Save rule")
            self.btn_cancel_edit = QPushButton("Cancel")
            save_row.addWidget(self.btn_save_rule)
            save_row.addWidget(self.btn_cancel_edit)
            save_row.addStretch()
            rl.addLayout(save_row)

            splitter.addWidget(right)
            splitter.setSizes([340, 400])
            root.addWidget(splitter)

            self.log = LogPanel()
            self.log.setMaximumHeight(100)
            root.addWidget(self.log)

            # Wiring
            btn_new.clicked.connect(self._new_rule)
            btn_template.clicked.connect(self._from_template)
            self.btn_delete.clicked.connect(self._delete_rule)
            self.btn_move_up.clicked.connect(lambda: self._shift_priority(-5))
            self.btn_move_dn.clicked.connect(lambda: self._shift_priority(5))
            self.btn_save_rule.clicked.connect(self._save_rule)
            self.btn_cancel_edit.clicked.connect(self._clear_editor)

        # ── Rules list ─────────────────────────────────────────────────

        def _refresh_rules(self):
            rules = self._engine.all_rules()
            self.rules_table.setRowCount(len(rules))
            for i, r in enumerate(rules):
                self.rules_table.setItem(i, 0, QTableWidgetItem(r.name))
                cond_summary = f"{len(r.conditions)} cond. ({r.condition_logic})"
                self.rules_table.setItem(i, 1, QTableWidgetItem(cond_summary))
                act = r.action
                act_str = f"{act.type}: {act.destination or act.value}" if act else "—"
                self.rules_table.setItem(i, 2, QTableWidgetItem(act_str))

                chk = QCheckBox()
                chk.setChecked(r.enabled)
                rule_id = r.id
                chk.toggled.connect(lambda checked, rid=rule_id: self._toggle_rule(rid, checked))
                self.rules_table.setCellWidget(i, 3, chk)

            self.log.append_info(f"{len(rules)} rules loaded")

        def _on_rule_selected(self):
            rows = self.rules_table.selectedItems()
            if not rows:
                self.btn_delete.setEnabled(False)
                return
            self.btn_delete.setEnabled(True)
            row_idx = self.rules_table.currentRow()
            rules = self._engine.all_rules()
            if row_idx < len(rules):
                self._load_rule_into_editor(rules[row_idx])

        def _toggle_rule(self, rule_id: str, enabled: bool):
            rule = self._engine.get_rule(rule_id)
            if rule:
                rule.enabled = enabled
                self._engine.save()

        # ── Editor ─────────────────────────────────────────────────────

        def _new_rule(self):
            self._editing_id = ""
            self.edit_name.clear()
            self.spn_priority.setValue(50)
            self.chk_enabled.setChecked(True)
            self.combo_logic.setCurrentIndex(0)
            self.cond_table.setRowCount(0)
            self.combo_action.setCurrentIndex(0)
            self.edit_dest.clear()
            self.test_result.setText("")
            self._add_condition_row()

        def _load_rule_into_editor(self, rule):
            self._editing_id = rule.id
            self.edit_name.setText(rule.name)
            self.spn_priority.setValue(rule.priority)
            self.chk_enabled.setChecked(rule.enabled)
            self.combo_logic.setCurrentIndex(0 if rule.condition_logic == "ALL" else 1)

            self.cond_table.setRowCount(0)
            for cond in rule.conditions:
                self._add_condition_row(cond.field, cond.op, cond.value)

            if rule.action:
                idx = self.combo_action.findText(rule.action.type)
                self.combo_action.setCurrentIndex(max(idx, 0))
                self.edit_dest.setText(rule.action.destination or rule.action.value)

        def _add_condition_row(self, field="name", op="contains", value=""):
            row = self.cond_table.rowCount()
            self.cond_table.insertRow(row)

            field_cmb = QComboBox()
            field_cmb.addItems(["name", "filename", "extension", "size",
                                  "path", "category", "modified", "created"])
            field_cmb.setCurrentText(field)
            self.cond_table.setCellWidget(row, 0, field_cmb)

            op_cmb = QComboBox()
            op_cmb.addItems(["contains", "not_contains", "starts_with", "ends_with",
                               "equals", "not_equals", "in", "not_in",
                               "greater_than", "less_than", "greater_eq", "less_eq",
                               "regex"])
            op_cmb.setCurrentText(op)
            self.cond_table.setCellWidget(row, 1, op_cmb)

            val_edit = QLineEdit(value)
            val_edit.setPlaceholderText("value…")
            self.cond_table.setCellWidget(row, 2, val_edit)

            btn_rm = QPushButton("✕")
            btn_rm.setFixedWidth(28)
            btn_rm.clicked.connect(lambda _, r=row: self.cond_table.removeRow(r))
            self.cond_table.setCellWidget(row, 3, btn_rm)

        def _on_action_changed(self, action_type: str):
            placeholders = {
                "move_to":       "Destination folder, e.g. Documents/Invoices",
                "skip":          "(no value needed)",
                "rename_prefix": "Prefix to add, e.g. WORK_",
                "rename_suffix": "Suffix to add, e.g. _archived",
            }
            self.edit_dest.setPlaceholderText(
                placeholders.get(action_type, "value…")
            )

        def _save_rule(self):
            name = self.edit_name.text().strip()
            if not name:
                QMessageBox.warning(self, "FileForge", "Rule name cannot be empty.")
                return

            # Collect conditions
            conditions = []
            for i in range(self.cond_table.rowCount()):
                f_w  = self.cond_table.cellWidget(i, 0)
                op_w = self.cond_table.cellWidget(i, 1)
                v_w  = self.cond_table.cellWidget(i, 2)
                if f_w and op_w and v_w:
                    val = v_w.text().strip()
                    if val or op_w.currentText() == "skip":
                        from core.rules import Condition
                        conditions.append(Condition(
                            field=f_w.currentText(),
                            op=op_w.currentText(),
                            value=val,
                        ))

            if not conditions:
                QMessageBox.warning(self, "FileForge", "Add at least one condition.")
                return

            from core.rules import Rule, Action
            import uuid as _uuid

            action = Action(
                type=self.combo_action.currentText(),
                destination=self.edit_dest.text().strip(),
                value=self.edit_dest.text().strip(),
            )

            rule = Rule(
                id=self._editing_id or str(_uuid.uuid4()),
                name=name,
                enabled=self.chk_enabled.isChecked(),
                priority=self.spn_priority.value(),
                conditions=conditions,
                condition_logic="ALL" if self.combo_logic.currentIndex() == 0 else "ANY",
                action=action,
            )

            self._engine.update_rule(rule)
            self._engine.save()
            self._refresh_rules()
            self.log.append_info(f"Rule saved: {name}")
            self._clear_editor()

        def _clear_editor(self):
            self._editing_id = ""
            self.edit_name.clear()
            self.cond_table.setRowCount(0)
            self.edit_dest.clear()
            self.test_result.setText("")

        def _delete_rule(self):
            row = self.rules_table.currentRow()
            rules = self._engine.all_rules()
            if 0 <= row < len(rules):
                rule = rules[row]
                ans = QMessageBox.question(
                    self, "Delete rule",
                    f"Delete rule '{rule.name}'?",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No
                )
                if ans == QMessageBox.Yes:
                    self._engine.remove_rule(rule.id)
                    self._engine.save()
                    self._refresh_rules()
                    self._clear_editor()

        def _shift_priority(self, delta: int):
            row = self.rules_table.currentRow()
            rules = self._engine.all_rules()
            if 0 <= row < len(rules):
                rules[row].priority = max(1, rules[row].priority + delta)
                self._engine.save()
                self._refresh_rules()

        def _from_template(self):
            from core.rules import RULE_TEMPLATES, Rule, Condition, Action
            import uuid as _uuid

            items = [t["name"] for t in RULE_TEMPLATES]

            # Simple picker dialog
            dialog = QDialog(self)
            dialog.setWindowTitle("Choose a template")
            dialog.setMinimumWidth(400)
            vl = QVBoxLayout(dialog)
            vl.addWidget(QLabel("Select a preset rule to start from:"))
            lst = QTableWidget(len(items), 1)
            lst.setHorizontalHeaderLabels(["Template"])
            lst.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
            lst.verticalHeader().hide()
            lst.setEditTriggers(QAbstractItemView.NoEditTriggers)
            for i, name in enumerate(items):
                lst.setItem(i, 0, QTableWidgetItem(name))
            vl.addWidget(lst)
            btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            btns.accepted.connect(dialog.accept)
            btns.rejected.connect(dialog.reject)
            vl.addWidget(btns)

            if dialog.exec() != QDialog.Accepted:
                return

            sel = lst.currentRow()
            if sel < 0 or sel >= len(RULE_TEMPLATES):
                return

            tpl = RULE_TEMPLATES[sel]
            rule = Rule.from_dict({
                "id": str(_uuid.uuid4()),
                **tpl,
                "enabled": True,
                "priority": 50,
            })
            self._load_rule_into_editor(rule)
            self._editing_id = ""   # treat as new
            self.log.append_info(f"Template loaded: {rule.name}")

        def _test_rule(self):
            folder = self.test_picker.path()
            if not folder:
                QMessageBox.warning(self, "FileForge", "Select a folder to test against.")
                return

            from core.rules import Rule, Condition, Action
            from core.scanner import Scanner
            from core.classifier import Classifier
            import uuid as _uuid

            # Build rule from current editor state
            conditions = []
            for i in range(self.cond_table.rowCount()):
                f_w  = self.cond_table.cellWidget(i, 0)
                op_w = self.cond_table.cellWidget(i, 1)
                v_w  = self.cond_table.cellWidget(i, 2)
                if f_w and op_w and v_w and v_w.text().strip():
                    conditions.append(Condition(
                        field=f_w.currentText(),
                        op=op_w.currentText(),
                        value=v_w.text().strip(),
                    ))

            if not conditions:
                QMessageBox.warning(self, "FileForge", "Add at least one condition first.")
                return

            rule = Rule(
                id=str(_uuid.uuid4()),
                name="test",
                conditions=conditions,
                condition_logic="ALL" if self.combo_logic.currentIndex() == 0 else "ANY",
                action=Action(type="move_to", destination="test"),
            )

            entries = Scanner(progress_interval=1000).scan(folder)
            Classifier().classify_all(entries)
            matches = self._engine.test_rule(rule, entries)

            if matches:
                sample = ", ".join(matches[:5])
                extra  = f" … and {len(matches)-5} more" if len(matches) > 5 else ""
                self.test_result.setText(
                    f"✓ {len(matches)} files would match: {sample}{extra}"
                )
                self.test_result.setStyleSheet("color: #a6e3a1; font-size: 11px;")
            else:
                self.test_result.setText("No files matched in that folder.")
                self.test_result.setStyleSheet("color: #f38ba8; font-size: 11px;")

    class WatcherPage(QWidget):
        """Page — Real-time folder watcher with auto-organize."""

        def __init__(self, parent=None):
            super().__init__(parent)
            from core.watcher import Watcher
            self._watcher = Watcher(
                on_file=self._on_file_processed,
                on_log=self._append_log,
            )
            self._build_ui()

        def _build_ui(self):
            root = QVBoxLayout(self)
            root.setContentsMargins(28, 24, 28, 24)
            root.setSpacing(16)

            root.addWidget(make_label("Watcher", "PageTitle"))
            root.addWidget(make_label(
                "Monitor folders and auto-organize new files the moment they appear",
                "PageSubtitle"
            ))

            # ── Add target card ────────────────────────────────────────
            card = make_card()
            gl = QGridLayout(card)
            gl.setSpacing(12)

            gl.addWidget(QLabel("Watch folder"), 0, 0)
            self.src_picker = FolderPicker("Folder to monitor…")
            gl.addWidget(self.src_picker, 0, 1)

            gl.addWidget(QLabel("Organize into"), 1, 0)
            self.dst_picker = FolderPicker("Leave empty → <watch>/_Organized")
            gl.addWidget(self.dst_picker, 1, 1)

            self.chk_recursive = QCheckBox("Include subfolders")
            gl.addWidget(self.chk_recursive, 2, 0, 1, 2)

            btn_add = QPushButton("＋  Add target")
            btn_add.clicked.connect(self._add_target)
            gl.addWidget(btn_add, 3, 0)
            root.addWidget(card)

            # ── Targets table ──────────────────────────────────────────
            tgt_grp = QGroupBox("Watched folders")
            tgl = QVBoxLayout(tgt_grp)
            self.tgt_table = QTableWidget(0, 4)
            self.tgt_table.setHorizontalHeaderLabels(["Folder", "Destination", "Recursive", ""])
            self.tgt_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
            self.tgt_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
            self.tgt_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            self.tgt_table.verticalHeader().hide()
            tgl.addWidget(self.tgt_table)
            root.addWidget(tgt_grp)

            # ── Status + controls ──────────────────────────────────────
            stat_row = QHBoxLayout()
            self.stat_processed = StatCard("Files organized", "0", "#a6e3a1")
            self.stat_errors    = StatCard("Errors",          "0", "#f38ba8")
            self.stat_backend   = StatCard("Backend",         "—", "#89b4fa")
            stat_row.addWidget(self.stat_processed)
            stat_row.addWidget(self.stat_errors)
            stat_row.addWidget(self.stat_backend)
            root.addLayout(stat_row)

            btn_row = QHBoxLayout()
            self.btn_start = make_primary_btn("▶  Start Watching")
            self.btn_stop  = make_danger_btn("■  Stop")
            self.btn_stop.setEnabled(False)
            btn_row.addWidget(self.btn_start)
            btn_row.addWidget(self.btn_stop)
            btn_row.addStretch()

            # Status indicator
            self.status_dot = QLabel("⬤  Idle")
            self.status_dot.setStyleSheet("color: #45475a; font-size: 13px;")
            btn_row.addWidget(self.status_dot)
            root.addLayout(btn_row)

            # ── Live log ───────────────────────────────────────────────
            root.addWidget(make_label("Activity log", ""))
            self.log = LogPanel()
            self.log.setMaximumHeight(220)
            root.addWidget(self.log)

            # Timer to refresh stats
            self._timer = QTimer()
            self._timer.setInterval(1000)
            self._timer.timeout.connect(self._refresh_stats)

            # Wiring
            self.btn_start.clicked.connect(self._start)
            self.btn_stop.clicked.connect(self._stop)

            # Show backend
            from core.watcher import _WATCHDOG
            self.stat_backend.set_value("watchdog" if _WATCHDOG else "polling")

        def _add_target(self):
            src = self.src_picker.path()
            if not src:
                QMessageBox.warning(self, "FileForge", "Select a folder to watch.")
                return
            if not __import__('pathlib').Path(src).exists():
                QMessageBox.warning(self, "FileForge", f"Folder does not exist:\n{src}")
                return

            from core.watcher import WatchTarget
            target = WatchTarget(
                path=src,
                destination=self.dst_picker.path(),
                recursive=self.chk_recursive.isChecked(),
            )
            self._watcher.add(target)
            self._refresh_targets()
            self.src_picker.set_path("")
            self.dst_picker.set_path("")
            self.log.append_info(f"Added: {src}")

        def _refresh_targets(self):
            targets = self._watcher.targets()
            self.tgt_table.setRowCount(len(targets))
            for row, t in enumerate(targets):
                self.tgt_table.setItem(row, 0, QTableWidgetItem(t.path))
                self.tgt_table.setItem(row, 1, QTableWidgetItem(
                    t.destination or "→ _Organized"
                ))
                self.tgt_table.setItem(row, 2, QTableWidgetItem(
                    "Yes" if t.recursive else "No"
                ))
                btn_rm = QPushButton("Remove")
                btn_rm.setFixedWidth(70)
                path = t.path
                btn_rm.clicked.connect(lambda _, p=path: self._remove_target(p))
                self.tgt_table.setCellWidget(row, 3, btn_rm)

        def _remove_target(self, path: str):
            self._watcher.remove(path)
            self._refresh_targets()
            self.log.append_info(f"Removed: {path}")

        def _start(self):
            if not self._watcher.targets():
                QMessageBox.warning(self, "FileForge",
                    "Add at least one folder to watch first.")
                return
            self._watcher.start()
            self.btn_start.setEnabled(False)
            self.btn_stop.setEnabled(True)
            self.status_dot.setText("⬤  Watching")
            self.status_dot.setStyleSheet("color: #a6e3a1; font-size: 13px;")
            self._timer.start()

        def _stop(self):
            self._watcher.stop()
            self.btn_start.setEnabled(True)
            self.btn_stop.setEnabled(False)
            self.status_dot.setText("⬤  Idle")
            self.status_dot.setStyleSheet("color: #45475a; font-size: 13px;")
            self._timer.stop()

        def _on_file_processed(self, event):
            self._refresh_stats()

        def _append_log(self, msg: str):
            self.log.append_info(msg)

        def _refresh_stats(self):
            self.stat_processed.set_value(str(self._watcher.files_processed))
            self.stat_errors.set_value(str(self._watcher.files_errors))

        def closeEvent(self, event):
            self._watcher.stop()
            event.accept()

    class SettingsPage(QWidget):
        """Page 6 — Visual config editor."""

        def __init__(self, parent=None):
            super().__init__(parent)
            self._build_ui()

        def _build_ui(self):
            root = QVBoxLayout(self)
            root.setContentsMargins(28, 24, 28, 24)
            root.setSpacing(16)

            root.addWidget(make_label("Settings", "PageTitle"))
            root.addWidget(make_label("Configure FileForge behaviour", "PageSubtitle"))

            tabs = QTabWidget()
            tabs.addTab(self._make_general_tab(), "General")
            tabs.addTab(self._make_dupes_tab(),   "Duplicates")
            tabs.addTab(self._make_sizes_tab(),   "Large Files")
            tabs.addTab(self._make_heuristics_tab(), "Heuristics")
            tabs.addTab(self._make_language_tab(), "Language")
            root.addWidget(tabs)

            btn_row = QHBoxLayout()
            btn_save   = make_primary_btn("💾  Save")
            btn_reload = QPushButton("↻  Reload from disk")
            btn_row.addWidget(btn_save)
            btn_row.addWidget(btn_reload)
            btn_row.addStretch()
            root.addLayout(btn_row)

            btn_save.clicked.connect(self._save)
            btn_reload.clicked.connect(self._load)
            self._load()

        def _make_general_tab(self) -> QWidget:
            w = QWidget()
            gl = QGridLayout(w)
            gl.setContentsMargins(16, 16, 16, 16)
            gl.setSpacing(12)

            gl.addWidget(QLabel("Organize mode"), 0, 0)
            self.cmb_mode = QComboBox()
            self.cmb_mode.addItems(["move", "copy"])
            gl.addWidget(self.cmb_mode, 0, 1)

            gl.addWidget(QLabel("Conflict handling"), 1, 0)
            self.cmb_conflict = QComboBox()
            self.cmb_conflict.addItems(["rename", "skip", "overwrite"])
            gl.addWidget(self.cmb_conflict, 1, 1)

            gl.addWidget(QLabel("Max scan depth (-1 = unlimited)"), 2, 0)
            self.spn_depth = QSpinBox()
            self.spn_depth.setRange(-1, 999)
            gl.addWidget(self.spn_depth, 2, 1)

            self.chk_hidden = QCheckBox("Skip hidden files and folders")
            gl.addWidget(self.chk_hidden, 3, 0, 1, 2)

            gl.setRowStretch(4, 1)
            return w

        def _make_dupes_tab(self) -> QWidget:
            w = QWidget()
            gl = QGridLayout(w)
            gl.setContentsMargins(16, 16, 16, 16)
            gl.setSpacing(12)

            self.chk_dupes_enabled = QCheckBox("Enable duplicate detection")
            gl.addWidget(self.chk_dupes_enabled, 0, 0, 1, 2)

            gl.addWidget(QLabel("Default strategy"), 1, 0)
            self.cmb_dup_strategy = QComboBox()
            self.cmb_dup_strategy.addItems(["move_to_folder", "delete"])
            gl.addWidget(self.cmb_dup_strategy, 1, 1)

            gl.addWidget(QLabel("Keep"), 2, 0)
            self.cmb_dup_keep = QComboBox()
            self.cmb_dup_keep.addItems(["newest", "oldest"])
            gl.addWidget(self.cmb_dup_keep, 2, 1)

            gl.addWidget(QLabel("Min file size (bytes)"), 3, 0)
            self.spn_min_size = QSpinBox()
            self.spn_min_size.setRange(0, 10_000_000)
            self.spn_min_size.setSingleStep(1024)
            gl.addWidget(self.spn_min_size, 3, 1)

            gl.setRowStretch(4, 1)
            return w

        def _make_sizes_tab(self) -> QWidget:
            w = QWidget()
            gl = QGridLayout(w)
            gl.setContentsMargins(16, 16, 16, 16)
            gl.setSpacing(12)
            gl.addWidget(QLabel("Category"), 0, 0)
            gl.addWidget(QLabel("Threshold (MB)"), 0, 1)

            self._size_spins: dict[str, QSpinBox] = {}
            cats = ["documents", "images", "photoshop", "videos", "audio", "archives", "other"]
            for row, cat in enumerate(cats, 1):
                gl.addWidget(QLabel(cat.title()), row, 0)
                spn = QSpinBox()
                spn.setRange(1, 100_000)
                self._size_spins[cat] = spn
                gl.addWidget(spn, row, 1)

            gl.setRowStretch(len(cats) + 1, 1)
            return w

        def _make_heuristics_tab(self) -> QWidget:
            w = QWidget()
            vl = QVBoxLayout(w)
            vl.setContentsMargins(16, 16, 16, 16)

            self.chk_ss  = QCheckBox("Enable screenshot detection")
            self.chk_mem = QCheckBox("Enable meme detection")
            self.chk_lf  = QCheckBox("Enable large file detection")
            vl.addWidget(self.chk_ss)
            vl.addWidget(self.chk_mem)
            vl.addWidget(self.chk_lf)

            vl.addWidget(QLabel("Screenshot name patterns (comma-separated):"))
            self.edit_ss_patterns = QLineEdit()
            vl.addWidget(self.edit_ss_patterns)

            vl.addWidget(QLabel("Meme name patterns (comma-separated):"))
            self.edit_meme_patterns = QLineEdit()
            vl.addWidget(self.edit_meme_patterns)

            vl.addStretch()
            return w

        def _make_language_tab(self) -> QWidget:
            w = QWidget()
            vl = QVBoxLayout(w)
            vl.setContentsMargins(16, 16, 16, 16)
            vl.setSpacing(14)

            lbl = QLabel("Interface language")
            lbl.setStyleSheet("color: #a6adc8; font-size: 12px;")
            vl.addWidget(lbl)

            self.cmb_language = QComboBox()
            self.cmb_language.setMinimumWidth(200)
            vl.addWidget(self.cmb_language)

            # Populate with available languages
            try:
                from system.i18n import I18n
                for code, name in I18n.available_languages():
                    self.cmb_language.addItem(name, userData=code)
                # Select current language
                active = I18n.active_language()
                for i in range(self.cmb_language.count()):
                    if self.cmb_language.itemData(i) == active:
                        self.cmb_language.setCurrentIndex(i)
                        break
            except Exception:
                self.cmb_language.addItem("English", userData="en")

            note = QLabel("Restart the app to apply the new language.")
            note.setStyleSheet("color: #6c7086; font-size: 11px;")
            note.setWordWrap(True)
            vl.addWidget(note)

            # Live preview label
            self._lang_preview = QLabel("")
            self._lang_preview.setStyleSheet("color: #cba6f7; font-size: 12px; padding-top: 8px;")
            self._lang_preview.setWordWrap(True)
            vl.addWidget(self._lang_preview)

            self.cmb_language.currentIndexChanged.connect(self._on_language_changed)
            vl.addStretch()
            return w

        def _on_language_changed(self, _index: int):
            """Show a quick preview of the selected language."""
            code = self.cmb_language.currentData()
            try:
                from system.i18n import I18n
                preview = (
                    f"{I18n.t('scan.title', code)}  ·  "
                    f"{I18n.t('organize.title', code)}  ·  "
                    f"{I18n.t('dupes.title', code)}  ·  "
                    f"{I18n.t('history.title', code)}"
                )
                self._lang_preview.setText(preview)
            except Exception:
                pass

        def _load(self):
            from system.config import Config
            Config.reload()

            self.cmb_mode.setCurrentText(Config.get("organize.mode", "move"))
            self.cmb_conflict.setCurrentText(Config.get("organize.handle_conflicts", "rename"))
            self.spn_depth.setValue(Config.get("scan.max_depth", -1))
            self.chk_hidden.setChecked(Config.get("scan.skip_hidden", True))

            self.chk_dupes_enabled.setChecked(Config.get("duplicates.enabled", True))
            self.cmb_dup_strategy.setCurrentText(Config.get("duplicates.strategy", "move_to_folder"))
            self.cmb_dup_keep.setCurrentText(Config.get("duplicates.keep", "newest"))
            self.spn_min_size.setValue(Config.get("duplicates.min_size_bytes", 1024))

            thresholds = Config.get("large_file_thresholds", {})
            for cat, spn in self._size_spins.items():
                spn.setValue(int(thresholds.get(cat, 500)))

            self.chk_ss.setChecked(Config.get("heuristics.screenshots.enabled", True))
            self.chk_mem.setChecked(Config.get("heuristics.memes.enabled", True))
            self.chk_lf.setChecked(Config.get("large_files.enabled", True))
            self.edit_ss_patterns.setText(
                ", ".join(Config.get("heuristics.screenshots.name_patterns", []))
            )
            self.edit_meme_patterns.setText(
                ", ".join(Config.get("heuristics.memes.name_patterns", []))
            )

        def _save(self):
            from system.config import Config

            Config.set("organize.mode",              self.cmb_mode.currentText())
            Config.set("organize.handle_conflicts",  self.cmb_conflict.currentText())
            Config.set("scan.max_depth",             self.spn_depth.value())
            Config.set("scan.skip_hidden",           self.chk_hidden.isChecked())

            Config.set("duplicates.enabled",         self.chk_dupes_enabled.isChecked())
            Config.set("duplicates.strategy",        self.cmb_dup_strategy.currentText())
            Config.set("duplicates.keep",            self.cmb_dup_keep.currentText())
            Config.set("duplicates.min_size_bytes",  self.spn_min_size.value())

            for cat, spn in self._size_spins.items():
                Config.set(f"large_file_thresholds.{cat}", spn.value())

            Config.set("heuristics.screenshots.enabled", self.chk_ss.isChecked())
            Config.set("heuristics.memes.enabled",       self.chk_mem.isChecked())
            Config.set("large_files.enabled",            self.chk_lf.isChecked())

            ss_pats = [p.strip() for p in self.edit_ss_patterns.text().split(",") if p.strip()]
            Config.set("heuristics.screenshots.name_patterns", ss_pats)

            meme_pats = [p.strip() for p in self.edit_meme_patterns.text().split(",") if p.strip()]
            Config.set("heuristics.memes.name_patterns", meme_pats)

            Config.save()

            # Save selected language
            try:
                lang_code = self.cmb_language.currentData()
                if lang_code:
                    Config.set("gui.language", lang_code)
                    Config.save()
            except Exception:
                pass

            QMessageBox.information(self, "FileForge", "Settings saved successfully.")


# ──────────────────────────────────────────────────────────────────────────────
#  Main Window
# ──────────────────────────────────────────────────────────────────────────────

if _PYSIDE6_AVAILABLE:

    class MainWindow(QMainWindow):
        """
        Root window — sidebar navigation + stacked content pages.

        Layout:
            ┌─────────────┬────────────────────────────────────┐
            │             │                                     │
            │   Sidebar   │         Stacked Pages               │
            │  (nav btns) │  (Scan/Organize/Dupes/Auto/…)       │
            │             │                                     │
            └─────────────┴────────────────────────────────────┘
                              StatusBar
        """

        def __init__(self):
            super().__init__()
            from system.config import Config
            w = Config.get("gui.window_width",  1280)
            h = Config.get("gui.window_height", 800)
            self.setWindowTitle("FileForge")
            self.resize(w, h)
            self.setMinimumSize(900, 600)
            self.setStyleSheet(DARK_STYLE)

            self._build_ui()
            self._connect_pages()

        def _build_ui(self):
            # Central splitter
            central = QWidget()
            self.setCentralWidget(central)
            main_layout = QHBoxLayout(central)
            main_layout.setContentsMargins(0, 0, 0, 0)
            main_layout.setSpacing(0)

            # ── Sidebar ────────────────────────────────────────────────
            self.sidebar = QWidget()
            self.sidebar.setObjectName("Sidebar")
            sidebar_layout = QVBoxLayout(self.sidebar)
            sidebar_layout.setContentsMargins(0, 0, 0, 0)
            sidebar_layout.setSpacing(0)

            title_lbl = QLabel("FileForge")
            title_lbl.setObjectName("SidebarTitle")
            version_lbl = QLabel("v1.1.0 — Professional File Organizer")
            version_lbl.setObjectName("SidebarVersion")
            version_lbl.setWordWrap(True)
            sidebar_layout.addWidget(title_lbl)
            sidebar_layout.addWidget(version_lbl)
            sidebar_layout.addWidget(make_divider())

            nav_items = [
                ("🔍  Scan",        0),
                ("📁  Organize",    1),
                ("♻️  Duplicates",  2),
                ("⚡  Auto",         3),
                ("📋  Rules",       4),
                ("🕑  Scheduler",   5),
                ("👁  Watcher",     6),
                ("🕑  History",     7),
                ("⚙️  Settings",    8),
            ]
            self._nav_buttons: list[QPushButton] = []
            for label, idx in nav_items:
                btn = QPushButton(label)
                btn.setObjectName("NavButton")
                btn.setCheckable(False)
                btn.clicked.connect(lambda _, i=idx: self._navigate(i))
                sidebar_layout.addWidget(btn)
                self._nav_buttons.append(btn)

            sidebar_layout.addStretch()

            # Bottom info
            info = QLabel("🔒 100% local\nNo internet required")
            info.setStyleSheet("color: #6c7086; font-size: 10px; padding: 12px 16px;")
            info.setWordWrap(True)
            sidebar_layout.addWidget(info)

            main_layout.addWidget(self.sidebar)

            # ── Pages ──────────────────────────────────────────────────
            self.stack = QStackedWidget()
            self.page_scan      = ScanPage()
            self.page_organize  = OrganizePage()
            self.page_dupes     = DupesPage()
            self.page_auto      = AutoPage()
            self.page_rules     = RulesPage()
            self.page_scheduler = SchedulerPage()
            self.page_watcher   = WatcherPage()
            self.page_history   = HistoryPage()
            self.page_settings  = SettingsPage()

            for page in (
                self.page_scan, self.page_organize, self.page_dupes,
                self.page_auto, self.page_rules, self.page_scheduler,
                self.page_watcher, self.page_history, self.page_settings
            ):
                self.stack.addWidget(page)

            main_layout.addWidget(self.stack)

            # ── Status bar ─────────────────────────────────────────────
            self.status = QStatusBar()
            self.setStatusBar(self.status)
            self.status.showMessage("Ready  ·  FileForge 1.0.0")

            self._navigate(0)

        def _connect_pages(self):
            """Wire inter-page signals."""
            self.page_scan.scan_complete.connect(self.page_organize.load_entries)

        def _navigate(self, index: int):
            self.stack.setCurrentIndex(index)
            for i, btn in enumerate(self._nav_buttons):
                btn.setProperty("active", "true" if i == index else "false")
                btn.style().unpolish(btn)
                btn.style().polish(btn)

            page_names = ["Scan", "Organize", "Duplicates", "Auto",
                          "Rules", "Scheduler", "Watcher", "History", "Settings"]
            self.status.showMessage(
                f"FileForge  ·  {page_names[index]}  ·  Ready"
            )
            if index == 7:
                self.page_history.refresh()

        def closeEvent(self, event):
            from system.config import Config
            Config.set("gui.window_width",  self.width())
            Config.set("gui.window_height", self.height())
            Config.save()
            event.accept()

else:
    # Fallback if PySide6 is not installed
    class MainWindow:  # type: ignore
        def __init__(self):
            raise ImportError(
                "PySide6 is not installed.\n"
                "Install it with: pip install PySide6"
            )

