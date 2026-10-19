from __future__ import annotations

import io
import io
import re
from pathlib import Path

import pytest
from sphinx.application import Sphinx

from sphinx_fortran_domain.lexers.lexer_regex import RegexFortranLexer


_FORTRAN_SOURCE = """
module iface_mod
  implicit none
  private

  public :: solve, integrate, callback

  !> Generic linear solver.
  interface solve
    module procedure solve_real, solve_int
  end interface solve

  !> Integrates sampled values.
  interface integrate
    !> Integrate with a constant spacing.
    pure module function integrate_dx(y, dx) result(res)
      real, intent(in) :: y(:) !> Sampled values.
      real, intent(in) :: dx !> Spacing.
      real :: res
    end function integrate_dx
  end interface integrate

  abstract interface
    !> User callback signature.
    subroutine callback(x)
      real, intent(inout) :: x !> Value to update.
    end subroutine callback
  end interface

contains

  subroutine solve_real(x)
    real, intent(inout) :: x
  end subroutine solve_real

  subroutine solve_int(x)
    integer, intent(inout) :: x
  end subroutine solve_int

  subroutine hidden_helper()
  end subroutine hidden_helper

end module iface_mod
""".lstrip()


def _write_fortran(tmp_path: Path) -> Path:
	fort_file = tmp_path / "iface_mod.f90"
	fort_file.write_text(_FORTRAN_SOURCE, encoding="utf-8")
	return fort_file


def test_regex_lexer_collects_interface_procedures(tmp_path: Path) -> None:
	fort_file = _write_fortran(tmp_path)
	result = RegexFortranLexer().parse([str(fort_file)], doc_markers=["!>"])
	module = result.modules["iface_mod"]
	ifaces = {i.name: i for i in module.interfaces}

	assert tuple(ifaces["solve"].procedures) == ("solve_real", "solve_int")
	assert not ifaces["solve"].bodies

	integrate = ifaces["integrate"]
	assert tuple(integrate.procedures) == ("integrate_dx",)
	(body,) = integrate.bodies
	assert body.kind == "function"
	assert body.doc and "constant spacing" in body.doc
	assert [a.name for a in body.arguments] == ["y", "dx"]
	assert body.result is not None and body.result.name == "res"

	# Abstract interface bodies become their own (public) interfaces.
	callback = ifaces["callback"]
	assert not callback.is_private
	assert [b.name for b in callback.bodies] == ["callback"]

	# Interface bodies must not leak into the module procedures.
	proc_names = {p.name for p in module.procedures}
	assert proc_names == {"solve_real", "solve_int", "hidden_helper"}


def _build_html(tmp_path: Path, lexer: str) -> str:
	fort_file = _write_fortran(tmp_path)
	docs_dir = tmp_path / "docs"
	out_dir = tmp_path / "_out"
	docs_dir.mkdir()

	repo_root = Path(__file__).resolve().parents[1]
	(docs_dir / "conf.py").write_text(
		"""import os
import sys

sys.path.insert(0, os.path.abspath(r"{repo_root}"))

extensions = ["sphinx_fortran_domain"]
fortran_lexer = "{lexer}"
fortran_doc_chars = [">"]
fortran_sources = [r"{fort_file}"]
master_doc = "index"
""".format(repo_root=str(repo_root), lexer=lexer, fort_file=str(fort_file)),
		encoding="utf-8",
	)
	(docs_dir / "index.rst").write_text(
		"""Interfaces
==========

.. f:module:: iface_mod
""",
		encoding="utf-8",
	)

	app = Sphinx(
		srcdir=str(docs_dir),
		confdir=str(docs_dir),
		outdir=str(out_dir),
		doctreedir=str(tmp_path / "_doctrees"),
		buildername="html",
		freshenv=True,
		warningiserror=False,
	)
	app.build(force_all=True)
	return (out_dir / "index.html").read_text(encoding="utf-8", errors="replace")


def _section(html: str, anchor: str) -> str:
	start = html.index(f'id="{anchor}"')
	end = html.find("<section", start)
	return html[start : end if end != -1 else len(html)]


@pytest.mark.parametrize("lexer", ["regex", "ford"])
def test_interface_lists_its_procedures(tmp_path: Path, lexer: str) -> None:
	if lexer == "ford":
		pytest.importorskip("ford")
	html = _build_html(tmp_path, lexer)

	# Private specifics reachable through a public generic are documented...
	assert "solve_real (subroutine)" in html
	assert "solve_int (subroutine)" in html
	assert "hidden_helper" not in html

	# ...and the generic interface lists and links them.
	solve = _section(html, "f-interface-iface-mod-solve")
	assert "Procedures" in solve
	assert re.search(r'href="#f-subroutine-iface-mod-solve-real"', solve)
	assert re.search(r'href="#f-subroutine-iface-mod-solve-int"', solve)

	# Interface bodies are rendered (with arguments) and linked from the list.
	integrate = _section(html, "f-interface-iface-mod-integrate")
	assert "Integrates sampled values." in integrate
	assert 'href="#f-function-iface-mod-integrate-integrate-dx"' in integrate
	assert 'id="f-function-iface-mod-integrate-integrate-dx"' in integrate
	assert "Integrate with a constant spacing." in integrate
	assert "Sampled values." in integrate
	assert "Returns" in integrate


def test_abstract_interface_renders_its_signature(tmp_path: Path) -> None:
	html = _build_html(tmp_path, "regex")
	callback = _section(html, "f-interface-iface-mod-callback")
	assert re.search(r"subroutine</span>\s*<span[^>]*>callback\(x\)", callback)
	assert "User callback signature." in callback
	assert "Value to update." in callback


def test_manual_interface_lists_procedures(tmp_path: Path) -> None:
	docs_dir = tmp_path / "docs"
	out_dir = tmp_path / "_out"
	docs_dir.mkdir()
	repo_root = Path(__file__).resolve().parents[1]
	(docs_dir / "conf.py").write_text(
		"""import os
import sys

sys.path.insert(0, os.path.abspath(r"{repo_root}"))

extensions = ["sphinx_fortran_domain"]
master_doc = "index"
""".format(repo_root=str(repo_root)),
		encoding="utf-8",
	)
	(docs_dir / "index.rst").write_text(
		"""Manual
======

.. f:interface:: interpolate
   :procedures: interp_linear, interp_spline

   Interpolate tabulated data.

.. f:function:: interp_linear

   Linear.

.. f:subroutine:: interp_spline

   Spline.
""",
		encoding="utf-8",
	)
	app = Sphinx(
		srcdir=str(docs_dir),
		confdir=str(docs_dir),
		outdir=str(out_dir),
		doctreedir=str(tmp_path / "_doctrees"),
		buildername="html",
		freshenv=True,
		warningiserror=False,
	)
	app.build(force_all=True)
	html = (out_dir / "index.html").read_text(encoding="utf-8", errors="replace")

	assert "Procedures" in html
	# Functions and subroutines both resolve, whatever their kind.
	assert 'href="#f-function-interp-linear"' in html
	assert 'href="#f-subroutine-interp-spline"' in html


def test_module_renders_interfaces_before_procedures(tmp_path: Path) -> None:
	html = _build_html(tmp_path, "regex")
	assert html.index("solve (interface)") < html.index("solve_real (subroutine)")


def _build_manual(tmp_path: Path, body: str) -> tuple[str, str]:
	fort_file = _write_fortran(tmp_path)
	docs_dir = tmp_path / "docs"
	out_dir = tmp_path / "_out"
	docs_dir.mkdir()
	repo_root = Path(__file__).resolve().parents[1]
	(docs_dir / "conf.py").write_text(
		"""import os
import sys

sys.path.insert(0, os.path.abspath(r"{repo_root}"))

extensions = ["sphinx_fortran_domain"]
fortran_lexer = "regex"
fortran_doc_chars = [">"]
fortran_sources = [r"{fort_file}"]
master_doc = "index"
""".format(repo_root=str(repo_root), fort_file=str(fort_file)),
		encoding="utf-8",
	)
	(docs_dir / "index.rst").write_text("Manual\n======\n\n" + body, encoding="utf-8")
	warnings = io.StringIO()
	app = Sphinx(
		srcdir=str(docs_dir),
		confdir=str(docs_dir),
		outdir=str(out_dir),
		doctreedir=str(tmp_path / "_doctrees"),
		buildername="html",
		freshenv=True,
		warningiserror=False,
		warning=warnings,
	)
	app.build(force_all=True)
	return (out_dir / "index.html").read_text(encoding="utf-8", errors="replace"), warnings.getvalue()


def test_manual_interface_defaults_to_parsed_procedures(tmp_path: Path) -> None:
	html, warnings = _build_manual(
		tmp_path,
		""".. f:interface:: solve

   Hand-written description.

.. f:subroutine:: solve_real

.. f:subroutine:: solve_int
""",
	)
	assert "Procedures" in html
	assert 'href="#f-subroutine-solve-real"' in html
	assert 'href="#f-subroutine-solve-int"' in html
	assert "not among the procedures" not in warnings


def test_manual_interface_option_overrides_and_warns_on_unknown(tmp_path: Path) -> None:
	html, warnings = _build_manual(
		tmp_path,
		""".. f:interface:: solve
   :module: iface_mod
   :procedures: solve_real, solve_typo
""",
	)
	assert "solve_real" in html
	assert "solve_int" not in html
	assert "solve_typo" in warnings and "not among the procedures" in warnings


def test_manual_interface_warns_on_unknown_module(tmp_path: Path) -> None:
	html, warnings = _build_manual(
		tmp_path,
		""".. f:interface:: solve
   :module: no_such_module
""",
	)
	assert "no parsed interface of that name in module no_such_module" in warnings
	assert "solve_real" not in html
