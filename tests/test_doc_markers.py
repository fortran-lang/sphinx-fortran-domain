from __future__ import annotations

from sphinx_fortran_domain.lexers.lexer_regex import RegexFortranLexer


def test_custom_doc_marker_double_bang(tmp_path) -> None:
    src = tmp_path / "m.f90"
    src.write_text(
        """
!! Module doc line 1
!! Module doc line 2
module m
  implicit none
contains
!! Adds two ints
subroutine add(a,b,c)
end subroutine add
end module m
""".lstrip(),
        encoding="utf-8",
    )

    lexer = RegexFortranLexer()
    result = lexer.parse([str(src)], doc_markers=["!!"])

    assert "m" in result.modules
    assert result.modules["m"].doc == "Module doc line 1\nModule doc line 2"
    assert any(p.name == "add" and p.doc == "Adds two ints" for p in result.modules["m"].procedures)
