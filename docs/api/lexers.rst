=====================
Lexer Plugins
=====================

This project's “lexer” is a lightweight Fortran *parser* that extracts enough
structure to drive directives and cross-references (it is not intended to be a
full compiler frontend).

This page explains:

- where parsing starts in the Sphinx build,
- what your lexer must return,
- how to populate the Fortran object model used by this project,
- how to register your lexer as a plugin.


Where Parsing Starts
====================

Parsing runs automatically during a Sphinx build:

1. Sphinx loads extensions listed in ``conf.py``.
2. This extension registers an event handler on ``builder-inited``.
3. When the builder initializes, the handler:

   - collects Fortran source files from ``fortran_sources`` (and applies
     ``fortran_sources_exclude``),
   - derives doc markers from ``fortran_doc_chars``,
   - resolves the configured lexer name via the lexer registry,
   - calls ``lexer.parse(files, doc_markers=...)``,
   - stores the returned symbols into the ``f`` domain data.

After that, directives (e.g. ``.. f:module::``) render by reading the stored
symbols from the domain.


The Lexer Interface
===================

A lexer is any object implementing the ``FortranLexer`` protocol defined in
``sphinx_fortran_domain.lexers``.

At minimum:

- ``name``: a string identifier
- ``parse(file_paths, *, doc_markers) -> FortranParseResult``

Example skeleton:

.. code-block:: python

   from __future__ import annotations

   from typing import Sequence

   from sphinx_fortran_domain.lexers import (
       FortranLexer,
       FortranParseResult,
       FortranModuleInfo,
   )
   from sphinx_fortran_domain.utils import read_text_utf8


   class MyLexer(FortranLexer):
       name = "my-lexer"

       def parse(self, file_paths: Sequence[str], *, doc_markers: Sequence[str]) -> FortranParseResult:
           modules = {}
           submodules = {}
           programs = {}

           for path in file_paths:
               text = read_text_utf8(path)
               # ... parse text ...
               # modules["mymodule"] = FortranModuleInfo(name="mymodule", doc="...", ...)

           return FortranParseResult(modules=modules, submodules=submodules, programs=programs)

The ``doc_markers`` argument is the *resolved* marker list (examples: ``["!>"]``,
``["!>", "!!"]``). It is your lexer's responsibility to interpret those markers
and extract doc text.


Reusable Helpers (Recommended)
==============================

If you are writing a plugin lexer, you can reuse a few small helper functions
provided by this project instead of re-implementing common logic.

These helpers live in ``sphinx_fortran_domain.utils``:

* ``read_text_utf8(path)`` / ``read_lines_utf8(path)``: consistent UTF-8 reads with ``errors="replace"``.
* ``extract_predoc_before_line(lines, idx, doc_markers=...)``: grab the contiguous doc block immediately *above* a definition line.
* ``is_doc_line(line, doc_markers)`` and ``find_inline_doc(line, doc_markers)``: detect doc markers in whole-line docs and inline comment docs.
* ``strip_inline_comment(line)``: best-effort removal of ``! ...`` trailing comments.

These helpers can also be useful:

* ``doc_markers_from_doc_chars(fortran_doc_chars)``: convert config values like ``['>']`` into concrete markers like ``['!>']``.
* ``collect_fortran_source_files_from_config(confdir, config)``: collect Fortran sources using the standard config attribute names.


Populating the Fortran Object Model
===================================

Your ``parse`` method returns a ``FortranParseResult``:

- ``modules``: mapping ``module_name -> FortranModuleInfo``
- ``submodules``: mapping ``submodule_name -> FortranSubmoduleInfo``
- ``programs``: mapping ``program_name -> FortranProgramInfo``

The domain stores these mappings and directives query them by exact key.

Naming
------

Use stable, human-facing names as keys (typically the Fortran entity name as
written in source). Cross-references like ``:f:mod:`foo``` resolve against these
names.

Locations
---------

Most object types accept an optional ``SourceLocation(path, lineno)``.
Providing locations is recommended because it enables:

- better debugging,
- better program-source extraction in directives,
- future improvements (source links, jump-to-definition, etc.).

Use 1-based line numbers.

Docs
----

Most objects accept a ``doc: str | None``. That string is treated as a
reStructuredText fragment by this project's directives.

Practical guidance:

- Store *plain text* without the leading doc marker.
- Keep line breaks as you want them rendered.
- You may include Sphinx roles/directives (e.g. ``:math:`...``` or ``.. math::``).

This project also supports a lightweight doc convention that is normalized
before parsing as reST (for example, ``## Title`` becomes a rubric). If you
extract docs from source, you can preserve those markers.


Objects You Can Produce
=======================

Below is a simplified overview of the main dataclasses.

Module
------

.. code-block:: python

   from sphinx_fortran_domain.lexers import FortranModuleInfo, SourceLocation

   mod = FortranModuleInfo(
       name="mymodule",
       doc="""Module documentation.""",
       procedures=[...],
       types=[...],
       interfaces=[...],
       location=SourceLocation(path="/abs/or/rel/path.f90", lineno=1),
   )

Procedures (functions/subroutines)
----------------------------------

Procedures are represented as ``FortranProcedure`` objects.

- ``kind`` must be either ``"function"`` or ``"subroutine"``.
- ``arguments`` is a sequence of ``FortranArgument``.
- For functions, optionally set ``result`` (a ``FortranArgument``) to document the
  result variable.

Derived types
-------------

Derived types are represented by ``FortranType``.

- components/attributes: ``FortranComponent``
- type-bound procedures: ``FortranTypeBoundProcedure``

Programs
--------

Programs are represented by ``FortranProgramInfo``.

If you can provide them:

- ``dependencies``: modules referenced via ``use`` statements
- ``procedures``: internal procedures after ``contains``
- ``source``: raw source string for the program unit

All of these are optional; you can start with just ``name``/``doc``/``location``.


Registering a Lexer Plugin
==========================

A plugin is typically a small Python package that exposes a Sphinx extension.
In its ``setup(app)`` function, register a lexer factory:

.. code-block:: python

   from sphinx_fortran_domain.lexers import register_lexer

   def setup(app):
       register_lexer("my-lexer", lambda: MyLexer())
       return {"version": "0.1.0", "parallel_read_safe": True}

Then, in the consuming project's ``conf.py``:

.. code-block:: python

   extensions = [
       "my_fortran_lexer_plugin",  # registers the lexer
       "sphinx_fortran_domain",
   ]

   fortran_lexer = "my-lexer"


Reference Plugin (Concrete Example)
===================================

This section shows a minimal, end-to-end "reference plugin" that you can copy
as a starting point.

It consists of:

* a Python module that registers a lexer via ``register_lexer``
* a project ``conf.py`` that enables the plugin and selects the lexer
* a minimal Fortran source file that the lexer parses

The plugin module
-----------------

Create a module (or package) that Sphinx can import, for example
``reference_plugin.py``:

For a fully working (tested) reference implementation, see
``tests/fixtures/reference_plugin.py`` in this repository.

.. code-block:: python

   from __future__ import annotations

    import re
    from typing import Dict, Sequence

   from sphinx_fortran_domain.lexers import (
       FortranLexer,
       FortranModuleInfo,
       FortranParseResult,
       SourceLocation,
       register_lexer,
   )

   from sphinx_fortran_domain.utils import extract_predoc_before_line, read_lines_utf8


   _RE_MODULE = re.compile(r"^\s*module\s+(?!procedure\b)([A-Za-z_]\w*)\b", re.IGNORECASE)


   class ReferenceLexer(FortranLexer):
       name = "reference"

       def parse(self, file_paths: Sequence[str], *, doc_markers: Sequence[str]) -> FortranParseResult:
           modules: Dict[str, FortranModuleInfo] = {}
           for file_path in file_paths:
               lines = read_lines_utf8(file_path)
               for idx, line in enumerate(lines):
                   m = _RE_MODULE.match(line)
                   if not m:
                       continue
                   name = m.group(1)
                   doc = extract_predoc_before_line(lines, idx, doc_markers=doc_markers)
                   modules[name] = FortranModuleInfo(
                       name=name,
                       doc=doc,
                       location=SourceLocation(path=str(file_path), lineno=idx + 1),
                   )
                   break
           return FortranParseResult(modules=modules, submodules={}, programs={})


   def setup(app):
       # The registry stores a factory; Sphinx will call it when parsing starts.
       register_lexer("reference", lambda: ReferenceLexer())
       return {"version": "0.1.0", "parallel_read_safe": True}


Enable it in a consuming project's conf.py
------------------------------------------

In the consuming project (the docs you are building), enable both the plugin
and this domain:

.. code-block:: python

   extensions = [
       "reference_plugin",      # registers the lexer
       "sphinx_fortran_domain", # uses the registered lexer
   ]

   fortran_lexer = "reference"


Minimal Fortran input
---------------------

With the default doc marker ``!>``, a minimal module might look like:

.. code-block:: fortran

   !> This is a test module.
   module mymod
   end module mymod

When you run Sphinx, parsing starts at ``builder-inited`` and your lexer is
invoked with the collected ``fortran_sources``.
