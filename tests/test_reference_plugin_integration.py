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
		warningiserror=True,
	)
	app.build(force_all=True)


def test_reference_lexer_plugin_end_to_end(tmp_path: Path) -> None:
	# Layout:
	# tmp/
	#   docs/ (Sphinx srcdir)
	#   fortran/ (sources)
	#   _out/ (html)
	#   _doctrees/
	root = tmp_path
	fortran_dir = root / "fortran"
	docs_dir = root / "docs"
	out_dir = root / "_out"
	doctrees_dir = root / "_doctrees"
	for d in (fortran_dir, docs_dir, out_dir, doctrees_dir):
		d.mkdir(parents=True, exist_ok=True)

	# Minimal Fortran source: doc block immediately preceding module.
	(fort_file := (fortran_dir / "mymod.f90")).write_text(
		"""!> This is a test module
module mymod

	!> A tiny derived type.
	type :: vec
		!> x component docs.
		real :: x
	end type vec

contains

	!> Add one to x.
	function add_one(x) result(y)
		real, intent(in) :: x
		real :: y
		y = x + 1
	end function add_one

end module mymod
""",
		encoding="utf-8",
	)

	# Sphinx config. We add the repo root to sys.path so sphinx_fortran_domain is importable,
	# and add tests/fixtures so the reference_plugin module is importable.
	repo_root = Path(__file__).resolve().parents[1]
	fixture_dir = repo_root / "tests" / "fixtures"
	conf_py = docs_dir / "conf.py"
	conf_py.write_text(
		"""import os
import sys

sys.path.insert(0, os.path.abspath(r"{repo_root}"))
sys.path.insert(0, os.path.abspath(r"{fixture_dir}"))

extensions = [
    "reference_plugin",
    "sphinx_fortran_domain",
]

# Use the plugin-registered lexer.
fortran_lexer = "reference"

# Keep doc markers simple: default is !>
fortran_doc_chars = [">"]

# Point at the Fortran source file.
fortran_sources = [r"{fort_file}"]

master_doc = "index"
""".format(repo_root=str(repo_root), fixture_dir=str(fixture_dir), fort_file=str(fort_file)),
		encoding="utf-8",
	)

	(docs_dir / "index.rst").write_text(
		"""Reference Plugin Integration Test
===============================================================================

.. f:module:: mymod
""",
		encoding="utf-8",
	)

	_build_sphinx(srcdir=docs_dir, confdir=docs_dir, outdir=out_dir, doctreedir=doctrees_dir)

	# Sanity check: the module page should have rendered.
	index_html = (out_dir / "index.html").read_text(encoding="utf-8", errors="replace")
	assert "Module mymod" in index_html
	assert "This is a test module" in index_html
	# Our module should include a type and a procedure.
	assert "Type vec" in index_html
	assert "x" in index_html
	assert "x component docs" in index_html.lower()
	assert "Function add_one" in index_html
	assert "Add one to x" in index_html
