from __future__ import annotations

import re
from typing import Dict, List, Sequence

from sphinx_fortran_domain.lexers import (
	FortranComponent,
	FortranProcedure,
	FortranType,
	FortranLexer,
	FortranModuleInfo,
	FortranParseResult,
	SourceLocation,
	register_lexer,
)

from sphinx_fortran_domain.utils import (
	extract_predoc_before_line,
	read_lines_utf8,
	strip_inline_comment,
)


_RE_MODULE = re.compile(r"^\s*module\s+(?!procedure\b)([A-Za-z_]\w*)\b", re.IGNORECASE)
_RE_END_MODULE = re.compile(r"^\s*end\s*module\b", re.IGNORECASE)
_RE_CONTAINS = re.compile(r"^\s*contains\b", re.IGNORECASE)

_RE_TYPE_DEF = re.compile(r"^\s*type\b(?!\s*\()(?P<attrs>[^!]*)::\s*(?P<name>[A-Za-z_]\w*)\b", re.IGNORECASE)
_RE_END_TYPE = re.compile(r"^\s*end\s*type\b", re.IGNORECASE)

_RE_PROC = re.compile(
	r"^\s*(?:[A-Za-z_]\w*\s+)*\b(?P<kind>function|subroutine)\s+(?P<name>[A-Za-z_]\w*)\b",
	re.IGNORECASE,
)
_RE_END_PROC = re.compile(r"^\s*end\s*(?:function|subroutine)\b", re.IGNORECASE)


def _declared_names_from_declaration(line: str) -> List[str]:
	code = strip_inline_comment(line)
	if "::" not in code:
		return []
	after = code.split("::", 1)[1]
	parts = [p.strip() for p in after.split(",")]
	names: List[str] = []
	for p in parts:
		if not p:
			continue
		p = p.split("=", 1)[0].strip()
		m = re.match(r"^([A-Za-z_]\w*)\b", p)
		if m:
			names.append(m.group(1))
	return names


def _decl_from_declaration(line: str) -> str | None:
	code = strip_inline_comment(line).strip()
	if "::" not in code:
		return None
	left = code.split("::", 1)[0].strip()
	return left or None


class ReferencePluginLexer(FortranLexer):
	"""A minimal reference lexer.

	This intentionally implements only a small subset:

	- modules
	- derived types + components
	- procedures (function/subroutine) at module scope

	The goal is to show the *shape* of a plugin lexer and the object model.
	"""

	name = "reference-plugin"

	def parse(self, file_paths: Sequence[str], *, doc_markers: Sequence[str]) -> FortranParseResult:
		modules: Dict[str, FortranModuleInfo] = {}

		for file_path in file_paths:
			lines = read_lines_utf8(file_path)
			for idx, line in enumerate(lines):
				m = _RE_MODULE.match(line)
				if not m:
					continue
				name = m.group(1)
				mod_doc = extract_predoc_before_line(lines, idx, doc_markers=doc_markers)

				procedures: List[FortranProcedure] = []
				types: List[FortranType] = []

				in_contains = False
				in_type: FortranType | None = None
				type_components: List[FortranComponent] = []

				j = idx + 1
				while j < len(lines):
					raw = lines[j]
					if _RE_END_MODULE.match(raw):
						break
					if _RE_CONTAINS.match(raw):
						in_contains = True
						j += 1
						continue

					# Derived type blocks (only handled before CONTAINS).
					if not in_contains and in_type is None:
						mt = _RE_TYPE_DEF.match(raw)
						if mt:
							tname = mt.group("name")
							tdoc = extract_predoc_before_line(lines, j, doc_markers=doc_markers)
							in_type = FortranType(
								name=str(tname),
								doc=tdoc,
								components=[],
								bound_procedures=[],
								location=SourceLocation(path=str(file_path), lineno=j + 1),
							)
							type_components = []
							j += 1
							continue

					if not in_contains and in_type is not None:
						if _RE_END_TYPE.match(raw):
							types.append(
								FortranType(
									name=in_type.name,
									doc=in_type.doc,
									components=type_components,
									bound_procedures=[],
									location=in_type.location,
								)
							)
							in_type = None
							type_components = []
							j += 1
							continue

						decl = _decl_from_declaration(raw)
						names = _declared_names_from_declaration(raw)
						if decl and names:
							cdoc = extract_predoc_before_line(lines, j, doc_markers=doc_markers)
							for cname in names:
								type_components.append(
									FortranComponent(
										name=cname,
										decl=decl,
										doc=cdoc,
										location=SourceLocation(path=str(file_path), lineno=j + 1),
									)
								)
						j += 1
						continue

					# Procedures (only at module scope, and only after CONTAINS).
					if in_contains:
						mp = _RE_PROC.match(raw)
						if mp:
							kind = mp.group("kind").lower()
							pname = mp.group("name")
							pdoc = extract_predoc_before_line(lines, j, doc_markers=doc_markers)
							procedures.append(
								FortranProcedure(
									name=str(pname),
									kind=str(kind),
									signature=strip_inline_comment(raw).strip() or None,
									doc=pdoc,
									location=SourceLocation(path=str(file_path), lineno=j + 1),
									arguments=(),
									result=None,
								)
							)
							# Skip to end of procedure to avoid matching nested definitions.
							j += 1
							while j < len(lines) and not _RE_END_PROC.match(lines[j]):
								j += 1
							j += 1
							continue

					j += 1

				modules[name] = FortranModuleInfo(
					name=name,
					doc=mod_doc,
					procedures=procedures,
					types=types,
					interfaces=[],
					location=SourceLocation(path=str(file_path), lineno=idx + 1),
				)
				break

		return FortranParseResult(modules=modules, submodules={}, programs={})


def setup(app):
	register_lexer("reference", lambda: ReferencePluginLexer())
	return {"version": "0.0", "parallel_read_safe": True, "parallel_write_safe": True}
