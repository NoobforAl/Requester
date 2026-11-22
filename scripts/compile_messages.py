"""Compile every ``src/locale/*/LC_MESSAGES/django.po`` to ``django.mo`` with polib.

A pure-Python stand-in for ``manage.py compilemessages`` for machines without GNU
gettext (the Docker image uses the real thing). Usage: ``make i18n-compile``.
"""

import sys
from pathlib import Path

import polib

LOCALE_DIR = Path(__file__).resolve().parent.parent / "src" / "locale"


def compile_all(locale_dir: Path = LOCALE_DIR) -> int:
    compiled = 0
    for po_path in sorted(locale_dir.glob("*/LC_MESSAGES/django.po")):
        polib.pofile(str(po_path)).save_as_mofile(str(po_path.with_suffix(".mo")))
        compiled += 1
        print(f"compiled {po_path.relative_to(locale_dir.parent)}")
    if not compiled:
        print(f"no .po files found under {locale_dir}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(compile_all())
