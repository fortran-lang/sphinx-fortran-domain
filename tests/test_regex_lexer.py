from __future__ import annotations

from pathlib import Path

from sphinx_fortran_domain.lexers.lexer_regex import RegexFortranLexer


def test_regex_lexer_parses_examples() -> None:
    root = Path(__file__).resolve().parents[1]
    example_dir = root / "example"
    files = sorted(str(p) for p in example_dir.glob("*.f90"))

    lexer = RegexFortranLexer()
    result = lexer.parse(files, doc_markers=["!", ">"])

    assert "example_module" in result.modules
    assert "math_utils" in result.modules
    assert "stdlib_quadrature" in result.modules
    assert "stdlib_quadrature_trapz" in result.submodules

    m = result.modules["example_module"]
    t_vec = next((t for t in m.types if t.name == "vector_type"), None)
    assert t_vec is not None

    # Derived type members (components)
    comps = list(getattr(t_vec, "components", []) or [])
    assert {c.name for c in comps} >= {"x", "y", "z"}
    cx = next((c for c in comps if c.name == "x"), None)
    assert cx is not None
    assert cx.doc and "x component" in cx.doc.lower()

    # Type-bound procedures (methods)
    bps = list(getattr(t_vec, "bound_procedures", []) or [])
    assert {b.name for b in bps} >= {"magnitude", "dot"}
    mag = next((b for b in bps if b.name == "magnitude"), None)
    assert mag is not None
    assert (mag.target or "").lower().endswith("vector_magnitude")

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

    # And argument docs should not leak into the procedure description.
    assert "first integer" not in add.doc.lower()

    # Array arguments should include their dimension.
    norm = next((p for p in math_utils.procedures if p.name == "norm_array"), None)
    assert norm is not None
    arg_arr = next((a for a in getattr(norm, "arguments", []) if a.name == "array"), None)
    assert arg_arr is not None
    assert arg_arr.decl and "dimension(:)" in arg_arr.decl.lower()

    # Derived type component decl should include dimension + default initializer.
    math_utilities = result.modules.get("math_utilities")
    assert math_utilities is not None
    t_mat = next((t for t in math_utilities.types if t.name == "matrix_type"), None)
    assert t_mat is not None
    elements = next((c for c in getattr(t_mat, "components", []) if c.name == "elements"), None)
    assert elements is not None
    assert elements.decl and "dimension(3,3)" in elements.decl.replace(" ", "").lower()
    assert elements.decl and "dimension(3,3),default=0.0" in elements.decl.replace(" ", "").lower()

    # Function result variable should be captured and documented.
    mul = next((p for p in math_utils.procedures if p.name == "multiply_reals"), None)
    assert mul is not None
    res = getattr(mul, "result", None)
    assert res is not None
    assert res.name == "res"
    assert res.doc and "result of the multiplication" in res.doc.lower()
    # Result should not be duplicated as a regular argument.
    assert all(a.name != "res" for a in getattr(mul, "arguments", []))


def test_regex_lexer_parses_programs() -> None:
    root = Path(__file__).resolve().parents[1]
    f = root / "example" / "example_03.f90"

    lexer = RegexFortranLexer()
    result = lexer.parse([str(f)], doc_markers=["!", ">"])

    assert "test_program" in result.programs
