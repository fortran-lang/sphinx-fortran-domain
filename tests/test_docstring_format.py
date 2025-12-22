from __future__ import annotations

from sphinx_fortran_domain.directives import _preprocess_fortran_docstring


def test_preprocess_sections_to_rubrics() -> None:
    text = """Short summary

## References
- A
- B
"""

    out = _preprocess_fortran_docstring(text)
    assert ".. rubric:: References" in out
    assert "## References" not in out


def test_preprocess_examples_to_code_block() -> None:
    text = """## Examples
>>> call foo(a, b)
>>> print *, a

Trailing text.
"""

    out = _preprocess_fortran_docstring(text)
    assert ".. rubric:: Examples" in out
    assert ".. code-block:: fortran" in out
    assert "   call foo(a, b)" in out
    assert "   print *, a" in out
    assert ">>>" not in out


def test_preprocess_inserts_blank_line_before_footnote_def() -> None:
    text = """## References
Cite the relevant literature, e.g. [1]_.
.. [1] Example reference.
"""

    out = _preprocess_fortran_docstring(text)
    assert "e.g. [1]_.\n\n.. [1]" in out
