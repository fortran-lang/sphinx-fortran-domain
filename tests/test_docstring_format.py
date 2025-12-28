from __future__ import annotations

from sphinx_fortran_domain.directives import (
    _preprocess_fortran_docstring,
    _split_out_examples_sections,
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


def test_split_out_examples_sections_moves_examples_to_end() -> None:
    text = """Summary

## Examples
>>> call foo(a)

## Notes
Something important.
"""

    main, examples = _split_out_examples_sections(text)
    assert main and "## Examples" not in main
    assert "## Notes" in main
    assert examples and "## Examples" in examples


def test_split_out_examples_sections_keeps_non_examples_in_place() -> None:
    text = """## Notes
Text.
"""
    main, examples = _split_out_examples_sections(text)
    assert main == text.strip()
    assert examples is None


def test_split_out_examples_sections_keeps_fenced_blocks_in_place() -> None:
    text = """Summary

```fortran
print *, 'hello'
```

## Notes
More text.
"""

    main, examples = _split_out_examples_sections(text)
    assert main and "```fortran" in main
    assert "## Notes" in main
    assert examples is None


def test_split_out_examples_sections_moves_examples_section_with_fences() -> None:
    text = """Summary

## Examples
```fortran
print *, 'hello'
```

## Notes
More text.
"""

    main, examples = _split_out_examples_sections(text)
    assert main and "## Examples" not in main
    assert "## Notes" in main
    assert examples and "## Examples" in examples
    assert "```fortran" in examples


