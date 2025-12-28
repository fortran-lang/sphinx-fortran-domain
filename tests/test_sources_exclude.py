from __future__ import annotations

from types import SimpleNamespace


class _DummyApp:
    def __init__(self, *, confdir: str, config) -> None:
        self.confdir = confdir
        self.config = config


def test_fortran_sources_exclude_file_dir_and_glob(tmp_path) -> None:
    # Layout under the Sphinx confdir
    src = tmp_path / "src"
    sub = src / "sub"
    src.mkdir()
    sub.mkdir()

    (src / "a.f90").write_text("module a\nend module a\n", encoding="utf-8")
    (src / "b.f90").write_text("module b\nend module b\n", encoding="utf-8")
    (src / "skip_me.f90").write_text("module s\nend module s\n", encoding="utf-8")
    (sub / "c.f90").write_text("module c\nend module c\n", encoding="utf-8")

    config = SimpleNamespace(
        fortran_sources=["src"],
        fortran_sources_exclude=[
            "src/b.f90",      # exclude individual file
            "src/sub",        # exclude directory
            "src/*skip*.f90", # exclude via glob
        ],
        fortran_file_extensions=[".f90"],
    )
    app = _DummyApp(confdir=str(tmp_path), config=config)

    from sphinx_fortran_domain import _collect_fortran_files

    files = _collect_fortran_files(app)

    # Only a.f90 should remain.
    assert len(files) == 1
    assert files[0].replace("\\", "/").endswith("/src/a.f90")
