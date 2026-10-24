from __future__ import annotations

from sphinx_fortran_domain.lexers.lexer_regex import RegexFortranLexer
from sphinx_fortran_domain.utils import dedent_doc, is_doc_line


def _parse(tmp_path, source: str):
    src = tmp_path / "m.f90"
    src.write_text(source.lstrip(), encoding="utf-8")
    return RegexFortranLexer().parse([str(src)], doc_markers=["!>"])


def test_is_doc_line_removes_only_the_separator() -> None:
    assert is_doc_line("!> text", ["!>"]) == "text"
    assert is_doc_line("!>text", ["!>"]) == "text"
    assert is_doc_line("  !>   indented", ["!>"]) == "  indented"
    assert is_doc_line("!>\ttab", ["!>"]) == "tab"
    assert is_doc_line("!>", ["!>"]) == ""
    assert is_doc_line("! plain comment", ["!>"]) is None


def test_dedent_doc_removes_common_indentation_only() -> None:
    assert dedent_doc(["  a", "  b"]) == "a\nb"
    assert dedent_doc(["* item", "  continued"]) == "* item\n  continued"
    assert dedent_doc(["", "a", ""]) == "a"
    assert dedent_doc(["", ""]) is None


def test_list_item_continuation_is_kept_before_module(tmp_path) -> None:
    result = _parse(
        tmp_path,
        """
!> Rules:
!>
!> * first item, which goes on
!>   over two lines;
!> * second item.
module m
end module m
""",
    )
    assert result.modules["m"].doc == (
        "Rules:\n\n* first item, which goes on\n  over two lines;\n* second item."
    )


def test_uniform_extra_indentation_is_removed(tmp_path) -> None:
    result = _parse(
        tmp_path,
        """
!>   Line one,
!>   line two.
module m
end module m
""",
    )
    assert result.modules["m"].doc == "Line one,\nline two."


def test_indentation_kept_in_docs_after_module_statement(tmp_path) -> None:
    result = _parse(
        tmp_path,
        """
module m
  !>   The first line, indented like the others,
  !>   then a directive:
  !>
  !>   .. math::
  !>
  !>      a = b
end module m
""",
    )
    assert result.modules["m"].doc == (
        "The first line, indented like the others,\nthen a directive:\n\n.. math::\n\n   a = b"
    )


def test_indentation_kept_in_procedure_docs(tmp_path) -> None:
    result = _parse(
        tmp_path,
        """
module m
  implicit none
contains
  !> Summary.
  !>
  !> .. code-block:: fortran
  !>
  !>    call f(1)
  subroutine f(n)
    integer, intent(in) :: n
  end subroutine f
end module m
""",
    )
    (proc,) = [p for p in result.modules["m"].procedures if p.name == "f"]
    assert proc.doc == "Summary.\n\n.. code-block:: fortran\n\n   call f(1)"
