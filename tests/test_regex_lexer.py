from __future__ import annotations

from pathlib import Path

from sphinx_fortran_domain.lexers.lexer_regex import RegexFortranLexer


def test_regex_lexer_parses_examples() -> None:
    root = Path(__file__).resolve().parents[1]
    example_dir = root / "example"
    files = sorted(str(p) for p in example_dir.glob("*.f90"))

    lexer = RegexFortranLexer()
    result = lexer.parse(files, doc_markers=["!>", "!!"])

    assert "example_module" in result.modules
    assert "math_utils" in result.modules
    assert "stdlib_quadrature" in result.modules
    assert "stdlib_quadrature_trapz" in result.submodules

    m = result.modules["example_module"]
    assert any(t.name == "vector_type" for t in m.types)
    assert any(p.name == "add_vectors" and p.kind == "function" for p in m.procedures)
    assert any(p.name == "normalize_vector" and p.kind == "subroutine" for p in m.procedures)

    math_utils = result.modules["math_utils"]
    assert math_utils.doc and "utilities" in math_utils.doc.lower()

    add = next((p for p in math_utils.procedures if p.name == "add_integers"), None)
    assert add is not None
    arg_a = next((a for a in getattr(add, "arguments", []) if a.name == "a"), None)
    assert arg_a is not None
    assert arg_a.doc and "first integer" in arg_a.doc.lower()

    # Decl should include type/intent attributes.
    assert arg_a.decl and "intent" in arg_a.decl.lower()

    # Procedure doc should remain on the procedure, not be merged into arg docs.
    assert add.doc and "adds two integers" in add.doc.lower()


def test_regex_lexer_parses_programs() -> None:
    root = Path(__file__).resolve().parents[1]
    f = root / "example" / "example_03.f90"

    lexer = RegexFortranLexer()
    result = lexer.parse([str(f)], doc_markers=["!", ">"])

    assert "test_program" in result.programs
