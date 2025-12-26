from __future__ import annotations

from pathlib import Path

import pytest


def _has_standalone_dim_token(decl: str) -> bool:
    # Detect comma-separated bare "(:)" (or similar) tokens.
    # Valid output should use dimension(:) instead.
    import re

    return re.search(r"(?:^|,)\s*\([^=]*:\s*[^=]*\)\s*(?:,|$)", decl) is not None


def test_ford_lexer_parses_examples_without_crashing() -> None:
    ford = pytest.importorskip("ford")
    assert ford is not None

    from sphinx_fortran_domain.lexers.lexer_ford import FORDFortranLexer

    root = Path(__file__).resolve().parents[1]
    example_dir = root / "example"
    files = sorted(str(p) for p in example_dir.glob("*.f90"))

    lexer = FORDFortranLexer()
    result = lexer.parse(files, doc_markers=["!", ">"])

    # Sanity checks: these should exist in the examples.
    assert "example_module" in result.modules
    assert "math_utils" in result.modules

    # Programs and their internal procedures (after CONTAINS)
    assert "test_program" in result.programs
    prog = result.programs["test_program"]
    assert getattr(prog, "procedures", None)
    assert any(p.name == "example_internal_procedure" and p.kind == "function" for p in prog.procedures)

    math_utils = result.modules["math_utils"]
    add = next((p for p in math_utils.procedures if p.name == "add_integers"), None)
    assert add is not None
    # example_01.f90 has inline docs on the argument declarations; we split them into doc lines for FORD.
    arg_a = next((a for a in getattr(add, "arguments", []) if a.name == "a"), None)
    assert arg_a is not None
    assert arg_a.doc and "first integer" in arg_a.doc.lower()

    # FORD may provide a full declaration; ensure we capture something useful when present.
    assert arg_a.decl
    assert "intent" in arg_a.decl.lower()

    # Array argument should not produce a standalone "(:)" token in the decl.
    norm = next((p for p in math_utils.procedures if p.name == "norm_array"), None)
    assert norm is not None
    arg_arr = next((a for a in getattr(norm, "arguments", []) if a.name == "array"), None)
    assert arg_arr is not None
    assert arg_arr.decl
    assert "dimension" in arg_arr.decl.lower()
    assert not _has_standalone_dim_token(arg_arr.decl)

    # Function result variable should be captured and documented.
    mul = next((p for p in math_utils.procedures if p.name == "multiply_reals"), None)
    assert mul is not None
    res = getattr(mul, "result", None)
    assert res is not None
    assert res.name == "res"
    assert res.doc and "result of the multiplication" in res.doc.lower()

    # Derived type members and type-bound procedures
    example_module = result.modules["example_module"]
    t_vec = next((t for t in example_module.types if t.name == "vector_type"), None)
    assert t_vec is not None
    comps = list(getattr(t_vec, "components", []) or [])
    assert {c.name for c in comps} >= {"x", "y", "z"}
    cx = next((c for c in comps if c.name == "x"), None)
    assert cx is not None
    assert cx.doc and "x component" in cx.doc.lower()

    bps = list(getattr(t_vec, "bound_procedures", []) or [])
    assert {b.name for b in bps} >= {"magnitude", "dot"}
    mag = next((b for b in bps if b.name == "magnitude"), None)
    assert mag is not None
    assert (mag.target or "").lower().endswith("vector_magnitude")

    # Derived type component decl should include dimension + default initializer.
    math_utilities = result.modules.get("math_utilities")
    assert math_utilities is not None
    t_mat = next((t for t in math_utilities.types if t.name == "matrix_type"), None)
    assert t_mat is not None
    elements = next((c for c in getattr(t_mat, "components", []) if c.name == "elements"), None)
    assert elements is not None
    assert elements.decl
    assert "dimension" in elements.decl.lower()
    assert "3" in elements.decl
    assert "default" in elements.decl.lower()
