"""
FileForge - Professional File Organizer
========================================
Entry point: detects whether to launch GUI or CLI.

Usage:
    python main.py                    → launches GUI
    python main.py scan C:\\Users     → launches CLI
"""

import sys
import os

# Ensure the project root is in sys.path when running as script
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main() -> None:
    """
    Universal entry point.
    - No arguments  → launch GUI
    - With arguments → delegate to CLI
    """
    # Bootstrap system layer first (logger + config must be ready)
    from system.logger import setup_logger
    from system.config import Config

    Config.initialize()
    setup_logger()

    if len(sys.argv) > 1:
        # CLI mode
        from cli import run_cli
        run_cli()
    else:
        # GUI mode
        try:
            from PySide6.QtWidgets import QApplication
            from gui import MainWindow

            app = QApplication(sys.argv)
            app.setApplicationName("FileForge")
            app.setApplicationVersion("1.0.0")
            app.setOrganizationName("FileForge")

            window = MainWindow()
            window.show()

            sys.exit(app.exec())

        except ImportError:
            print(
                "[FileForge] PySide6 is not installed.\n"
                "Install it with: pip install PySide6\n"
                "Or use CLI mode: python main.py --help"
            )
            sys.exit(1)


if __name__ == "__main__":
    main()
