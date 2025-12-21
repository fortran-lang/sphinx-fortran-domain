from __future__ import annotations

from typing import Sequence

from sphinx_fortran_domain.lexers import FortranLexer, FortranParseResult


class Fparser2FortranLexer(FortranLexer):
	"""Placeholder lexer for fparser2 integration.

	Kept as a stub to avoid forcing heavy dependencies for the base domain.
	"""

	name = "fparser2"

	def parse(self, file_paths: Sequence[str], *, doc_markers: Sequence[str]) -> FortranParseResult:
		raise NotImplementedError(
			"fparser2 lexer is not implemented in the core package. "
			"Install an integration package or use fortran_lexer='regex'."
		)
