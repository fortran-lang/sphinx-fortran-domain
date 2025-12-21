from __future__ import annotations

from typing import Sequence

from sphinx_fortran_domain.lexers import FortranLexer, FortranParseResult


class LFortranLexer(FortranLexer):
    """Placeholder lexer for LFortran integration.

    The core project stays dependency-light; LFortran bindings/CLI can be wired
    from a small companion package.
    """

    name = "lfortran"

    def parse(self, file_paths: Sequence[str], *, doc_markers: Sequence[str]) -> FortranParseResult:
        raise NotImplementedError(
            "LFortran lexer is not implemented in the core package. "
            "Install an integration package or use fortran_lexer='regex'."
        )
