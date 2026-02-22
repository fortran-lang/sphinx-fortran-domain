from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from sphinx_fortran_domain.utils import (
	find_inline_doc as _find_inline_doc,
	is_doc_line as _is_doc_line,
	read_lines_utf8,
	strip_inline_comment as _strip_inline_comment,
)

from sphinx_fortran_domain.lexers import (
	FortranArgument,
	FortranComponent,
	FortranInterface,
	FortranLexer,
	FortranModuleInfo,
	FortranParseResult,
	FortranProcedure,
	FortranProgramInfo,
	FortranSubmoduleInfo,
	FortranType,
	FortranTypeBoundProcedure,
	FortranVariable,
	SourceLocation,
)


_RE_MODULE = re.compile(r"^\s*module\s+(?!procedure\b)([A-Za-z_]\w*)\b", re.IGNORECASE)
_RE_END_MODULE = re.compile(r"^\s*end\s*module\b", re.IGNORECASE)
_RE_SUBMODULE = re.compile(
	r"^\s*submodule\s*\(\s*([A-Za-z_]\w*)\s*\)\s*([A-Za-z_]\w*)\b", re.IGNORECASE
)
_RE_END_SUBMODULE = re.compile(r"^\s*end\s*submodule\b", re.IGNORECASE)
_RE_PROGRAM = re.compile(r"^\s*program\s+([A-Za-z_]\w*)\b", re.IGNORECASE)
_RE_END_PROGRAM = re.compile(r"^\s*end\s*program\b", re.IGNORECASE)
_RE_CONTAINS = re.compile(r"^\s*contains\b", re.IGNORECASE)
_RE_USE = re.compile(
	r"^\s*use\b\s*(?:,\s*(?:non_intrinsic|intrinsic)\s*)?(?:\s*::\s*)?([A-Za-z_]\w*)\b",
	re.IGNORECASE,
)
# Derived type definition: `type [,...] :: name`.
# Avoid matching declarations like `type(foo) :: var` (note the parentheses).
_RE_TYPE_DEF = re.compile(
	r"^\s*type\b(?!\s*\()(?P<attrs>[^!]*)::\s*(?P<name>[A-Za-z_]\w*)\b",
	re.IGNORECASE,
)
_RE_END_TYPE = re.compile(r"^\s*end\s*type\b", re.IGNORECASE)
_RE_TYPE_PROC_BIND = re.compile(
	r"^\s*procedure\b(?P<attrs>[^!]*)::\s*(?P<name>[A-Za-z_]\w*)\b(?:\s*=>\s*(?P<target>[A-Za-z_]\w*)\b)?",
	re.IGNORECASE,
)
_RE_END_PROC = re.compile(r"^\s*end\s*(subroutine|function)\b", re.IGNORECASE)
_RE_RESULT = re.compile(r"\bresult\s*\(\s*([A-Za-z_]\w*)\s*\)", re.IGNORECASE)


def _match_proc(line: str) -> Optional[tuple[str, str, list[str], str]]:
	# Returns (kind, name, arg_names, raw_signature)
	# Handle both "pure function foo" and "real pure function foo".
	code = _strip_inline_comment(line)
	low = code.lower()
	if low.lstrip().startswith("end "):
		return None

	m = re.search(r"\bsubroutine\s+([A-Za-z_]\w*)\s*(?:\(([^)]*)\))?", code, flags=re.IGNORECASE)
	if m:
		name = m.group(1)
		args = (m.group(2) or "").strip()
		arg_names = [a.strip() for a in args.split(",") if a.strip()] if args else []
		return ("subroutine", name, arg_names, code.strip())

	m = re.search(r"\bfunction\s+([A-Za-z_]\w*)\s*(?:\(([^)]*)\))?", code, flags=re.IGNORECASE)
	if m:
		name = m.group(1)
		args = (m.group(2) or "").strip()
		arg_names = [a.strip() for a in args.split(",") if a.strip()] if args else []
		return ("function", name, arg_names, code.strip())

	return None


def _split_top_level_commas(text: str) -> List[str]:
	parts: List[str] = []
	buf: List[str] = []
	depth = 0
	for ch in text:
		if ch == "(":
			depth += 1
		elif ch == ")" and depth > 0:
			depth -= 1
		if ch == "," and depth == 0:
			parts.append("".join(buf))
			buf = []
		else:
			buf.append(ch)
	parts.append("".join(buf))
	return parts


def _declared_names_from_declaration(line: str) -> List[str]:
	code = _strip_inline_comment(line)
	if "::" not in code:
		return []
	after = code.split("::", 1)[1]
	names: List[str] = []
	for token in _split_top_level_commas(after):
		t = token.strip()
		if not t:
			continue
		# Remove initializations and attributes.
		t = t.split("=", 1)[0].strip()
		m = re.match(r"^([A-Za-z_]\w*)\b", t)
		if m:
			names.append(m.group(1))
	return names


def _decl_from_declaration(line: str) -> Optional[str]:
	code = _strip_inline_comment(line).strip()
	if "::" not in code:
		return None
	left = code.split("::", 1)[0].strip()
	return left or None


def _dims_from_declaration(line: str) -> Dict[str, str]:
	"""Extract per-variable array specs from a declaration line.

	Example: "real, intent(in) :: a(:), b(1:3)" -> {"a": ":", "b": "1:3"}
	"""
	code = _strip_inline_comment(line)
	if "::" not in code:
		return {}
	after = code.split("::", 1)[1]
	out: Dict[str, str] = {}
	for token in _split_top_level_commas(after):
		t = token.strip()
		if not t:
			continue
		# Remove initializations.
		lhs = t.split("=", 1)[0].strip()
		m = re.match(r"^([A-Za-z_]\w*)\s*\(([^)]*)\)", lhs)
		if not m:
			continue
		name = m.group(1)
		dims = (m.group(2) or "").strip()
		if name and dims:
			out[name] = dims
	return out


def _inits_from_declaration(line: str) -> Dict[str, str]:
	"""Extract per-variable initializer from a declaration line.

	Example: "real :: a = 1.0, b(3) = 0.0" -> {"a": "1.0", "b": "0.0"}
	"""
	code = _strip_inline_comment(line)
	if "::" not in code:
		return {}
	after = code.split("::", 1)[1]
	out: Dict[str, str] = {}
	for token in _split_top_level_commas(after):
		t = token.strip()
		if not t or "=" not in t:
			continue
		lhs, rhs = t.split("=", 1)
		lhs = lhs.strip()
		rhs = rhs.strip()
		m = re.match(r"^([A-Za-z_]\w*)\b", lhs)
		if m and rhs:
			out[m.group(1)] = rhs
	return out


def _normalize_proc_signature(raw: str) -> str:
	# Convert "... result(res)" into "... -> res" for functions.
	s = " ".join(raw.split())
	m = _RE_RESULT.search(s)
	if m:
		res = m.group(1)
		s = _RE_RESULT.sub("", s).strip()
		s = f"{s} -> {res}"
	return s


def _match_interface(line: str) -> Optional[str]:
	code = _strip_inline_comment(line)
	low = code.lower().strip()
	if low.startswith("end interface"):
		return None
	m = re.match(r"^\s*(?:abstract\s+)?interface\s+([A-Za-z_]\w*)\b", code, flags=re.IGNORECASE)
	if not m:
		return None
	return m.group(1)

class RegexFortranLexer(FortranLexer):
	name = "regex"

	def parse(self, file_paths: Sequence[str], *, doc_markers: Sequence[str]) -> FortranParseResult:
		modules: Dict[str, FortranModuleInfo] = {}
		submodules: Dict[str, FortranSubmoduleInfo] = {}
		programs: Dict[str, FortranProgramInfo] = {}

		for path in file_paths:
			lines = read_lines_utf8(path)
			self._parse_file(
				path,
				lines,
				modules=modules,
				submodules=submodules,
				programs=programs,
				doc_markers=doc_markers,
			)

		return FortranParseResult(modules=modules, submodules=submodules, programs=programs)

	def _parse_file(
		self,
		path: str,
		lines: List[str],
		*,
		modules: Dict[str, FortranModuleInfo],
		submodules: Dict[str, FortranSubmoduleInfo],
		programs: Dict[str, FortranProgramInfo],
		doc_markers: Sequence[str],
	) -> None:
		pending_doc: List[str] = []
		scope_kind: Optional[str] = None  # "module" | "submodule" | "program"
		scope_name: Optional[str] = None
		scope_parent: Optional[str] = None
		in_header_doc_phase = False
		header_doc_inline_open = False
		header_doc_inline_seen = False
		current_program_lines: List[str] | None = None
		in_program_contains = False
		current_program_deps: set[str] | None = None
		in_scope_contains = False  # for module/submodule
		scope_vars_seen: set[str] = set()

		proc_stack: List[dict] = []
		current_proc: Optional[dict] = None
		current_type: Optional[dict] = None

		def flush_doc() -> Optional[str]:
			nonlocal pending_doc
			if not pending_doc:
				return None
			doc = "\n".join(pending_doc).rstrip()
			pending_doc = []
			return doc

		def add_to_pending(text: str) -> None:
			pending_doc.append(text)

		def add_module_doc_line(text: str) -> None:
			nonlocal modules
			if scope_kind != "module" or not scope_name:
				return
			current = modules.get(scope_name)
			if current is None:
				return
			updated = (current.doc + "\n" + text).strip() if current.doc else text.strip()
			modules[scope_name] = FortranModuleInfo(
				name=current.name,
				doc=updated,
				variables=getattr(current, "variables", ()),
				procedures=current.procedures,
				types=current.types,
				interfaces=current.interfaces,
				location=current.location,
			)

		def add_submodule_doc_line(text: str) -> None:
			nonlocal submodules
			if scope_kind != "submodule" or not scope_name:
				return
			current = submodules.get(scope_name)
			if current is None:
				return
			updated = (current.doc + "\n" + text).strip() if current.doc else text.strip()
			submodules[scope_name] = FortranSubmoduleInfo(
				name=current.name,
				parent=current.parent,
				doc=updated,
				variables=getattr(current, "variables", ()),
				procedures=current.procedures,
				types=current.types,
				interfaces=current.interfaces,
				location=current.location,
			)

		def add_program_doc_line(text: str) -> None:
			if scope_kind != "program" or not scope_name:
				return
			current = programs.get(scope_name)
			if current is None:
				return
			updated = (current.doc + "\n" + text).strip() if current.doc else text.strip()
			programs[scope_name] = FortranProgramInfo(
				name=current.name,
				doc=updated,
				location=current.location,
				dependencies=getattr(current, "dependencies", ()),
				procedures=getattr(current, "procedures", ()),
				source=getattr(current, "source", None),
			)

		for idx, raw in enumerate(lines, start=1):
			# While inside a program unit, capture the full program source.
			if scope_kind == "program" and scope_name and current_program_lines is not None:
				current_program_lines.append(raw)

			# Collect program dependencies from USE statements up to CONTAINS.
			if scope_kind == "program" and scope_name and not in_program_contains:
				code = _strip_inline_comment(raw)
				muse = _RE_USE.match(code)
				if muse and current_program_deps is not None:
					modname = (muse.group(1) or "").strip()
					if modname:
						current_program_deps.add(modname)

			# If we are inside a procedure, allow parsing of inline/preceding arg docs.
			doc_text = _is_doc_line(raw, doc_markers)
			if doc_text is not None:
				if current_proc is not None and current_proc.get("in_proc_doc_phase"):
					# Doc lines immediately after a signature are ambiguous:
					# - If the next non-doc statement is an argument declaration, they document that argument.
					# - Otherwise they are procedure-level docs.
					# Buffer them until we see the next non-doc statement.
					current_proc["post_sig_doc_buffer"].append(doc_text)
					continue
				if current_type is not None:
					# Doc inside a derived type applies to the next component/binding.
					add_to_pending(doc_text)
					continue
				if in_header_doc_phase:
					if scope_kind in {"module", "submodule"}:
						if header_doc_inline_open:
							# Doc lines immediately after the module/submodule statement
							# are treated as container-level docs. If a blank line occurs first,
							# header_doc_inline_open will be False and docs attach to the next symbol.
							if scope_kind == "module":
								add_module_doc_line(doc_text)
							else:
								add_submodule_doc_line(doc_text)
							header_doc_inline_seen = True
						else:
							add_to_pending(doc_text)
					else:
						# For programs, we render doc markers from the embedded source to avoid duplication.
						add_to_pending(doc_text)
				else:
					add_to_pending(doc_text)
				continue

			if raw.strip() == "":
				# Keep doc blocks intact through blank lines.
				if in_header_doc_phase and scope_kind in {"module", "submodule"} and not header_doc_inline_seen:
					header_doc_inline_open = False
				if current_proc is not None and current_proc.get("in_proc_doc_phase"):
					current_proc["post_sig_doc_buffer"].append("")
				elif current_type is not None and pending_doc:
					pending_doc.append("")
				elif pending_doc:
					pending_doc.append("")
				continue

			line = raw

			if current_proc is not None and current_proc.get("in_proc_doc_phase"):
				# First non-doc, non-blank line ends the post-signature doc phase.
				# If the line is an argument declaration, treat buffered doc as pending arg docs.
				buffer = list(current_proc.get("post_sig_doc_buffer") or [])
				declared = _declared_names_from_declaration(line)
				is_arg_decl = bool(declared) and any(n in current_proc.get("arg_set", set()) for n in declared)
				if buffer:
					if is_arg_decl:
						pending_doc = buffer
					else:
						current_proc["proc_doc_lines"].extend(buffer)
				current_proc["post_sig_doc_buffer"] = []
				current_proc["in_proc_doc_phase"] = False

			if current_type is not None:
				# We are inside a derived type definition.
				if _RE_END_TYPE.match(line):
					entry = FortranType(
						name=current_type["name"],
						doc=current_type.get("doc"),
						components=tuple(current_type.get("components", [])),
						bound_procedures=tuple(current_type.get("bound_procedures", [])),
						location=current_type.get("location"),
					)
					if current_type["container_kind"] == "module":
						container = modules.get(current_type["container_name"])  # type: ignore[arg-type]
						if container:
							modules[current_type["container_name"]] = FortranModuleInfo(
								name=container.name,
								doc=container.doc,
								variables=getattr(container, "variables", ()),
								procedures=container.procedures,
								types=[*container.types, entry],
								interfaces=container.interfaces,
								location=container.location,
							)
					elif current_type["container_kind"] == "submodule":
						container = submodules.get(current_type["container_name"])  # type: ignore[arg-type]
						if container:
							submodules[current_type["container_name"]] = FortranSubmoduleInfo(
								name=container.name,
								parent=container.parent,
								doc=container.doc,
								variables=getattr(container, "variables", ()),
								procedures=container.procedures,
								types=[*container.types, entry],
								interfaces=container.interfaces,
								location=container.location,
							)

					current_type = None
					pending_doc = []
					continue

				if _RE_CONTAINS.match(line):
					current_type["in_type_contains"] = True
					pending_doc = []
					continue

				# Type-bound procedure bindings
				if current_type.get("in_type_contains"):
					inline = _find_inline_doc(line, doc_markers)
					doc_inline: Optional[str] = None
					code_part = line
					if inline is not None:
						pos, marker = inline
						code_part = line[:pos].rstrip()
						doc_inline = line[pos + len(marker) :].strip() or None
						pending_doc = []

					m = _RE_TYPE_PROC_BIND.match(code_part)
					if m:
						name = m.group("name")
						target = m.group("target") or name
						doc = flush_doc()
						if doc_inline:
							doc = f"{doc}\n{doc_inline}".strip() if doc else doc_inline
						current_type["bound_procedures"].append(
							FortranTypeBoundProcedure(
								name=name,
								target=target,
								doc=doc,
								location=SourceLocation(path=path, lineno=idx),
							)
						)
						continue

				# Components (member declarations) before type CONTAINS.
				inline = _find_inline_doc(line, doc_markers)
				doc_inline = None
				code_part = line
				if inline is not None:
					pos, marker = inline
					code_part = line[:pos].rstrip()
					doc_inline = line[pos + len(marker) :].strip() or None
					pending_doc = []

				# Skip non-declaration statements.
				low = _strip_inline_comment(code_part).strip().lower()
				if low.startswith(("procedure", "generic", "final", "private", "public", "type")):
					pending_doc = []
					continue

				names = _declared_names_from_declaration(code_part)
				decl = _decl_from_declaration(code_part)
				dims = _dims_from_declaration(code_part)
				inits = _inits_from_declaration(code_part)
				if names and decl:
					doc = flush_doc()
					if doc_inline:
						doc = f"{doc}\n{doc_inline}".strip() if doc else doc_inline
					for n in names:
						decl_n = decl
						dim_n = dims.get(n)
						if dim_n and "dimension" not in (decl_n or "").lower():
							decl_n = f"{decl_n}, dimension({dim_n})".strip(", ")
						init_n = inits.get(n)
						if init_n:
							decl_n = (
								f"{decl_n}, Default = {init_n}".strip(", ") if decl_n else f"Default = {init_n}"
							)
						current_type["components"].append(
							FortranComponent(
								name=n,
								decl=decl_n,
								doc=doc,
								location=SourceLocation(path=path, lineno=idx),
							)
						)
					continue

				# Anything else inside a type breaks a pending-doc chain.
				pending_doc = []
				continue

			if current_proc is not None and _RE_END_PROC.match(line):
				# Finalize the current (innermost) procedure. Nested internal procedures
				# are ignored for documentation purposes; only depth-1 procedures are
				# emitted into the module/submodule/program API.
				finished = proc_stack.pop() if proc_stack else current_proc
				current_proc = proc_stack[-1] if proc_stack else None

				kind = finished["kind"]
				name = finished["name"]
				arg_order: List[str] = finished["arg_order"]
				arg_docs: Dict[str, str] = finished["arg_docs"]
				arg_decls: Dict[str, str] = finished["arg_decls"]
				args: List[FortranArgument] = []
				for aname in arg_order:
					doc = arg_docs.get(aname)
					decl = arg_decls.get(aname)
					args.append(FortranArgument(name=aname, decl=decl, doc=doc, location=None))

				# Merge doc captured before signature with the doc captured after signature.
				proc_doc = finished.get("doc")
				post = "\n".join(finished.get("proc_doc_lines", [])).strip() or None
				if proc_doc and post:
					proc_doc = f"{proc_doc}\n{post}".strip()
				elif post:
					proc_doc = post

				entry = FortranProcedure(
					name=name,
					kind=kind,
					signature=finished.get("signature"),
					doc=proc_doc,
					location=finished["location"],
					arguments=tuple(args),
					result=(
						FortranArgument(
							name=str(finished.get("result_name")),
							decl=finished.get("result_decl"),
							doc=finished.get("result_doc"),
							location=None,
						)
						if kind == "function"
						and finished.get("result_name")
						and (finished.get("result_decl") is not None or finished.get("result_doc") is not None)
						else None
					),
				)

				if finished.get("nesting_depth", 1) == 1:
					if finished["container_kind"] == "module":
						container = modules.get(finished["container_name"])  # type: ignore[arg-type]
						if container:
							modules[finished["container_name"]] = FortranModuleInfo(
								name=container.name,
								doc=container.doc,
								variables=getattr(container, "variables", ()),
								procedures=[*container.procedures, entry],
								types=container.types,
								interfaces=container.interfaces,
								location=container.location,
							)
					elif finished["container_kind"] == "submodule":
						container = submodules.get(finished["container_name"])  # type: ignore[arg-type]
						if container:
							submodules[finished["container_name"]] = FortranSubmoduleInfo(
								name=container.name,
								parent=container.parent,
								doc=container.doc,
								variables=getattr(container, "variables", ()),
								procedures=[*container.procedures, entry],
								types=container.types,
								interfaces=container.interfaces,
								location=container.location,
							)
					elif finished["container_kind"] == "program":
						container = programs.get(finished["container_name"])  # type: ignore[arg-type]
						if container:
							programs[finished["container_name"]] = FortranProgramInfo(
								name=container.name,
								doc=container.doc,
								location=container.location,
								dependencies=getattr(container, "dependencies", ()),
								procedures=[*getattr(container, "procedures", ()), entry],
								source=getattr(container, "source", None),
							)

				pending_doc = []
				continue

			# Scope transitions
			m = _RE_MODULE.match(line)
			if m and scope_kind is None:
				name = m.group(1)
				modules[name] = FortranModuleInfo(
					name=name,
					doc=flush_doc(),
					variables=[],
					procedures=[],
					types=[],
					interfaces=[],
					location=SourceLocation(path=path, lineno=idx),
				)
				scope_kind = "module"
				scope_name = name
				scope_parent = None
				in_header_doc_phase = True
				header_doc_inline_open = True
				header_doc_inline_seen = False
				in_scope_contains = False
				scope_vars_seen = set()
				continue

			m = _RE_SUBMODULE.match(line)
			if m and scope_kind is None:
				parent, name = m.group(1), m.group(2)
				submodules[name] = FortranSubmoduleInfo(
					name=name,
					parent=parent,
					doc=flush_doc(),
					variables=[],
					procedures=[],
					types=[],
					interfaces=[],
					location=SourceLocation(path=path, lineno=idx),
				)
				scope_kind = "submodule"
				scope_name = name
				scope_parent = parent
				in_header_doc_phase = True
				header_doc_inline_open = True
				header_doc_inline_seen = False
				in_scope_contains = False
				scope_vars_seen = set()
				continue

			m = _RE_PROGRAM.match(line)
			if m and scope_kind is None:
				name = m.group(1)
				programs[name] = FortranProgramInfo(
					name=name,
					doc=flush_doc(),
					location=SourceLocation(path=path, lineno=idx),
					dependencies=(),
					procedures=[],
					source=None,
				)
				scope_kind = "program"
				scope_name = name
				scope_parent = None
				in_header_doc_phase = True
				header_doc_inline_open = False
				header_doc_inline_seen = False
				in_scope_contains = False
				scope_vars_seen = set()
				# Seed capture with the current `program ...` line.
				current_program_lines = [raw]
				in_program_contains = False
				current_program_deps = set()
				continue

			if scope_kind == "module" and _RE_END_MODULE.match(line):
				scope_kind = None
				scope_name = None
				scope_parent = None
				in_header_doc_phase = False
				header_doc_inline_open = False
				header_doc_inline_seen = False
				in_scope_contains = False
				scope_vars_seen = set()
				pending_doc = []
				continue

			if scope_kind == "submodule" and _RE_END_SUBMODULE.match(line):
				scope_kind = None
				scope_name = None
				scope_parent = None
				in_header_doc_phase = False
				header_doc_inline_open = False
				header_doc_inline_seen = False
				in_scope_contains = False
				scope_vars_seen = set()
				pending_doc = []
				continue

			if scope_kind == "program" and _RE_END_PROGRAM.match(line):
				# Finalize program unit and attach captured program source + dependencies.
				if scope_name and current_program_lines is not None:
					current = programs.get(scope_name)
					if current is not None:
						programs[scope_name] = FortranProgramInfo(
							name=current.name,
							doc=current.doc,
							location=current.location,
							procedures=getattr(current, "procedures", ()),
							dependencies=tuple(sorted((current_program_deps or set()))),
							source="\n".join(current_program_lines),
						)
				scope_kind = None
				scope_name = None
				scope_parent = None
				in_header_doc_phase = False
				header_doc_inline_open = False
				header_doc_inline_seen = False
				in_scope_contains = False
				scope_vars_seen = set()
				current_program_lines = None
				in_program_contains = False
				current_program_deps = None
				pending_doc = []
				continue

			if in_header_doc_phase:
				# Header doc phase ends at the first non-doc statement other than implicit/use/private/public.
				stripped = _strip_inline_comment(line).strip().lower()
				if stripped.startswith(("use ", "implicit ", "private", "public")):
					continue
				if _RE_CONTAINS.match(line):
					if scope_kind == "program":
						in_program_contains = True
					elif scope_kind in {"module", "submodule"}:
						in_scope_contains = True
					in_header_doc_phase = False
					continue
				# Any other statement ends header doc collection.
				in_header_doc_phase = False

			# Program CONTAINS marks the transition to internal procedures.
			if scope_kind == "program" and _RE_CONTAINS.match(line):
				in_program_contains = True
				pending_doc = []
				continue

			# Module/Submodule CONTAINS marks the transition to procedures.
			if scope_kind in {"module", "submodule"} and _RE_CONTAINS.match(line):
				in_scope_contains = True
				pending_doc = []
				continue

			# Collect symbols into the current scope
			# Variables (module/submodule spec-part, before CONTAINS)
			if (
				scope_kind in {"module", "submodule"}
				and scope_name
				and not in_scope_contains
				and current_proc is None
				and current_type is None
			):
				inline = _find_inline_doc(line, doc_markers)
				doc_inline: Optional[str] = None
				code_part = line
				if inline is not None:
					pos, marker = inline
					code_part = line[:pos].rstrip()
					doc_inline = line[pos + len(marker) :].strip() or None
					# Inline docs shouldn't merge with prior pending docs.
					pending_doc = []

				decl = _decl_from_declaration(code_part)
				names = _declared_names_from_declaration(code_part)
				decl_low = (decl or "").strip().lower()
				is_stmt_with_colon = decl_low.startswith(
					(
						"public",
						"private",
						"protected",
						"generic",
						"procedure",
						"import",
						"use",
					)
				)
				is_type_def = bool(_RE_TYPE_DEF.match(code_part))

				if names and decl and not is_stmt_with_colon and not is_type_def:
					dims = _dims_from_declaration(code_part)
					inits = _inits_from_declaration(code_part)
					doc = flush_doc()
					if doc_inline:
						doc = f"{doc}\n{doc_inline}".strip() if doc else doc_inline

					new_vars: List[FortranVariable] = []
					for n in names:
						key = n.lower()
						if key in scope_vars_seen:
							continue
						scope_vars_seen.add(key)

						decl_n = decl
						dim_n = dims.get(n)
						if dim_n and "dimension" not in (decl_n or "").lower():
							decl_n = f"{decl_n}, dimension({dim_n})".strip(", ")
						init_n = inits.get(n)
						if init_n:
							decl_n = f"{decl_n}, Default = {init_n}".strip(", ") if decl_n else f"Default = {init_n}"

						new_vars.append(
							FortranVariable(
								name=n,
								decl=decl_n,
								doc=doc,
								location=SourceLocation(path=path, lineno=idx),
							)
						)

					if new_vars:
						if scope_kind == "module":
							container = modules.get(scope_name)
							if container:
								modules[scope_name] = FortranModuleInfo(
									name=container.name,
									doc=container.doc,
									variables=[*getattr(container, "variables", ()), *new_vars],
									procedures=container.procedures,
									types=container.types,
									interfaces=container.interfaces,
									location=container.location,
								)
						else:
							container = submodules.get(scope_name)
							if container:
								submodules[scope_name] = FortranSubmoduleInfo(
									name=container.name,
									parent=container.parent,
									doc=container.doc,
									variables=[*getattr(container, "variables", ()), *new_vars],
									procedures=container.procedures,
									types=container.types,
									interfaces=container.interfaces,
									location=container.location,
								)

					pending_doc = []
					continue

			proc = _match_proc(line)
			if proc and scope_name and (
				scope_kind in {"module", "submodule"}
				or (scope_kind == "program" and in_program_contains)
			):
				kind, name, arg_order, raw_sig = proc
				pre_sig_doc = flush_doc()
				new_proc = {
					"kind": kind,
					"name": name,
					"doc": pre_sig_doc,
					"location": SourceLocation(path=path, lineno=idx),
					"container_kind": scope_kind,
					"container_name": scope_name,
					"nesting_depth": len(proc_stack) + 1,
					"result_name": None,
					"result_doc": None,
					"result_decl": None,
					"arg_order": arg_order,
					"arg_set": set(arg_order),
					"arg_docs": {},
					"arg_decls": {},
					"proc_doc_lines": [],
					"post_sig_doc_buffer": [],
					# If there is already doc before the signature, treat any post-signature
					# doc lines as argument docs (not additional procedure docs).
					"in_proc_doc_phase": pre_sig_doc is None,
					"signature": _normalize_proc_signature(raw_sig),
				}
				proc_stack.append(new_proc)
				current_proc = new_proc
				if kind == "function":
					mres = _RE_RESULT.search(raw_sig)
					current_proc["result_name"] = mres.group(1) if mres else name
				continue

			if current_proc is not None:
				# Inline arg docs (declarations like: integer :: a !> doc)
				inline = _find_inline_doc(line, doc_markers)
				if inline is not None:
					pos, marker = inline
					code_part = line[:pos].rstrip()
					doc_part = line[pos + len(marker) :].strip()
					if doc_part:
						decl = _decl_from_declaration(code_part)
						dims = _dims_from_declaration(code_part)
						for n in _declared_names_from_declaration(code_part):
							if n in current_proc["arg_set"]:
								if n not in current_proc["arg_decls"]:
									decl_n = decl
									dim_n = dims.get(n)
									if dim_n and (decl_n is None or "dimension" not in decl_n.lower()):
										decl_n = f"{decl_n}, dimension({dim_n})".strip(", ") if decl_n else f"dimension({dim_n})"
									if decl_n:
										current_proc["arg_decls"][n] = decl_n
								prev = current_proc["arg_docs"].get(n)
								current_proc["arg_docs"][n] = (prev + "\n" + doc_part).strip() if prev else doc_part
							elif n == current_proc.get("result_name"):
								if current_proc.get("result_decl") is None:
									decl_n = decl
									dim_n = dims.get(n)
									if dim_n and (decl_n is None or "dimension" not in decl_n.lower()):
										decl_n = f"{decl_n}, dimension({dim_n})".strip(", ") if decl_n else f"dimension({dim_n})"
									if decl_n:
										current_proc["result_decl"] = decl_n
								prev = current_proc.get("result_doc")
								current_proc["result_doc"] = (prev + "\n" + doc_part).strip() if prev else doc_part
						pending_doc = []
						continue

				# Preceding arg docs (doc-only lines right above a declaration)
				if pending_doc:
					declared = _declared_names_from_declaration(line)
					if declared:
						decl = _decl_from_declaration(line)
						dims = _dims_from_declaration(line)
						doc_part = flush_doc()
						if doc_part:
							for n in declared:
								if n in current_proc["arg_set"]:
									if n not in current_proc["arg_decls"]:
										decl_n = decl
										dim_n = dims.get(n)
										if dim_n and (decl_n is None or "dimension" not in decl_n.lower()):
											decl_n = f"{decl_n}, dimension({dim_n})".strip(", ") if decl_n else f"dimension({dim_n})"
										if decl_n:
											current_proc["arg_decls"][n] = decl_n
									prev = current_proc["arg_docs"].get(n)
									current_proc["arg_docs"][n] = (prev + "\n" + doc_part).strip() if prev else doc_part
								elif n == current_proc.get("result_name"):
									if current_proc.get("result_decl") is None:
										decl_n = decl
										dim_n = dims.get(n)
										if dim_n and (decl_n is None or "dimension" not in decl_n.lower()):
											decl_n = f"{decl_n}, dimension({dim_n})".strip(", ") if decl_n else f"dimension({dim_n})"
										if decl_n:
											current_proc["result_decl"] = decl_n
									prev = current_proc.get("result_doc")
									current_proc["result_doc"] = (prev + "\n" + doc_part).strip() if prev else doc_part
							continue

				# Capture declarations even without docs.
				decl = _decl_from_declaration(line)
				dims = _dims_from_declaration(line)
				for n in _declared_names_from_declaration(line):
					if n in current_proc["arg_set"] and n not in current_proc["arg_decls"]:
						decl_n = decl
						dim_n = dims.get(n)
						if dim_n and (decl_n is None or "dimension" not in decl_n.lower()):
							decl_n = f"{decl_n}, dimension({dim_n})".strip(", ") if decl_n else f"dimension({dim_n})"
						if decl_n:
							current_proc["arg_decls"][n] = decl_n
					elif n == current_proc.get("result_name") and current_proc.get("result_decl") is None:
						decl_n = decl
						dim_n = dims.get(n)
						if dim_n and (decl_n is None or "dimension" not in decl_n.lower()):
							decl_n = f"{decl_n}, dimension({dim_n})".strip(", ") if decl_n else f"dimension({dim_n})"
						if decl_n:
							current_proc["result_decl"] = decl_n

			t = _RE_TYPE_DEF.match(line)
			if t and scope_kind in {"module", "submodule"} and scope_name:
				name = t.group("name")
				current_type = {
					"name": name,
					"doc": flush_doc(),
					"location": SourceLocation(path=path, lineno=idx),
					"container_kind": scope_kind,
					"container_name": scope_name,
					"in_type_contains": False,
					"components": [],
					"bound_procedures": [],
				}
				continue

			iface = _match_interface(line)
			if iface and scope_kind in {"module", "submodule"} and scope_name:
				doc = flush_doc()
				entry = FortranInterface(name=iface, doc=doc, location=SourceLocation(path=path, lineno=idx))
				if scope_kind == "module":
					current = modules.get(scope_name)
					if current:
						modules[scope_name] = FortranModuleInfo(
							name=current.name,
							doc=current.doc,
							variables=getattr(current, "variables", ()),
							procedures=current.procedures,
							types=current.types,
							interfaces=[*current.interfaces, entry],
							location=current.location,
						)
				else:
					current = submodules.get(scope_name)
					if current:
						submodules[scope_name] = FortranSubmoduleInfo(
							name=current.name,
							parent=current.parent,
							doc=current.doc,
							variables=getattr(current, "variables", ()),
							procedures=current.procedures,
							types=current.types,
							interfaces=[*current.interfaces, entry],
							location=current.location,
						)
				continue

			# Any non-doc, non-blank line breaks the "pending doc" chain.
			pending_doc = []
