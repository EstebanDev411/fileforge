<div align="center">

<img src="https://raw.githubusercontent.com/yourusername/fileforge/main/resources/icons/fileforge.png" alt="FileForge Logo" width="120" height="120">

# ⚒️ FileForge

**Professional File Organizer for Windows**

*Scan millions of files. Classify automatically. Detect duplicates. Never lose track of your files again.*

<br>

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![PySide6](https://img.shields.io/badge/PySide6-GUI-41CD52?style=for-the-badge&logo=qt&logoColor=white)](https://doc.qt.io/qtforpython)
[![License](https://img.shields.io/badge/License-MIT-cba6f7?style=for-the-badge)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-fab387?style=for-the-badge)]()
[![Offline](https://img.shields.io/badge/100%25-Offline-a6e3a1?style=for-the-badge)]()

<br>

![FileForge Screenshot](https://raw.githubusercontent.com/yourusername/fileforge/main/resources/preview.png)

</div>

---

## ✨ Features

| | Feature | Description |
|---|---|---|
| 🔍 | **Massive Scanner** | Handles millions of files with parallel `os.scandir()` + multithreading |
| 📂 | **Auto-Classify** | 26 categories · 504+ extensions · fully editable JSON file |
| 🧠 | **Smart Heuristics** | Detects screenshots, memes and oversized files automatically |
| ♻️ | **Duplicate Detection** | Two-phase: size grouping → SHA-256 hashing · reads only candidates |
| ⚡ | **Smart Auto Organize** | One-click full pipeline: scan → classify → dedupe → organize |
| ↩️ | **History & Undo** | Every operation is logged and move operations are fully reversible |
| 🎨 | **Dark Theme GUI** | PySide6 · Catppuccin palette · live progress bars · real-time log |
| 💻 | **Full CLI** | `scan` `organize` `dupes` `auto` `history` `undo` |
| 🔒 | **100% Local** | Zero network calls · no telemetry · no internet required |

---

## 📸 Screenshots

<div align="center">

| Auto Organize | Duplicate Detector |
|---|---|
| ![Auto Page](https://placehold.co/480x300/1e1e2e/cba6f7?text=Smart+Auto+Organize) | ![Dupes Page](https://placehold.co/480x300/1e1e2e/f38ba8?text=Duplicate+Detector) |

| Scanner | Settings |
|---|---|
| ![Scan Page](https://placehold.co/480x300/1e1e2e/89b4fa?text=File+Scanner) | ![Settings Page](https://placehold.co/480x300/1e1e2e/a6e3a1?text=Settings) |

</div>

---

## 🚀 Quick Start

### Requirements

- Python **3.11+**
- PySide6 `6.6+` *(GUI only)*
- PyInstaller `6.0+` *(building `.exe` only)*

### Install & Run

```bash
# 1. Clone the repository
git clone https://github.com/yourusername/fileforge.git
cd fileforge

# 2. Install dependencies
pip install -r requirements.txt

# 3. Launch the GUI
python main.py

# 4. Or use the CLI
python main.py --help
```

---

## 💻 CLI Reference

### `scan` — Scan a folder and view statistics

```bash
python main.py scan C:\Users\John\Downloads
python main.py scan /home/user/Documents --depth 3
```

### `organize` — Classify and move files

```bash
# Move files into organized folders (default)
python main.py organize C:\Downloads

# Copy to a custom destination, dry-run preview
python main.py organize C:\Downloads --dest D:\Organized --mode copy --dry-run
```

| Flag | Default | Description |
|---|---|---|
| `--dest` | `<src>/_Organized` | Destination root folder |
| `--mode` | `move` | `move` or `copy` |
| `--dry-run` | off | Preview without touching files |
| `--conflict` | `rename` | `rename` · `skip` · `overwrite` |

### `dupes` — Find and resolve duplicates

```bash
# Find and move duplicates
python main.py dupes C:\Users\John --strategy move_to_folder --keep newest

# Dry-run: just show what would be removed
python main.py dupes C:\Users\John --dry-run

# Permanently delete (requires --confirm for safety)
python main.py dupes C:\Users\John --strategy delete --confirm
```

### `auto` — Smart Auto Organize *(full pipeline)*

```bash
python main.py auto C:\Users\John\Documents
python main.py auto C:\Users\John\Documents --dest D:\Organized --dry-run
```

### `history` — View past operations

```bash
python main.py history
python main.py history --last 5
python main.py history --json
```

### `undo` — Reverse an organize operation

```bash
python main.py undo abc123ef
```

---

## 🗂️ Project Structure

```
FileForge/
│
├── main.py                 # Entry point — auto-detects GUI vs CLI
├── cli.py                  # CLI subcommands (argparse)
├── gui.py                  # PySide6 main window + all pages
├── requirements.txt
│
├── core/                   # Business logic — zero external deps
│   ├── scanner.py          # Multithreaded file system scanner
│   ├── classifier.py       # Extension-based classifier (O(1) lookup)
│   ├── organizer.py        # Move/copy engine with conflict resolution
│   ├── duplicates.py       # Two-phase SHA-256 duplicate detector
│   ├── heuristics.py       # Screenshot / meme / large-file detection
│   └── threadpool.py       # ThreadPoolExecutor wrapper + cancellation
│
├── system/                 # Infrastructure
│   ├── config.py           # Singleton config manager (dot-notation)
│   ├── logger.py           # Rotating file + console logger
│   └── history.py          # Operation log with undo support
│
├── data/
│   └── extensions.json     # 504 extensions across 26 categories (editable)
│
├── config/
│   └── config.json         # All runtime configuration
│
├── logs/                   # Auto-created on first run
├── history/                # Auto-created on first run
├── resources/
│   ├── icons/
│   └── themes/
└── docs/
    ├── README.md
    └── INSTALL.md
```

---

## ⚙️ Configuration

All settings live in `config/config.json` and can also be edited visually from the **Settings** page in the GUI.

```json
{
  "organize": {
    "mode": "move",
    "handle_conflicts": "rename"
  },
  "duplicates": {
    "strategy": "move_to_folder",
    "keep": "newest"
  },
  "large_file_thresholds": {
    "documents": 100,
    "images":    500,
    "videos":    1000
  },
  "heuristics": {
    "screenshots": {
      "enabled": true,
      "name_patterns": ["screenshot", "captura", "img_", "screen shot"],
      "source_folders": ["Downloads", "Desktop", "WhatsApp Images"]
    },
    "memes": {
      "enabled": true,
      "name_patterns": ["meme", "funny", "lol", "wtf", "lmao"]
    }
  }
}
```

### Adding custom extensions

Just edit `data/extensions.json` — no code changes needed:

```json
{
  "Images":     [".jpg", ".png", ".myformat"],
  "MyCategory": [".abc", ".xyz"]
}
```

---

## 🏗️ Building a standalone `.exe`

```bash
pip install pyinstaller

pyinstaller \
  --onefile \
  --windowed \
  --name FileForge \
  --add-data "data/extensions.json;data" \
  --add-data "config/config.json;config" \
  --icon resources/icons/fileforge.ico \
  main.py
```

Output: `dist/FileForge.exe` — fully portable, no Python installation required.

> See [`docs/INSTALL.md`](docs/INSTALL.md) for the full build guide including spec file, UPX compression and troubleshooting.

---

## 📊 Performance

| Metric | Result |
|---|---|
| Scan speed | ~50 000 files/second *(NVMe SSD)* |
| Duplicate phase 1 | O(n) — **zero disk I/O** |
| Duplicate phase 2 | Only candidate files hashed |
| RAM usage | Streaming scan — no full list in memory |
| Cancellation | Sub-50 ms response on all operations |

---

## 🧩 Architecture

```
┌─────────────────────────────────────────────┐
│               ENTRYPOINTS                   │
│   main.py ──── gui.py (PySide6)             │
│            └── cli.py (argparse)            │
└─────────────────┬───────────────────────────┘
                  │
┌─────────────────▼───────────────────────────┐
│                CORE LAYER                   │
│  scanner → classifier → heuristics          │
│       ↓                      ↓              │
│  duplicates            organizer            │
│       └──────── threadpool ─────┘           │
└─────────────────┬───────────────────────────┘
                  │
┌─────────────────▼───────────────────────────┐
│              SYSTEM LAYER                   │
│   config.py  ·  logger.py  ·  history.py   │
└─────────────────────────────────────────────┘
```

The **Smart Auto Organize** pipeline:

```
scan() → classify_all() → apply_all() → find() → organize()
  │           │               │            │          │
Scanner   Classifier      Heuristics   Duplicates  Organizer
```

---

## 🛠️ Tech Stack

| Component | Technology |
|---|---|
| Language | Python 3.11+ |
| GUI | PySide6 (Qt6) |
| Hashing | SHA-256 via `hashlib` |
| Concurrency | `concurrent.futures.ThreadPoolExecutor` |
| Packaging | PyInstaller |
| Storage | JSON (config, history, extensions) |
| External deps | **Zero** for core logic |

---

## 🤝 Contributing

1. Fork the repo
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Commit your changes: `git commit -m 'Add amazing feature'`
4. Push to the branch: `git push origin feature/amazing-feature`
5. Open a Pull Request

---

## 📄 License

Distributed under the **MIT License** — free for personal and commercial use.

See [`LICENSE`](LICENSE) for details.

---

<div align="center">

Made with ❤️ and Python

⭐ **Star this repo if FileForge saved you time!** ⭐

</div>
