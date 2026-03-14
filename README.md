<div align="center">

# FileForge

**A file organizer that actually does the work for you.**

Scan a folder, and FileForge figures out what everything is, moves it where it belongs, kills the duplicates, and remembers everything it did so you can undo it. Works on Windows, Linux and macOS. No internet, no tracking, no installation required if you use the `.exe`.

[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![PySide6](https://img.shields.io/badge/GUI-PySide6-41CD52?style=flat-square&logo=qt&logoColor=white)](https://doc.qt.io/qtforpython)
[![License MIT](https://img.shields.io/badge/License-MIT-cba6f7?style=flat-square)](LICENSE)
[![100% Offline](https://img.shields.io/badge/100%25-Offline-a6e3a1?style=flat-square)]()

</div>

---

## What it does

You give it a messy folder. It gives you back order.

- Scans millions of files using parallel threads
- Classifies them into 26 categories across 504+ file extensions — all editable
- Detects screenshots by filename pattern and source folder, memes by name, oversized files by category threshold
- Finds exact duplicates using a two-phase approach: first groups by size (zero disk I/O), then confirms with SHA-256 — only reads files that are actually candidates
- Organizes everything into a clean folder structure: `Images/`, `Documents/`, `Images/Screenshots/`, `Images/Memes/`, `_LargeFiles/Videos/`, etc.
- Logs every single operation. Move operations are fully reversible with one click

The whole thing runs locally. No data leaves your machine.

---

## Getting started

```bash
git clone https://github.com/EstebanDev411/fileforge.git
cd fileforge
pip install -r requirements.txt
python main.py
```

If you just want the CLI and don't need a GUI, PySide6 is optional — the core logic has zero external dependencies.

---

## GUI

Six pages accessible from the sidebar:

**Scan** — pick a folder, hit start, get a breakdown by category with file counts and sizes.

**Organize** — choose source, destination, whether to move or copy, how to handle conflicts (rename / skip / overwrite), and optionally run in dry-run mode to preview what would happen without touching anything.

**Duplicates** — finds all exact duplicate files in a folder. Shows them grouped by hash with the space wasted per group. You can move them to a `_Duplicates/` subfolder or delete them — deletion requires an explicit confirmation checkbox, it won't happen by accident.

**Auto** — one button that runs the full pipeline: scan → classify → heuristics → duplicate detection → organize. Shows a live stage indicator and progress bar.

**History** — table of every operation FileForge has ever run, with an Undo button on each row that actually works.

**Settings** — visual editor for all config options. Changes are saved to `config.json`. Supports multiple interface languages (see below).

---

## CLI

```bash
# Scan and see what's in a folder
python main.py scan C:\Users\John\Downloads

# Organize — preview first, then for real
python main.py organize C:\Downloads --dry-run
python main.py organize C:\Downloads --dest D:\Organized --mode copy

# Find duplicates
python main.py dupes C:\Users\John --strategy move_to_folder --keep newest
python main.py dupes C:\Users\John --strategy delete --confirm

# Full auto pipeline
python main.py auto C:\Users\John\Documents

# History
python main.py history --last 10
python main.py undo abc123ef
```

All subcommands support `--help`.

---

## Languages

FileForge supports multiple interface languages via XML files in the `locale/` folder. Currently ships with English and Spanish.

To add a new language, copy `locale/en.xml`, rename it to your language code (e.g. `locale/fr.xml`), translate the strings, and restart the app. It will appear automatically in Settings → Language.

```
locale/
├── en.xml   ← English (default)
└── es.xml   ← Español
```

Switching language from Settings saves the choice to `config.json` and takes effect on the next launch.

---

## Project structure

```
fileforge/
│
├── main.py              # entry point — GUI if no args, CLI otherwise
├── cli.py               # all CLI subcommands (argparse)
├── gui.py               # PySide6 interface — dark Catppuccin theme
├── paths.py             # path resolver — works both in dev and in .exe
│
├── core/
│   ├── scanner.py       # parallel os.scandir() with cancellation support
│   ├── classifier.py    # O(1) inverted index lookup from extensions.json
│   ├── heuristics.py    # screenshot / meme / large-file detection
│   ├── duplicates.py    # two-phase size → SHA-256 deduplication
│   ├── organizer.py     # move/copy engine with conflict resolution
│   └── threadpool.py    # ThreadPoolExecutor wrapper with cancel + progress
│
├── system/
│   ├── config.py        # singleton config with dot-notation access
│   ├── logger.py        # rotating file + console logger
│   ├── history.py       # operation log with undo
│   └── i18n.py          # XML-based translation engine
│
├── data/
│   └── extensions.json  # 504 extensions across 26 categories — edit freely
│
├── config/
│   └── config.json      # all runtime configuration
│
└── locale/
    ├── en.xml           # English strings
    └── es.xml           # Spanish strings
```

---

## Configuration

Everything lives in `config/config.json`. You can edit it directly or use the Settings page.

A few things worth knowing:

**Conflict handling** — when a file already exists at the destination, `rename` adds `(1)`, `(2)`, etc. to the filename. `skip` leaves it alone. `overwrite` replaces it.

**Heuristics** — the name patterns for screenshots and memes are just lists of strings to look for in the filename. You can add your own. The `source_folders` list for screenshots controls which parent directories trigger the screenshot route.

**Large file thresholds** — set per category in MB. A 600 MB image goes to `Images/` normally; a 600 MB video (threshold: 1000 MB) also goes to `Videos/` normally. Tune to your own usage.

**Duplicate detection** — can be disabled entirely. The `min_size_bytes` setting skips tiny files that would waste hashing time.

---

## Building the executable

```bash
pip install pyinstaller

pyinstaller --onefile --windowed --name FileForge \
  --add-data "data/extensions.json;data" \
  --add-data "config/config.json;config" \
  --add-data "locale;locale" \
  --add-data "resources;resources" \
  --hidden-import PySide6.QtCore \
  --hidden-import PySide6.QtGui \
  --hidden-import PySide6.QtWidgets \
  main.py
```

On Linux/macOS replace `;` with `:` in the `--add-data` arguments.

The output is `dist/FileForge.exe` — single file, no Python installation required. Config, logs and history are stored in `AppData/Roaming/FileForge/` on Windows so they survive between updates.

See [docs/INSTALL.md](docs/INSTALL.md) for the full guide with a `.spec` file, UPX compression tips, and common build errors.

---

## Adding file types

Open `data/extensions.json` and add extensions to any existing category, or create a new one:

```json
{
  "Images": [".jpg", ".png", ".heic"],
  "MyStuff": [".myext", ".custom"]
}
```

No code changes needed. The classifier hot-reloads the file.

---

## License

MIT — do whatever you want with it.

---

<div align="center">
<sub>Made by <a href="https://github.com/EstebanDev411">EstebanDev411</a></sub>
</div>
