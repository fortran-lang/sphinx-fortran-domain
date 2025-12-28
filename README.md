# Sphinx Fortran Domain

Fortran-lang's base Sphinx domain to document Fortran projects.

> **WARNING**: This project is under construction, at this stage you can use it but expect missing features or some rendering bugs. Your friendly feedback will be very important to get this project in shape.

## Install

Editable install for development:

`pip install -e .`

## Build the docs

Install with documentation dependencies:

`pip install -e ".[docs]"`

Build HTML documentation:

```
cd docs
make html
```

## Enable the extension

In `conf.py`:

```python
extensions = [
	"sphinx_fortran_domain",
]

# Where your Fortran sources live (directories, files, or glob patterns)
fortran_sources = [
	"../src",        # directory
	"../example/*.f90",  # glob pattern
]

# Exclude sources from parsing (directories, files, or glob patterns)
fortran_sources_exclude = [
	"../example/legacy",          # directory
	"../example/skip_this.f90",   # file
	"../example/**/generated_*.f90",  # glob
]

# Select a lexer (built-in: "regex")
fortran_lexer = "regex"

# Doc comment convention 
# Examples: '!>' or '!!' or '!@'
fortran_doc_chars = [">", "!"]
```

## Directives and roles

Manual declarations (create targets for cross-references):

```rst
.. f:function:: add_vectors(vec1, vec2)

.. f:subroutine:: normalize_vector(vec)
```

Autodoc-style views from parsed sources:

```rst
.. f:module:: example_module

.. f:submodule:: stdlib_quadrature_trapz

.. f:program:: test_program
```

Cross-references:

```rst
See :f:mod:`example_module` and :f:subr:`normalize_vector`.
```

## Writing a lexer plugin

External packages can register a lexer at import/setup time:

```python
from sphinx_fortran_domain.lexers import register_lexer

def setup(app):
	register_lexer("my-lexer", lambda: MyLexer())
```

Then use `fortran_lexer = "my-lexer"`.

## Math in doc comments

This extension parses Fortran doc comments as reStructuredText fragments, so Sphinx
roles/directives work inside docs (including math when `sphinx.ext.mathjax` is enabled).

Supported math styles:

- Recommended (reST):

```Fortran
!> .. math:: \hat{v} = \frac{\vec{v}}{|\vec{v}|}
```

Inline math also works via `:math:`:

```Fortran
!> The magnitude is :math:`|\vec{v}| = \sqrt{x^2 + y^2 + z^2}`.
```
