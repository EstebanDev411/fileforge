"""
cli.py
-------
FileForge command-line interface.

Subcommands
-----------
  fileforge scan      <path> [options]   – scan a directory
  fileforge organize  <path> [options]   – classify + move/copy files
  fileforge dupes     <path> [options]   – find and resolve duplicates
  fileforge auto      <path> [options]   – Smart Auto Organize (all-in-one)
  fileforge history   [options]          – view operation history
  fileforge undo      <id>               – undo an organize operation

Examples
--------
  python main.py scan C:\\Users\\John\\Downloads
  python main.py organize C:\\Users\\John\\Downloads --dest C:\\Organized --dry-run
  python main.py dupes C:\\Users\\John --strategy move_to_folder --keep newest
  python main.py auto C:\\Users\\John\\Documents
  python main.py history --last 10
  python main.py undo abc123
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _bold(text: str) -> str:
    """ANSI bold — gracefully degrades on Windows without ANSI support."""
    try:
        return f"\033[1m{text}\033[0m"
    except Exception:
        return text


def _print_header(title: str) -> None:
    line = "─" * 60
    print(f"\n{_bold('FileForge')} › {title}")
    print(line)


def _print_result_row(label: str, value, width: int = 24) -> None:
    print(f"  {label:<{width}} {value}")


def _progress_bar(done: int, total: int, width: int = 40) -> str:
    if total == 0:
        return "[" + "─" * width + "] 0%"
    ratio = min(done / total, 1.0)
    filled = int(width * ratio)
    bar = "█" * filled + "░" * (width - filled)
    pct = int(ratio * 100)
    return f"[{bar}] {pct:>3}%"


def _cli_progress(done: int, total: int, current: str) -> None:
    """Inline progress for long operations — overwrites same line."""
    bar = _progress_bar(done, total)
    name = Path(current).name[:30] if current else ""
    print(f"\r  {bar}  {name:<32}", end="", flush=True)


# ──────────────────────────────────────────────────────────────────────────────
#  Subcommand implementations
# ──────────────────────────────────────────────────────────────────────────────

def cmd_scan(args: argparse.Namespace) -> int:
    """fileforge scan <path> [--depth N] [--show-categories]"""
    from core.scanner import Scanner
    from core.classifier import Classifier
    from collections import Counter

    _print_header(f"Scan  →  {args.path}")

    path = Path(args.path)
    if not path.exists():
        print(f"  ERROR: Path does not exist: {path}", file=sys.stderr)
        return 1

    scanned_count = [0]

    def on_progress(n: int, current: str) -> None:
        scanned_count[0] = n
        print(f"\r  Files found: {n:>8}  │  {Path(current).name[:40]:<42}",
              end="", flush=True)

    scanner = Scanner(
        progress_callback=on_progress,
        progress_interval=500,
    )

    print(f"  Scanning …")
    entries = scanner.scan(path)
    print()   # newline after inline progress

    if not entries:
        print("  No files found.")
        return 0

    # Classify for category stats
    clf = Classifier()
    clf.classify_all(entries)

    total_size = sum(e.size for e in entries)
    categories = Counter(e.category for e in entries)

    _print_result_row("Total files:",   f"{len(entries):,}")
    _print_result_row("Total size:",    f"{total_size / (1024**3):.2f} GB")
    _print_result_row("Deepest path:",  max(entries, key=lambda e: e.path.count("/")).path[:60])
    print()

    if args.show_categories or True:
        print(f"  {'Category':<22} {'Files':>8}  {'%':>5}")
        print("  " + "─" * 38)
        for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
            pct = count / len(entries) * 100
            print(f"  {cat:<22} {count:>8,}  {pct:>5.1f}%")

    return 0


def cmd_organize(args: argparse.Namespace) -> int:
    """fileforge organize <path> [--dest DIR] [--mode move|copy] [--dry-run] [--conflict rename|skip|overwrite]"""
    from core.scanner import Scanner
    from core.classifier import Classifier
    from core.heuristics import Heuristics
    from core.organizer import Organizer
    from system.config import Config

    dest = args.dest or str(Path(args.path) / Config.get("organize.output_folder_name", "_Organized"))
    _print_header(f"Organize  →  {args.path}")

    if args.dry_run:
        print("  ⚠  DRY-RUN mode — no files will be moved")

    print(f"  Source      : {args.path}")
    print(f"  Destination : {dest}")
    print(f"  Mode        : {args.mode}")
    print(f"  Conflict    : {args.conflict}")
    print()

    # 1. Scan
    print("  [1/3] Scanning …")
    scanner = Scanner(progress_interval=1000)
    entries = scanner.scan(args.path)
    print(f"        {len(entries):,} files found")

    if not entries:
        print("  Nothing to organize.")
        return 0

    # 2. Classify
    print("  [2/3] Classifying …")
    clf = Classifier()
    clf.classify_all(entries)
    h = Heuristics()
    h.apply_all(entries)

    # 3. Organize
    print("  [3/3] Organizing …")
    done_ref = [0]

    def on_progress(done: int, total: int, current: str) -> None:
        done_ref[0] = done
        _cli_progress(done, total, current)

    org = Organizer(
        destination=dest,
        mode=args.mode,
        dry_run=args.dry_run,
        conflict=args.conflict,
        progress_callback=on_progress,
    )
    result = org.organize(entries, source_root=args.path)
    print()   # newline after progress

    print()
    action = "Would move" if args.dry_run else "Moved"
    _print_result_row(f"{action}:", f"{result.moved:,} files")
    if result.copied:
        _print_result_row("Copied:",  f"{result.copied:,} files")
    _print_result_row("Skipped:",  f"{result.skipped:,} files")
    _print_result_row("Errors:",   f"{result.errors}")

    if result.errors > 0:
        print(f"\n  ⚠  {result.errors} error(s) — check logs/log.txt for details")

    return 0 if result.errors == 0 else 1


def cmd_dupes(args: argparse.Namespace) -> int:
    """fileforge dupes <path> [--dest DIR] [--strategy move_to_folder|delete] [--keep newest|oldest] [--confirm]"""
    from core.scanner import Scanner
    from core.classifier import Classifier
    from core.duplicates import DuplicateDetector

    _print_header(f"Duplicates  →  {args.path}")

    if args.strategy == "delete" and not args.confirm:
        print("  ERROR: --strategy delete requires --confirm flag.", file=sys.stderr)
        print("         Add --confirm to permanently delete duplicates.", file=sys.stderr)
        return 1

    # Scan
    print("  [1/3] Scanning …")
    scanner = Scanner(progress_interval=1000)
    entries = scanner.scan(args.path)
    print(f"        {len(entries):,} files found")

    if not entries:
        print("  No files to check.")
        return 0

    Classifier().classify_all(entries)

    # Detect
    print("  [2/3] Hashing candidates …")
    hashed_ref = [0]

    def on_hash(done: int, total: int, current: str) -> None:
        hashed_ref[0] = done
        _cli_progress(done, total, current)

    detector = DuplicateDetector(progress_callback=on_hash)
    groups = detector.find(entries)
    print()

    if not groups:
        print("\n  ✓ No duplicate files found.")
        return 0

    total_wasted = sum(g.wasted_bytes for g in groups)
    print()
    _print_result_row("Duplicate groups:",  f"{len(groups):,}")
    _print_result_row("Duplicate files:",   f"{sum(len(g.files)-1 for g in groups):,}")
    _print_result_row("Space wasted:",      f"{total_wasted/(1024**2):.1f} MB")

    # Show top 5 groups
    print(f"\n  {'Hash':>14}  {'Files':>5}  {'Wasted MB':>10}  Sample name")
    print("  " + "─" * 60)
    for g in sorted(groups, key=lambda x: -x.wasted_bytes)[:5]:
        print(f"  {g.hash[:14]}  {len(g.files):>5}  "
              f"{g.wasted_mb():>10.2f}  {g.files[0].name[:28]}")

    if len(groups) > 5:
        print(f"  … and {len(groups)-5} more groups")

    if args.dry_run:
        print("\n  DRY-RUN — no changes made.")
        return 0

    # Resolve
    print(f"\n  [3/3] Resolving [{args.strategy}, keep={args.keep}] …")
    dest = args.dest or str(Path(args.path))
    result = detector.resolve(
        groups,
        destination=dest,
        strategy=args.strategy,
        keep=args.keep,
        confirmed=args.confirm,
    )
    print()
    _print_result_row("Processed:", f"{result.files_processed:,} duplicates")
    _print_result_row("Kept:",      f"{result.files_kept:,} originals")
    _print_result_row("Freed:",     f"{result.mb_freed():.1f} MB")
    _print_result_row("Errors:",    f"{result.errors}")

    return 0 if result.errors == 0 else 1


def cmd_auto(args: argparse.Namespace) -> int:
    """
    fileforge auto <path> [--dest DIR] [--dry-run]
    Smart Auto Organize: scan → classify → heuristics → duplicates → organize
    """
    from core.scanner import Scanner
    from core.classifier import Classifier
    from core.heuristics import Heuristics
    from core.duplicates import DuplicateDetector
    from core.organizer import Organizer
    from system.config import Config

    dest = args.dest or str(Path(args.path) / Config.get("organize.output_folder_name", "_Organized"))

    _print_header(f"Smart Auto Organize  →  {args.path}")
    if args.dry_run:
        print("  ⚠  DRY-RUN mode — no files will be moved\n")

    print(f"  Source      : {args.path}")
    print(f"  Destination : {dest}\n")

    # ── Step 1: Scan ────────────────────────────────────────────────────
    print("  [1/4] Scanning …")
    scanner = Scanner(progress_interval=1000)
    entries = scanner.scan(args.path)
    print(f"        {len(entries):,} files found")

    if not entries:
        print("  Nothing to process.")
        return 0

    # ── Step 2: Classify ─────────────────────────────────────────────────
    print("  [2/4] Classifying + applying heuristics …")
    Classifier().classify_all(entries)
    Heuristics().apply_all(entries)

    # ── Step 3: Detect duplicates ─────────────────────────────────────────
    dup_enabled = Config.get("duplicates.enabled", True)
    dup_groups = []
    if dup_enabled:
        print("  [3/4] Detecting duplicates …")
        hashed = [0]
        def on_hash(done, total, cur):
            hashed[0] = done
            _cli_progress(done, total, cur)
        detector = DuplicateDetector(progress_callback=on_hash)
        dup_groups = detector.find(entries)
        print()
        if dup_groups:
            wasted = sum(g.wasted_bytes for g in dup_groups) / (1024**2)
            print(f"        {len(dup_groups)} duplicate groups found ({wasted:.1f} MB wasted)")
        else:
            print("        No duplicates found")
    else:
        print("  [3/4] Duplicate detection disabled (config)")

    # ── Step 4: Organize ──────────────────────────────────────────────────
    print("  [4/4] Organizing files …")
    done_ref = [0]
    def on_org(done, total, cur):
        done_ref[0] = done
        _cli_progress(done, total, cur)

    org = Organizer(
        destination=dest,
        dry_run=args.dry_run,
        progress_callback=on_org,
    )
    org_result = org.organize(entries, source_root=args.path)
    print()

    # Resolve duplicates after organizing
    if dup_groups and not args.dry_run:
        strategy = Config.get("duplicates.strategy", "move_to_folder")
        keep = Config.get("duplicates.keep", "newest")
        dup_result = detector.resolve(
            dup_groups,
            destination=dest,
            strategy=strategy,
            keep=keep,
            confirmed=(strategy != "delete"),
        )
        print(f"        Duplicates resolved: {dup_result.files_processed} files, "
              f"{dup_result.mb_freed():.1f} MB freed")

    # ── Summary ──────────────────────────────────────────────────────────
    print()
    print(f"  {'─'*56}")
    print(f"  Smart Auto Organize {'(DRY-RUN) ' if args.dry_run else ''}complete")
    print(f"  {'─'*56}")
    action = "Would process" if args.dry_run else "Processed"
    _print_result_row(f"{action}:",    f"{len(entries):,} files")
    _print_result_row("Organized:",    f"{org_result.moved + org_result.copied:,} files")
    _print_result_row("Dup groups:",   f"{len(dup_groups)}")
    _print_result_row("Errors:",       f"{org_result.errors}")

    return 0 if org_result.errors == 0 else 1


def cmd_history(args: argparse.Namespace) -> int:
    """fileforge history [--last N] [--json]"""
    from system.history import History

    _print_header("Operation History")

    entries = History.get_all()

    if not entries:
        print("  No history entries yet.")
        return 0

    entries = entries[: args.last]

    if args.json:
        print(json.dumps(entries, indent=2, ensure_ascii=False))
        return 0

    print(f"  {'#':<4}  {'Date':<20}  {'Action':<12}  {'Files':>7}  {'Errors':>6}  Source")
    print("  " + "─" * 72)
    for i, e in enumerate(entries, 1):
        ts    = e.get("timestamp", "")[:19]
        act   = e.get("action", "")[:10]
        files = e.get("files_affected", 0)
        errs  = e.get("errors", 0)
        src   = e.get("source", "")[-40:]
        eid   = e.get("id", "")[:8]
        print(f"  {i:<4}  {ts:<20}  {act:<12}  {files:>7,}  {errs:>6}  {src}")

    print(f"\n  {len(entries)} entries shown  (use --last N to limit)")
    return 0


def cmd_watch(args: argparse.Namespace) -> int:
    """fileforge watch <path> [--dest DIR] [--recursive] [--interval N]"""
    import signal
    from core.watcher import Watcher, WatchTarget

    _print_header(f"Watcher  →  {args.path}")
    print(f"  Folder      : {args.path}")
    print(f"  Destination : {args.dest or '<folder>/_Organized'}")
    print(f"  Recursive   : {args.recursive}")
    print(f"  Press Ctrl+C to stop\n")

    processed = [0]
    errors    = [0]

    def on_file(event):
        processed[0] += 1
        action = "✓" if event.action != "error" else "✗"
        name = __import__('pathlib').Path(event.path).name
        cat  = f" [{event.category}]" if event.category else ""
        print(f"  {action} {name}{cat}")

    def on_log(msg: str):
        if not msg.startswith("  "):
            print(f"  {msg}")

    target = WatchTarget(
        path=args.path,
        destination=args.dest or "",
        recursive=args.recursive,
    )

    w = Watcher(
        on_file=on_file,
        on_log=on_log,
        poll_interval=args.interval,
    )
    w.add(target)
    w.start()

    print(f"  Backend: {w.backend}")
    print(f"  Watching for new files…\n")

    def _stop(sig, frame):
        print(f"\n\n  Stopping watcher…")
        w.stop()
        print(f"  Files organized : {processed[0]:,}")
        print(f"  Errors          : {errors[0]:,}")

    signal.signal(signal.SIGINT, _stop)

    try:
        while w.is_running:
            __import__('time').sleep(1)
    except SystemExit:
        pass

    return 0


def cmd_undo(args: argparse.Namespace) -> int:
    """fileforge undo <entry_id>"""
    from system.history import History

    _print_header(f"Undo  →  {args.id}")

    entry = History.get_entry(args.id)
    if not entry:
        # Try partial ID match
        all_entries = History.get_all()
        matches = [e for e in all_entries if e["id"].startswith(args.id)]
        if len(matches) == 1:
            entry = matches[0]
        elif len(matches) > 1:
            print(f"  ERROR: Ambiguous ID '{args.id}' matches {len(matches)} entries.", file=sys.stderr)
            return 1
        else:
            print(f"  ERROR: No history entry found for ID '{args.id}'", file=sys.stderr)
            return 1

    print(f"  Action    : {entry['action']}")
    print(f"  Date      : {entry['timestamp']}")
    print(f"  Files     : {entry['files_affected']:,}")
    print(f"  Source    : {entry.get('source', '')}")
    print(f"  Dest      : {entry.get('destination', '')}")
    print()

    if entry["action"] not in ("organize", "move"):
        print(f"  ERROR: Cannot undo action type '{entry['action']}'", file=sys.stderr)
        return 1

    if not args.confirm:
        print(f"  This will move {entry['files_affected']:,} files back to their original locations.")
        answer = input("  Proceed? [y/N] ").strip().lower()
        if answer != "y":
            print("  Cancelled.")
            return 0

    print("  Reversing …")
    reversed_count, errors = History.undo(entry["id"])
    print(f"\n  Reversed : {reversed_count:,} files")
    if errors:
        print(f"  Errors   : {len(errors)}")
        for err in errors[:5]:
            print(f"    {err}")

    return 0 if not errors else 1


# ──────────────────────────────────────────────────────────────────────────────
#  Argument parser
# ──────────────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fileforge",
        description=_bold("FileForge") + " — Professional File Organizer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              fileforge scan C:\\Users\\John\\Downloads
              fileforge organize Downloads --dest C:\\Organized --dry-run
              fileforge dupes C:\\Users --strategy move_to_folder --keep newest
              fileforge auto C:\\Users\\John\\Documents
              fileforge history --last 5
              fileforge undo abc123ef
        """),
    )
    parser.add_argument("--version", action="version", version="FileForge 1.0.0")

    sub = parser.add_subparsers(dest="command", title="commands")
    sub.required = True

    # ── scan ────────────────────────────────────────────────────────────
    p_scan = sub.add_parser("scan", help="Scan a directory and show statistics")
    p_scan.add_argument("path", help="Directory to scan")
    p_scan.add_argument("--depth", type=int, default=-1,
                        help="Maximum scan depth (-1 = unlimited)")
    p_scan.add_argument("--show-categories", action="store_true", default=True,
                        help="Show file count per category (default: on)")

    # ── organize ─────────────────────────────────────────────────────────
    p_org = sub.add_parser("organize", help="Classify and organize files into folders")
    p_org.add_argument("path", help="Source directory")
    p_org.add_argument("--dest", default=None,
                       help="Destination root (default: <path>/_Organized)")
    p_org.add_argument("--mode", choices=["move", "copy"], default="move",
                       help="Move or copy files (default: move)")
    p_org.add_argument("--dry-run", action="store_true",
                       help="Preview without making changes")
    p_org.add_argument("--conflict", choices=["rename", "skip", "overwrite"],
                       default="rename", help="Conflict resolution (default: rename)")

    # ── dupes ─────────────────────────────────────────────────────────────
    p_dup = sub.add_parser("dupes", help="Find and resolve duplicate files")
    p_dup.add_argument("path", help="Directory to check for duplicates")
    p_dup.add_argument("--dest", default=None,
                       help="Destination for moved duplicates")
    p_dup.add_argument("--strategy", choices=["move_to_folder", "delete"],
                       default="move_to_folder",
                       help="What to do with duplicates (default: move_to_folder)")
    p_dup.add_argument("--keep", choices=["newest", "oldest"], default="newest",
                       help="Which copy to keep (default: newest)")
    p_dup.add_argument("--dry-run", action="store_true",
                       help="Show duplicates without resolving")
    p_dup.add_argument("--confirm", action="store_true",
                       help="Required for --strategy delete")

    # ── auto ──────────────────────────────────────────────────────────────
    p_auto = sub.add_parser("auto", help="Smart Auto Organize (all-in-one)")
    p_auto.add_argument("path", help="Source directory")
    p_auto.add_argument("--dest", default=None,
                        help="Destination root (default: <path>/_Organized)")
    p_auto.add_argument("--dry-run", action="store_true",
                        help="Preview without making changes")

    # ── watch ──────────────────────────────────────────────────────────
    p_watch = sub.add_parser("watch", help="Watch a folder and auto-organize new files")
    p_watch.add_argument("path", help="Folder to monitor")
    p_watch.add_argument("--dest", default=None,
                         help="Destination root (default: <path>/_Organized)")
    p_watch.add_argument("--recursive", action="store_true",
                         help="Watch subfolders too")
    p_watch.add_argument("--interval", type=int, default=5,
                         help="Poll interval in seconds (default: 5)")

    # ── history ───────────────────────────────────────────────────────────
    p_hist = sub.add_parser("history", help="View operation history")
    p_hist.add_argument("--last", type=int, default=20,
                        help="Number of entries to show (default: 20)")
    p_hist.add_argument("--json", action="store_true",
                        help="Output as JSON")

    # ── undo ──────────────────────────────────────────────────────────────
    p_undo = sub.add_parser("undo", help="Undo a previous organize operation")
    p_undo.add_argument("id", help="History entry ID (or prefix)")
    p_undo.add_argument("--confirm", action="store_true",
                        help="Skip confirmation prompt")

    return parser


# ──────────────────────────────────────────────────────────────────────────────
#  Entry point
# ──────────────────────────────────────────────────────────────────────────────

_COMMANDS = {
    "scan":     cmd_scan,
    "organize": cmd_organize,
    "dupes":    cmd_dupes,
    "auto":     cmd_auto,
    "watch":    cmd_watch,
    "history":  cmd_history,
    "undo":     cmd_undo,
}


def run_cli() -> None:
    """Parse CLI arguments and dispatch to the correct subcommand."""
    parser = _build_parser()
    args = parser.parse_args()

    handler = _COMMANDS.get(args.command)
    if handler is None:
        parser.print_help()
        sys.exit(1)

    try:
        exit_code = handler(args)
        sys.exit(exit_code or 0)
    except KeyboardInterrupt:
        print("\n\n  Cancelled by user.")
        sys.exit(130)
    except Exception as exc:
        from system.logger import get_logger
        log = get_logger("cli")
        log.exception("Unhandled CLI error: %s", exc)
        print(f"\n  FATAL ERROR: {exc}", file=sys.stderr)
        print("  Check logs/log.txt for details.", file=sys.stderr)
        sys.exit(1)
