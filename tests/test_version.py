from __future__ import annotations

from pathlib import Path

import sphinx_fortran_domain


def test___version__matches_root_version_file() -> None:
    root = Path(__file__).resolve().parents[1]
    expected = (root / "VERSION").read_text(encoding="utf-8").strip()
    assert sphinx_fortran_domain.__version__ == expected
