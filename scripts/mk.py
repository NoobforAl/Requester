"""Cross-platform helpers for the Makefile (cmd.exe has no find, rm, mkdir -p, awk).

    python scripts/mk.py help [Makefile]     list the documented make targets
    python scripts/mk.py mkdir DIR...        create directories (like mkdir -p)
    python scripts/mk.py rm PATH...          delete files or folders (like rm -rf)
    python scripts/mk.py clean               remove caches, bytecode and build artifacts
    python scripts/mk.py clean-all           clean + remove .venv, src/db.sqlite3
    python scripts/mk.py guard CLEANUP -- CMD...
                                             run CMD, then CLEANUP; exit like CMD

Standard library only, so it runs under any Python.
"""

# ruff: noqa: S603, S607 - runs fixed commands from the Makefile, no user input

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
CACHE_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "htmlcov"}
SKIP_DIRS = {".venv", ".git", "node_modules"}
LOOSE_FILES = [ROOT / ".coverage", ROOT / "coverage.xml", ROOT / "test.png"]


def remove(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path, ignore_errors=True)
    elif path.exists() or path.is_symlink():
        path.unlink(missing_ok=True)


def help_(makefile: str = "Makefile") -> int:
    pattern = re.compile(r"^([a-zA-Z_-]+):.*## (.*)$")
    for line in (ROOT / makefile).read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if match:
            print(f"  make {match.group(1):<16} {match.group(2)}")
    return 0


def mkdir(*dirs: str) -> int:
    for d in dirs:
        Path(d).mkdir(parents=True, exist_ok=True)
    return 0


def rm(*paths: str) -> int:
    for p in paths:
        remove(Path(p))
    return 0


def clean() -> int:
    for dirpath, dirnames, _files in os.walk(ROOT):
        for name in [d for d in dirnames if d in CACHE_DIRS]:
            remove(Path(dirpath) / name)
        dirnames[:] = [
            d for d in dirnames if d not in CACHE_DIRS and d not in SKIP_DIRS
        ]
    remove(SRC / "staticfiles")
    for f in LOOSE_FILES:
        remove(f)
    print("Clean.")
    return 0


def clean_all() -> int:
    clean()
    remove(SRC / "db.sqlite3")
    venv = ROOT / ".venv"
    if not venv.exists():
        return 0
    if os.name == "nt":
        # This script may run from .venv's python.exe, which Windows will not let
        # us delete. Hand the job to a detached shell that waits for us to exit.
        subprocess.Popen(
            ["cmd", "/c", f'ping -n 3 127.0.0.1 >nul & rmdir /s /q "{venv}"'],
            creationflags=subprocess.DETACHED_PROCESS
            | subprocess.CREATE_NEW_PROCESS_GROUP,
            close_fds=True,
        )
        print("Removing .venv in the background.")
    else:
        remove(venv)
    return 0


def guard(cleanup: str, *command: str) -> int:
    """Run command, then the cleanup command line, whatever happened."""
    try:
        status = subprocess.call(list(command))
    finally:
        subprocess.call(shlex.split(cleanup))
    return status


def guard_args(*args: str) -> int:
    """``guard CLEANUP... -- COMMAND...``"""
    if "--" not in args:
        print(__doc__)
        return 2
    split = args.index("--")
    return guard(" ".join(args[:split]), *args[split + 1 :])


COMMANDS: dict[str, Callable[..., int]] = {
    "help": help_,
    "mkdir": mkdir,
    "rm": rm,
    "clean": clean,
    "clean-all": clean_all,
    "guard": guard_args,
}


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in COMMANDS:
        print(__doc__)
        return 2
    return COMMANDS[argv[0]](*argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
