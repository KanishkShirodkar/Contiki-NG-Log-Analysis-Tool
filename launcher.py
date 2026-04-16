import sys
import os
import subprocess
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPalette, QColor, QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QLabel,
    QPushButton,
    QFileDialog,
    QMessageBox,
    QGroupBox,
)


class FileDropLineEdit(QLineEdit):
    """
    LineEdit that accepts drag‑and‑drop of a single file.
    Emits fileDropped(path) when a file is dropped.
    """
    fileDropped = pyqtSignal(str)

    def __init__(self, placeholder: str = "", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setPlaceholderText(placeholder)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if not urls:
            return
        local = urls[0]
        if local.isLocalFile():
            path = local.toLocalFile()
            self.setText(path)
            self.fileDropped.emit(path)


class LauncherWindow(QMainWindow):
    """
    Launcher UI:
      - select/drag‑drop loglistener.txt (mote output)
      - select/drag‑drop rm (radio log)
      - select/drag‑drop timedetail (timeline)
      - run: python main.py <log> <radio> <timeline>
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Cooja RPL Log Analyzer – Launcher")

        central = QWidget(self)
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        grp = QGroupBox("Select Cooja log files")
        grp_layout = QVBoxLayout(grp)
        grp_layout.setSpacing(8)

        # 1) Mote output log (loglistener.txt) – required
        self.log_edit = FileDropLineEdit(
            "Drop mote output log here (e.g. loglistener.txt) or click Browse…"
        )
        log_label = QLabel("Mote Output Log (loglistener.txt) – REQUIRED")
        log_browse = QPushButton("Browse…")
        log_browse.clicked.connect(self.browse_log)

        row1 = QHBoxLayout()
        row1.addWidget(self.log_edit, 1)
        row1.addWidget(log_browse, 0)

        grp_layout.addWidget(log_label)
        grp_layout.addLayout(row1)

        # 2) Radio log (rm) – required for radio/topology accuracy
        self.radio_edit = FileDropLineEdit(
            "Drop radio log here (e.g. rm) or click Browse…"
        )
        radio_label = QLabel("Radio Log (rm) – REQUIRED")
        radio_browse = QPushButton("Browse…")
        radio_browse.clicked.connect(self.browse_radio)

        row2 = QHBoxLayout()
        row2.addWidget(self.radio_edit, 1)
        row2.addWidget(radio_browse, 0)

        grp_layout.addWidget(radio_label)
        grp_layout.addLayout(row2)

        # 3) Timeline / timedetail – required for timeline tab
        self.timeline_edit = FileDropLineEdit(
            "Drop timeline log here (e.g. timedetail) or click Browse…"
        )
        timeline_label = QLabel("Timeline / TimeDetail (timedetail) – REQUIRED")
        timeline_browse = QPushButton("Browse…")
        timeline_browse.clicked.connect(self.browse_timeline)

        row3 = QHBoxLayout()
        row3.addWidget(self.timeline_edit, 1)
        row3.addWidget(timeline_browse, 0)

        grp_layout.addWidget(timeline_label)
        grp_layout.addLayout(row3)

        layout.addWidget(grp)

        # Launch button
        self.launch_button = QPushButton("Open Analyzer")
        self.launch_button.setDefault(True)
        self.launch_button.clicked.connect(self.run_main_script)
        layout.addWidget(self.launch_button)

        help_label = QLabel(
            "Workflow:\n"
            "1) Activate venv (source venv/bin/activate)\n"
            "2) Run this launcher (python launcher.py)\n"
            "3) Select loglistener.txt, rm, and timedetail\n"
            "4) This launcher runs: python main.py <log> <radio> <timedetail>"
        )
        help_label.setStyleSheet("color: #555; font-size: 11px;")
        layout.addWidget(help_label)

        self.resize(620, 260)

    # ── File pickers ──────────────────────────────────────────────────

    def browse_log(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select mote output log (loglistener.txt)",
            os.getcwd(),
            "Text / log files (*.txt *.log *);;All files (*)",
        )
        if path:
            self.log_edit.setText(path)

    def browse_radio(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select radio log (rm)",
            os.getcwd(),
            "Text / log files (*.txt *.log *);;All files (*)",
        )
        if path:
            self.radio_edit.setText(path)

    def browse_timeline(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select timeline log (timedetail)",
            os.getcwd(),
            "Text / log files (*.txt *.log *);;All files (*)",
        )
        if path:
            self.timeline_edit.setText(path)

    # ── Run main.py as separate process ──────────────────────────────

    def run_main_script(self):
        log_path = self.log_edit.text().strip()
        radio_path = self.radio_edit.text().strip()
        timeline_path = self.timeline_edit.text().strip()

        # Validate
        missing = []
        if not log_path:
            missing.append("mote output log (loglistener.txt)")
        if not radio_path:
            missing.append("radio log (rm)")
        if not timeline_path:
            missing.append("timeline log (timedetail)")

        if missing:
            QMessageBox.warning(
                self,
                "Missing file(s)",
                "Please select the following before continuing:\n - " + "\n - ".join(missing),
            )
            return

        for label, path in [
            ("mote output log", log_path),
            ("radio log", radio_path),
            ("timeline log", timeline_path),
        ]:
            if not os.path.isfile(path):
                QMessageBox.critical(
                    self,
                    "File not found",
                    f"The {label} file does not exist:\n{path}",
                )
                return

        # Build command: use current Python interpreter (inside venv)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        main_py = os.path.join(script_dir, "main.py")

        if not os.path.isfile(main_py):
            QMessageBox.critical(
                self,
                "main.py not found",
                f"Could not find main.py next to launcher.py:\n{main_py}",
            )
            return

        cmd = [sys.executable, main_py, log_path, radio_path, timeline_path]

        try:
            # Start analyzer in a separate process and keep launcher alive
            subprocess.Popen(cmd)
        except Exception as e:
            QMessageBox.critical(
                self,
                "Failed to start analyzer",
                f"Command:\n{' '.join(cmd)}\n\nError:\n{e}",
            )
            return


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("white"))
    palette.setColor(QPalette.ColorRole.Base, QColor("white"))
    palette.setColor(QPalette.ColorRole.Text, QColor("black"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("black"))
    app.setPalette(palette)

    win = LauncherWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()