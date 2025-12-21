from __future__ import annotations

from pathlib import Path

import pytest


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
