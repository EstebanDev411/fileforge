# ⚒️ FileForge

**Organizador profesional de archivos para Windows, Linux y macOS**

*Escanea millones de archivos. Clasifica automáticamente. Detecta duplicados. Nunca pierdas el rastro de tus archivos.*

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![PySide6](https://img.shields.io/badge/PySide6-GUI-41CD52?style=for-the-badge&logo=qt&logoColor=white)](https://doc.qt.io/qtforpython)
[![License](https://img.shields.io/badge/License-MIT-cba6f7?style=for-the-badge)](./LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-fab387?style=for-the-badge)](.)
[![Offline](https://img.shields.io/badge/100%25-Offline-a6e3a1?style=for-the-badge)](.)

---

## ✨ Características

| | Característica | Descripción |
|---|---|---|
| 🔍 | **Escáner masivo** | Maneja millones de archivos con `os.scandir()` paralelo + multihilos |
| 📂 | **Clasificación automática** | 26 categorías · 500+ extensiones · archivo JSON completamente editable |
| 🧠 | **Heurísticas inteligentes** | Detecta capturas de pantalla, memes y archivos sobredimensionados automáticamente |
| ♻️ | **Detección de duplicados** | Dos fases: agrupación por tamaño → hashing SHA-256 · solo lee candidatos |
| ⚡ | **Auto organización** | Pipeline completo en un clic: escanear → clasificar → deduplicar → organizar |
| ↩️ | **Historial y deshacer** | Cada operación queda registrada y las operaciones de movimiento son completamente reversibles |
| 🎨 | **GUI con tema oscuro** | PySide6 · paleta Catppuccin · barras de progreso en vivo · log en tiempo real |
| 💻 | **CLI completo** | `scan` `organize` `dupes` `auto` `history` `undo` |
| 🔒 | **100% local** | Sin llamadas a red · sin telemetría · no requiere internet |

---

## 🚀 Inicio rápido

### Requisitos

- Python **3.11+**
- PySide6 `6.6+` *(solo GUI)*
- PyInstaller `6.0+` *(solo para compilar el `.exe`)*

### Instalar y ejecutar

```bash
# 1. Clonar el repositorio
git clone https://github.com/EstebanDev411/fileforge.git
cd fileforge

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Lanzar la GUI
python main.py

# 4. O usar la CLI
python main.py --help
```

---

## 💻 Referencia CLI

### `scan` — Escanear una carpeta y ver estadísticas

```bash
python main.py scan C:\Users\John\Downloads
python main.py scan /home/user/Documents --depth 3
```

### `organize` — Clasificar y mover archivos

```bash
# Mover archivos a carpetas organizadas (por defecto)
python main.py organize C:\Downloads

# Copiar a destino personalizado con vista previa
python main.py organize C:\Downloads --dest D:\Organizado --mode copy --dry-run
```

| Flag | Por defecto | Descripción |
|---|---|---|
| `--dest` | `<src>/_Organized` | Carpeta raíz de destino |
| `--mode` | `move` | `move` o `copy` |
| `--dry-run` | desactivado | Vista previa sin mover archivos |
| `--conflict` | `rename` | `rename` · `skip` · `overwrite` |

### `dupes` — Encontrar y resolver duplicados

```bash
# Encontrar y mover duplicados
python main.py dupes C:\Users\John --strategy move_to_folder --keep newest

# Solo mostrar qué se eliminaría
python main.py dupes C:\Users\John --dry-run

# Eliminar permanentemente (requiere --confirm)
python main.py dupes C:\Users\John --strategy delete --confirm
```

### `auto` — Auto organización completa *(pipeline completo)*

```bash
python main.py auto C:\Users\John\Documents
python main.py auto C:\Users\John\Documents --dest D:\Organizado --dry-run
```

### `history` — Ver operaciones pasadas

```bash
python main.py history
python main.py history --last 5
python main.py history --json
```

### `undo` — Revertir una operación

```bash
python main.py undo abc123ef
```

---

## 🗂️ Estructura del proyecto

```
fileforge/
│
├── main.py                 # Punto de entrada — auto-detecta GUI vs CLI
├── cli.py                  # Subcomandos CLI (argparse)
├── gui.py                  # Ventana principal PySide6 + todas las páginas
├── paths.py                # Gestión centralizada de rutas del proyecto
├── requirements.txt        # Dependencias Python
│
├── core/                   # Lógica de negocio — sin dependencias externas
│   ├── scanner.py          # Escáner de sistema de archivos multihilo
│   ├── classifier.py       # Clasificador por extensión (lookup O(1))
│   ├── organizer.py        # Motor de mover/copiar con resolución de conflictos
│   ├── duplicates.py       # Detector de duplicados SHA-256 en dos fases
│   ├── heuristics.py       # Detección de capturas, memes y archivos grandes
│   └── threadpool.py       # Wrapper de ThreadPoolExecutor con cancelación
│
├── system/                 # Infraestructura
│   ├── config.py           # Gestor de configuración Singleton (notación de punto)
│   ├── logger.py           # Logger rotativo a archivo y consola
│   └── history.py          # Registro de operaciones con soporte de deshacer
│
├── data/
│   └── extensions.json     # 500+ extensiones en 26 categorías (editable)
│
├── config/
│   └── config.json         # Configuración de ejecución
│
├── history/                # Se crea automáticamente en el primer uso
├── dist/                   # Ejecutables compilados (PyInstaller)
├── .gitignore
└── LICENSE
```

---

## ⚙️ Configuración

Toda la configuración vive en `config/config.json` y también puede editarse visualmente desde la página de **Ajustes** en la GUI.

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

### Agregar extensiones personalizadas

Edita `data/extensions.json` — sin cambios en el código:

```json
{
  "Images":      [".jpg", ".png", ".miFormato"],
  "MiCategoria": [".abc", ".xyz"]
}
```

---

## 🏗️ Arquitectura

```
┌─────────────────────────────────────────────┐
│               PUNTOS DE ENTRADA             │
│   main.py ──── gui.py  (PySide6)            │
│            └── cli.py  (argparse)           │
└─────────────────┬───────────────────────────┘
                  │
┌─────────────────▼───────────────────────────┐
│                CAPA CORE                    │
│  scanner → classifier → heuristics         │
│       ↓                      ↓             │
│  duplicates            organizer           │
│       └──────── threadpool ─────┘          │
└─────────────────┬───────────────────────────┘
                  │
┌─────────────────▼───────────────────────────┐
│              CAPA SYSTEM                    │
│   config.py  ·  logger.py  ·  history.py   │
└─────────────────────────────────────────────┘
```

Pipeline de **Smart Auto Organize**:

```
scan() → classify_all() → apply_all() → find() → organize()
  │           │               │            │          │
Scanner   Classifier      Heuristics   Duplicates  Organizer
```

---

## 📊 Rendimiento

| Métrica | Resultado |
|---|---|
| Velocidad de escaneo | ~50 000 archivos/segundo *(NVMe SSD)* |
| Duplicados fase 1 | O(n) — **sin I/O en disco** |
| Duplicados fase 2 | Solo archivos candidatos son hasheados |
| Uso de RAM | Escaneo en streaming — sin lista completa en memoria |
| Cancelación | < 50 ms de respuesta en todas las operaciones |

---

## 🛠️ Compilar ejecutable `.exe`

```bash
pip install pyinstaller

pyinstaller \
  --onefile \
  --windowed \
  --name FileForge \
  --add-data "data/extensions.json;data" \
  --add-data "config/config.json;config" \
  main.py
```

El ejecutable portable se genera en `dist/FileForge.exe` — no requiere Python instalado.

---

## 🛠️ Stack tecnológico

| Componente | Tecnología |
|---|---|
| Lenguaje | Python 3.11+ |
| GUI | PySide6 (Qt6) |
| Hashing | SHA-256 vía `hashlib` (stdlib) |
| Concurrencia | `concurrent.futures.ThreadPoolExecutor` |
| Empaquetado | PyInstaller |
| Almacenamiento | JSON (config, history, extensions) |
| Dependencias externas (core) | **Ninguna** |

---

## 🤝 Contribuir

1. Haz fork del repositorio
2. Crea una rama: `git checkout -b feature/mi-mejora`
3. Haz commit: `git commit -m 'Add mi mejora'`
4. Haz push: `git push origin feature/mi-mejora`
5. Abre un Pull Request

---

## 📄 Licencia

Distribuido bajo la **licencia MIT** — libre para uso personal y comercial.

Ver [`LICENSE`](./LICENSE) para más detalles.

---

<p align="center">Hecho con ❤️ y Python · <strong>EstebanDev411</strong></p>
<p align="center">⭐ ¡Dale una estrella si FileForge te ahorró tiempo! ⭐</p>
