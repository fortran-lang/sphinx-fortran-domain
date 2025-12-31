from __future__ import annotations

from sphinx_fortran_domain.directives import (
    _preprocess_fortran_docstring,
    _split_out_doc_section_blocks,
)


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


def test_preprocess_see_also_to_seealso_directive() -> None:
    text = """Summary

## See Also
:f:func:`matrix_determinant`
:f:func:`matrix_multiply`, :f:func:`matrix_transpose`
:f:func:`vector_add` : Related vector operation.

## Notes
More text.
"""

    out = _preprocess_fortran_docstring(text)
    assert ".. seealso::" in out
    assert ".. rubric:: See Also" not in out
    assert "   :f:func:`matrix_determinant`" in out
    assert "   :f:func:`matrix_multiply`, :f:func:`matrix_transpose`" in out
    assert "   :f:func:`vector_add`" in out
    assert "      Related vector operation." in out
    assert ".. rubric:: Notes" in out


def test_split_out_doc_section_blocks_includes_examples_in_sections() -> None:
    text = """Summary

Intro paragraph.

## Examples
>>> call foo(a)

## Notes
Something important.
"""

    preamble, sections = _split_out_doc_section_blocks(text)
    assert preamble and "## Examples" not in preamble
    assert sections and "## Examples" in sections
    assert sections and "## Notes" in sections


def test_split_out_doc_section_blocks_splits_preamble_from_sections() -> None:
    text = """Short summary line.

More details.

## Notes
Some notes.

## References
- A
"""

    preamble, sections = _split_out_doc_section_blocks(text)
    assert preamble and "Short summary" in preamble
    assert preamble and "## Notes" not in preamble
    assert sections and sections.lstrip().startswith("## Notes")
    assert sections and "## References" in sections


def test_split_out_doc_section_blocks_no_sections_returns_all_preamble() -> None:
    text = """Just prose.

No explicit sections.
"""
    preamble, sections = _split_out_doc_section_blocks(text)
    assert preamble == text.strip()
    assert sections is None


