from __future__ import annotations

from pathlib import Path

import pytest

from sphinx_fortran_domain.lexers.lexer_regex import RegexFortranLexer
from sphinx_fortran_domain.utils import find_inline_doc


_POSTDOC_SOURCE = """
module m
  implicit none
  interface gen
    !! Doc of the generic, written after the interface statement.
    module procedure a_impl
  end interface gen
contains
  subroutine a_impl(x, k, n)
    integer, intent(inout) :: x
      !! Doc of x.
    integer, intent(in) :: k
      !! Doc of k.
    integer, intent(in) :: n !! Doc of n.
    ! !!! Check arguments !!!!!!!!
    ! !!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  end subroutine a_impl
end module m
""".lstrip()


_PREDOC_SOURCE = """
module m
  implicit none
contains
  !> Doc of a_impl.
  subroutine a_impl(x, k)
    !> Doc of x.
    integer, intent(inout) :: x
    integer, intent(in) :: k !> Doc of k.
  end subroutine a_impl
end module m
""".lstrip()


def _parse_ford(tmp_path: Path, source: str):
	pytest.importorskip("ford")
	from sphinx_fortran_domain.lexers.lexer_ford import FORDFortranLexer

	path = tmp_path / "m.f90"
	path.write_text(source, encoding="utf-8")
	return FORDFortranLexer().parse([str(path)], doc_markers=["!>", "!!"]).modules["m"]


def test_ford_double_bang_documents_the_preceding_statement(tmp_path: Path) -> None:
	module = _parse_ford(tmp_path, _POSTDOC_SOURCE)
	(proc,) = module.procedures

	assert {a.name: a.doc for a in proc.arguments} == {
		"x": "Doc of x.",
		"k": "Doc of k.",
		"n": "Doc of n.",
	}
	assert module.interfaces[0].doc == "Doc of the generic, written after the interface statement."
	# Ordinary comments containing '!!' are not documentation.
	assert not proc.doc


def test_ford_predoc_marker_still_documents_the_next_statement(tmp_path: Path) -> None:
	module = _parse_ford(tmp_path, _PREDOC_SOURCE)
	(proc,) = module.procedures

	assert proc.doc == "Doc of a_impl."
	assert {a.name: a.doc for a in proc.arguments} == {"x": "Doc of x.", "k": "Doc of k."}


def test_markers_inside_ordinary_comments_are_not_inline_docs() -> None:
	markers = ["!>", "!!"]
	assert find_inline_doc("    ! !!! Check arguments !!!!!!!!", markers) is None
	assert find_inline_doc("    ! see !> below", markers) is None
	assert find_inline_doc("    integer :: n !! Doc of n.", markers) == (17, "!!")


def test_regex_lexer_ignores_markers_inside_ordinary_comments(tmp_path: Path) -> None:
	path = tmp_path / "m.f90"
	path.write_text(_POSTDOC_SOURCE, encoding="utf-8")
	module = RegexFortranLexer().parse([str(path)], doc_markers=["!>", "!!"]).modules["m"]
	(proc,) = module.procedures

	assert not any("Check arguments" in (a.doc or "") for a in proc.arguments)
	assert "Check arguments" not in (proc.doc or "")
