from __future__ import annotations

from pathlib import Path

from sphinx.application import Sphinx


def _build_sphinx(*, srcdir: Path, confdir: Path, outdir: Path, doctreedir: Path) -> None:
	app = Sphinx(
		srcdir=str(srcdir),
		confdir=str(confdir),
		outdir=str(outdir),
		doctreedir=str(doctreedir),
		buildername="html",
		freshenv=True,
		warningiserror=False,
	)
	app.build(force_all=True)


def _write_test_project(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
	root = tmp_path
	fortran_dir = root / "fortran"
	docs_dir = root / "docs"
	out_dir = root / "_out"
	doctrees_dir = root / "_doctrees"
	for d in (fortran_dir, docs_dir, out_dir, doctrees_dir):
		d.mkdir(parents=True, exist_ok=True)

	fort_file = fortran_dir / "vis_mod.f90"
	fort_file.write_text(
		"""
module vis_mod
  implicit none
  private
  public :: pub_var, pub_type, pub_func, pub_iface

  integer :: hidden_var
  integer :: pub_var

  type :: hidden_type
    integer :: hidden_component
  end type hidden_type

  type :: pub_type
    private
    integer :: hidden_component
    integer, public :: pub_component
  contains
    procedure, private :: hidden_bind => impl_hidden
    procedure, public :: pub_bind => impl_pub
  end type pub_type

  interface hidden_iface
  end interface hidden_iface

  interface pub_iface
  end interface pub_iface

contains

  function hidden_func() result(r)
    integer :: r
    r = 0
  end function hidden_func

  function pub_func() result(r)
    integer :: r
    r = 1
  end function pub_func

  subroutine impl_hidden(this)
    class(pub_type), intent(inout) :: this
  end subroutine impl_hidden

  subroutine impl_pub(this)
    class(pub_type), intent(inout) :: this
  end subroutine impl_pub

end module vis_mod
""".lstrip(),
		encoding="utf-8",
	)

	repo_root = Path(__file__).resolve().parents[1]
	conf_py = docs_dir / "conf.py"
	conf_py.write_text(
		"""import os
import sys

sys.path.insert(0, os.path.abspath(r"{repo_root}"))

extensions = [
    "sphinx_fortran_domain",
]

fortran_lexer = "regex"
fortran_doc_chars = [">"]
fortran_sources = [r"{fort_file}"]

master_doc = "index"
""".format(repo_root=str(repo_root), fort_file=str(fort_file)),
		encoding="utf-8",
	)

	(docs_dir / "index.rst").write_text(
		"""Show Private Option Test
========================

.. toctree::
   :maxdepth: 1

   hidden
   shown
""",
		encoding="utf-8",
	)

	(docs_dir / "hidden.rst").write_text(
		"""Hidden View
===========

.. f:module:: vis_mod
""",
		encoding="utf-8",
	)

	(docs_dir / "shown.rst").write_text(
		"""Shown View
==========

.. f:module:: vis_mod
   :show-private:
""",
		encoding="utf-8",
	)

	return docs_dir, docs_dir, out_dir, doctrees_dir


def test_show_private_option_controls_module_and_type_members(tmp_path: Path) -> None:
	srcdir, confdir, outdir, doctreedir = _write_test_project(tmp_path)
	_build_sphinx(srcdir=srcdir, confdir=confdir, outdir=outdir, doctreedir=doctreedir)
	html_hidden = (outdir / "hidden.html").read_text(encoding="utf-8", errors="replace")

	assert "pub_var" in html_hidden
	assert "pub_type (type)" in html_hidden
	assert "pub_component" in html_hidden
	assert "pub_bind" in html_hidden
	assert "pub_func (function)" in html_hidden
	assert "pub_iface (interface)" in html_hidden

	assert "hidden_var" not in html_hidden
	assert "hidden_type (type)" not in html_hidden
	assert "hidden_component" not in html_hidden
	assert "hidden_bind" not in html_hidden
	assert "hidden_func (function)" not in html_hidden
	assert "hidden_iface (interface)" not in html_hidden

	html_shown = (outdir / "shown.html").read_text(encoding="utf-8", errors="replace")

	assert "hidden_var" in html_shown
	assert "hidden_type (type)" in html_shown
	assert "hidden_component" in html_shown
	assert "hidden_bind" in html_shown
	assert "hidden_func (function)" in html_shown
	assert "hidden_iface (interface)" in html_shown
