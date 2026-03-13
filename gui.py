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

                self.log_line.emit("Classifying files…")
                clf = Classifier()
                clf.classify_all(self.entries)

                self.log_line.emit("Applying heuristics…")
                Heuristics().apply_all(self.entries)

                self.log_line.emit(f"Organizing {len(self.entries):,} files…")
                self._org = Organizer(
                    destination=self.dest,
                    mode=self.mode,
                    dry_run=self.dry_run,
                    conflict=self.conflict,
                    progress_callback=lambda d, t, p: self.progress.emit(d, t, p),
                )
                result = self._org.organize(self.entries, source_root=self.source)
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

                # Stage 2: Classify
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
        """Page 2 — Classify, apply heuristics and organize files."""

        def __init__(self, parent=None):
            super().__init__(parent)
            self._entries  = []
            self._worker   = None
            self._build_ui()

        def load_entries(self, entries: list):
            """Called when ScanPage finishes — pre-loads entries."""
            self._entries = entries
            self.stat_loaded.set_value(str(len(entries)))

        def _build_ui(self):
            root = QVBoxLayout(self)
            root.setContentsMargins(28, 24, 28, 24)
            root.setSpacing(16)

            root.addWidget(make_label("Organize", "PageTitle"))
            root.addWidget(make_label(
                "Classify files by type and move them into a structured folder", "PageSubtitle"
            ))

            # Options card
            card = make_card()
            gl = QGridLayout(card)
            gl.setColumnStretch(1, 1)
            gl.setSpacing(12)

            gl.addWidget(QLabel("Source folder"), 0, 0)
            self.src_picker = FolderPicker()
            gl.addWidget(self.src_picker, 0, 1, 1, 2)

            gl.addWidget(QLabel("Destination folder"), 1, 0)
            self.dst_picker = FolderPicker("Leave empty to use <source>/_Organized")
            gl.addWidget(self.dst_picker, 1, 1, 1, 2)

            gl.addWidget(QLabel("Mode"), 2, 0)
            self.combo_mode = QComboBox()
            self.combo_mode.addItems(["move", "copy"])
            gl.addWidget(self.combo_mode, 2, 1)

            gl.addWidget(QLabel("Conflict"), 3, 0)
            self.combo_conflict = QComboBox()
            self.combo_conflict.addItems(["rename", "skip", "overwrite"])
            gl.addWidget(self.combo_conflict, 3, 1)

            self.chk_dryrun = QCheckBox("Dry-run (preview only — no files moved)")
            gl.addWidget(self.chk_dryrun, 4, 0, 1, 3)
            root.addWidget(card)

            # Stat row
            stat_row = QHBoxLayout()
            self.stat_loaded   = StatCard("Files loaded", "0",  "#cba6f7")
            self.stat_moved    = StatCard("Organized",    "—",  "#a6e3a1")
            self.stat_errors   = StatCard("Errors",       "—",  "#f38ba8")
            stat_row.addWidget(self.stat_loaded)
            stat_row.addWidget(self.stat_moved)
            stat_row.addWidget(self.stat_errors)
            root.addLayout(stat_row)

            # Progress
            self.progress = QProgressBar()
            self.progress.setVisible(False)
            self.progress_lbl = QLabel("")
            self.progress_lbl.setStyleSheet("color: #6c7086; font-size: 11px;")
            root.addWidget(self.progress)
            root.addWidget(self.progress_lbl)

            # Buttons
            row = QHBoxLayout()
            self.btn_scan_first = QPushButton("⟳  Load from Scan page first")
            self.btn_scan_first.setEnabled(False)
            self.btn_organize = make_primary_btn("▶  Organize Now")
            self.btn_cancel   = QPushButton("■  Cancel")
            self.btn_cancel.setEnabled(False)
            row.addWidget(self.btn_organize)
            row.addWidget(self.btn_cancel)
            row.addStretch()
            root.addLayout(row)

            # Log
            self.log = LogPanel()
            root.addWidget(self.log)
            root.addStretch()

            # Wiring
            self.btn_organize.clicked.connect(self._start)
            self.btn_cancel.clicked.connect(self._cancel)

        def _start(self):
            src = self.src_picker.path()
            if not src and not self._entries:
                QMessageBox.warning(self, "FileForge",
                    "Select a source folder or load files from the Scan page.")
                return

            # If no entries pre-loaded, scan now
            if not self._entries and src:
                from core.scanner import Scanner
                from system.logger import get_logger
                log = get_logger("gui.organize")
                self.log.append_info(f"Quick scan: {src}")
                scanner = Scanner(progress_interval=500)
                try:
                    self._entries = scanner.scan(src)
                    self.stat_loaded.set_value(str(len(self._entries)))
                except Exception as exc:
                    self.log.append_error(str(exc))
                    return

            from system.config import Config
            dest = self.dst_picker.path() or \
                   str(((__import__('pathlib').Path(src or self._entries[0].path)).parent
                        if not src else __import__('pathlib').Path(src)) /
                       Config.get("organize.output_folder_name", "_Organized"))

            self.btn_organize.setEnabled(False)
            self.btn_cancel.setEnabled(True)
            self.progress.setVisible(True)
            self.progress.setValue(0)
            self.progress.setRange(0, len(self._entries))
            self.log.clear_log()

            self._worker = OrganizeWorker(
                entries=self._entries,
                dest=dest,
                mode=self.combo_mode.currentText(),
                dry_run=self.chk_dryrun.isChecked(),
                conflict=self.combo_conflict.currentText(),
                source=src,
            )
            self._worker.progress.connect(self._on_progress)
            self._worker.log_line.connect(self.log.append_info)
            self._worker.finished.connect(self._on_finished)
            self._worker.error.connect(self._on_error)
            self._worker.start()

        def _cancel(self):
            if self._worker:
                self._worker.cancel()
            self._reset_ui()

        def _on_progress(self, done: int, total: int, current: str):
            self.progress.setMaximum(max(total, 1))
            self.progress.setValue(done)
            self.progress_lbl.setText(
                f"{done:,} / {total:,}  ·  {__import__('pathlib').Path(current).name[:50]}"
            )

        def _on_finished(self, result):
            self.stat_moved.set_value(
                str(result.moved + result.copied)
            )
            self.stat_errors.set_value(str(result.errors))
            dr = " (dry-run)" if result.dry_run else ""
            self.log.append_info(
                f"Done{dr}: {result.moved + result.copied:,} files organized, "
                f"{result.errors} errors"
            )
            self._reset_ui()

        def _on_error(self, msg: str):
            self.log.append_error(msg)
            self._reset_ui()

        def _reset_ui(self):
            self.btn_organize.setEnabled(True)
            self.btn_cancel.setEnabled(False)
            self.progress.setVisible(False)
            self.progress_lbl.setText("")


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
            version_lbl = QLabel("v1.0.0 — Professional File Organizer")
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
                ("📋  History",     4),
                ("⚙️  Settings",    5),
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
            self.page_scan     = ScanPage()
            self.page_organize = OrganizePage()
            self.page_dupes    = DupesPage()
            self.page_auto     = AutoPage()
            self.page_history  = HistoryPage()
            self.page_settings = SettingsPage()

            for page in (
                self.page_scan, self.page_organize, self.page_dupes,
                self.page_auto, self.page_history, self.page_settings
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

            page_names = ["Scan", "Organize", "Duplicates", "Auto", "History", "Settings"]
            self.status.showMessage(
                f"FileForge  ·  {page_names[index]}  ·  Ready"
            )

            # Refresh history when navigating to it
            if index == 4:
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

