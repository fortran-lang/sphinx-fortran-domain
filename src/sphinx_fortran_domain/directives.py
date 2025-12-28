from __future__ import annotations

import os
import re
from pathlib import Path

from docutils import nodes
from docutils.parsers.rst import Directive
from docutils.parsers.rst import directives as rst_directives
from docutils.statemachine import StringList
from sphinx import addnodes
from sphinx.directives import ObjectDescription
from sphinx.util.parsing import nested_parse_to_nodes

from sphinx_fortran_domain.utils import collect_fortran_source_files, _as_list


_RE_DOC_SECTION = re.compile(r"^\s*##\s+(?P<title>\S.*?\S)\s*$")
_RE_FOOTNOTE_DEF = re.compile(r"^\s*\.\.\s*\[(?P<label>\d+|#)\]\s+")
_RE_END_PROGRAM = re.compile(r"^\s*end\s*program\b", re.IGNORECASE)
_RE_CONTAINS = re.compile(r"^\s*contains\b", re.IGNORECASE)
_RE_USE = re.compile(
	r"^\s*use\b\s*(?:,\s*(?:non_intrinsic|intrinsic)\s*)?(?:\s*::\s*)?([A-Za-z_]\w*)\b",
	re.IGNORECASE,
)


def _doc_markers_from_env(env) -> list[str]:
	"""Return configured Fortran doc markers (e.g. ['!>'])."""
	chars = getattr(getattr(env, "app", None), "config", None)
	chars = getattr(chars, "fortran_doc_chars", None)
	markers: list[str] = []
	if chars is not None:
		if isinstance(chars, str):
			chars_list = [c for c in chars if c.strip()]
		else:
			chars_list = [str(c) for c in (chars or [])]
		chars_list = [c for c in chars_list if c]
		if chars_list:
			markers = ["!" + c for c in chars_list]

	return markers or ["!>"]


def _collect_fortran_files_from_env(env) -> list[str]:
	app = getattr(env, "app", None)
	if app is None:
		return []
	confdir = Path(getattr(app, "confdir", os.getcwd()))
	config = getattr(app, "config", None)
	roots = _as_list(getattr(config, "fortran_sources", []))
	excludes = _as_list(getattr(config, "fortran_sources_exclude", []))
	exts = {e.lower() for e in _as_list(getattr(config, "fortran_file_extensions", []))}
	return collect_fortran_source_files(
		confdir=confdir,
		roots=roots,
		extensions=exts,
		excludes=excludes,
	)


def _find_program_in_file(lines: list[str], progname: str, *, start_at: int = 0) -> int | None:
	pat = re.compile(rf"^\s*program\s+{re.escape(str(progname))}\b", re.IGNORECASE)
	for i in range(max(start_at, 0), len(lines)):
		if pat.match(lines[i]):
			return i
	return None


def _extract_predoc_before_line(lines: list[str], idx: int, *, doc_markers: list[str]) -> str | None:
	if idx <= 0:
		return None
	markers = [m for m in (doc_markers or []) if m and m.strip()]
	buf: list[str] = []
	i = idx - 1
	while i >= 0:
		line = lines[i]
		stripped = line.lstrip()
		marker = next((m for m in markers if stripped.startswith(m)), None)
		if marker is None:
			break
		buf.append(stripped[len(marker) :].lstrip(" \t").rstrip())
		i -= 1
	if not buf:
		return None
	buf.reverse()
	text = "\n".join(buf).strip()
	return text or None


def _extract_use_dependencies_from_source(source: str) -> list[str]:
	deps: list[str] = []
	seen: set[str] = set()
	for raw in (source or "").splitlines():
		if _RE_CONTAINS.match(raw) or _RE_END_PROGRAM.match(raw):
			break
		code = raw.split("!", 1)[0]
		m = _RE_USE.match(code)
		if not m:
			continue
		name = (m.group(1) or "").strip()
		key = name.lower()
		if name and key not in seen:
			seen.add(key)
			deps.append(name)
	return deps


def _read_program_source_by_search(env, progname: str, *, doc_markers: list[str]) -> tuple[str | None, str | None]:
	"""Find and read a program unit by scanning configured fortran_sources.

	Returns (source, predoc) where predoc is doc lines immediately preceding
	the program statement (using configured doc_markers).
	"""
	files = _collect_fortran_files_from_env(env)
	if not files:
		return (None, None)

	for path in files:
		try:
			text = Path(path).read_text(encoding="utf-8", errors="replace")
		except OSError:
			continue
		lines = text.splitlines()
		start = _find_program_in_file(lines, progname)
		if start is None:
			continue

		predoc = _extract_predoc_before_line(lines, start, doc_markers=doc_markers)
		buf: list[str] = []
		for i in range(start, len(lines)):
			buf.append(lines[i])
			if _RE_END_PROGRAM.match(lines[i]):
				break
		return ("\n".join(buf), predoc)

	return (None, None)


def _split_out_examples_sections(text: str | None) -> tuple[str | None, str | None]:
	"""Split docstring into (main, examples) where examples are '## Example(s)' sections.

	We treat sections introduced by our lightweight marker syntax ("## Title").
	If the title is "Example" or "Examples" (case-insensitive), we extract that
	section (including its content until the next "##" marker) and return it
	separately so callers can render it at the end.
	"""
	if not text:
		return None, None

	lines = str(text).splitlines()
	main: list[str] = []
	examples: list[str] = []
	i = 0
	while i < len(lines):
		line = lines[i]
		m = _RE_DOC_SECTION.match(line)
		if not m:
			main.append(line)
			i += 1
			continue

		title = (m.group("title") or "").strip().lower()
		is_examples = title in {"example", "examples"}

		# Capture this section (header + body until next section header).
		section_lines: list[str] = [line]
		i += 1
		while i < len(lines) and not _RE_DOC_SECTION.match(lines[i]):
			section_lines.append(lines[i])
			i += 1

		if is_examples:
			# Ensure examples start on a clean boundary when appended.
			if examples and examples[-1].strip() != "":
				examples.append("")
			examples.extend(section_lines)
		else:
			main.extend(section_lines)

	main_text = "\n".join(main).strip() or None
	examples_text = "\n".join(examples).strip() or None
	return main_text, examples_text


def _preprocess_fortran_docstring(text: str) -> str:
	"""Normalize a lightweight docstring convention into valid reST.

	Supported patterns:
	- Section markers: "## References" -> ".. rubric:: References"
	- Example blocks: contiguous lines starting with ">>>" -> ".. code-block:: fortran"
	"""
	lines = (text or "").splitlines()
	out: list[str] = []
	i = 0
	while i < len(lines):
		line = lines[i]
		m = _RE_DOC_SECTION.match(line)
		if m:
			title = m.group("title")
			if out and out[-1].strip() != "":
				out.append("")
			out.append(f".. rubric:: {title}")
			out.append("")
			i += 1
			continue

		if line.lstrip().startswith(">>>"):
			block: list[str] = []
			while i < len(lines) and lines[i].lstrip().startswith(">>>"):
				s = lines[i].lstrip()[3:]
				block.append(s.lstrip(" \t"))
				i += 1

			if out and out[-1].strip() != "":
				out.append("")
			out.append(".. code-block:: fortran")
			out.append("")
			for b in block:
				out.append("   " + b)
			out.append("")
			continue
		
		stripped = line.lstrip()
		if stripped.startswith("```"):
			# Extract language if provided
			fence = stripped[3:].strip()   # after "```"
			language = fence if fence else "fortran"

			block: list[str] = []
			i += 1
			while i < len(lines):
				s = lines[i].lstrip()
				if s.startswith("```"):
					i += 1
					break
				block.append(s.rstrip("\t"))
				i += 1

			if out and out[-1].strip() != "":
				out.append("")
			out.append(f".. code-block:: {language}")
			out.append("")
			for b in block:
				out.append("   " + b)
			out.append("")
			continue

		out.append(line)
		i += 1

		# Make footnote/citation definitions robust in docstring fragments.
		# In reST, a footnote definition must be preceded by a blank line.
		# Many docstrings omit that blank line, which causes undefined refs like [1]_.
		# We insert it here for common `.. [n] ...` patterns.
		if _RE_FOOTNOTE_DEF.match(line):
			# If the previous non-empty line isn't blank, insert a blank line *before*
			# this definition. Because we've already appended the line, adjust in-place.
			if len(out) >= 2 and out[-2].strip() != "":
				out.insert(len(out) - 1, "")

	return "\n".join(out).rstrip()

def _make_object_id(objtype: str, fullname: str) -> str:
    # ``nodes.make_id`` produces a valid HTML id fragment.
    return nodes.make_id(f"f-{objtype}-{fullname}")


def _append_doc(section: nodes.Element, doc: str | None, state) -> None:
	if not doc:
		return

	text = _preprocess_fortran_docstring(str(doc))
	content = StringList(text.splitlines(), source="<fortran-doc>")
	container: nodes.Element = nodes.container()

	# Parse doc as a reST fragment so Sphinx roles/directives work (e.g. .. math::).
	for n in nested_parse_to_nodes(
		state,
		content,
		source="<fortran-doc>",
		offset=0,
		allow_section_headings=True,
		keep_title_context=True,
		):
		container += n

	section += container


def _read_program_source_from_location(location) -> str | None:
	"""Best-effort read of a program unit source from its file location."""
	if location is None:
		return None
	path = getattr(location, "path", None)
	lineno = getattr(location, "lineno", None)
	if not path or not lineno:
		return None
	try:
		with open(path, "r", encoding="utf-8", errors="replace") as f:
			lines = f.read().splitlines()
	except OSError:
		return None

	start = max(int(lineno) - 1, 0)
	buf: list[str] = []
	for i in range(start, len(lines)):
		buf.append(lines[i])
		if re.match(r"^\s*end\s*program\b", lines[i], flags=re.IGNORECASE):
			break
	return "\n".join(buf)

def _append_fortran_code_block(section: nodes.Element, *, source: str) -> None:
	text = (source or "").rstrip() + "\n"
	lit = nodes.literal_block(text, text)
	lit["language"] = "fortran"
	section += lit


def _append_program_dependencies(section: nodes.Element, *, dependencies, state) -> None:
	deps = [str(d).strip() for d in (dependencies or []) if str(d).strip()]
	if not deps:
		return
	items = nodes.bullet_list()
	for dep in deps:
		xref = addnodes.pending_xref(
			"",
			refdomain="f",
			reftype="module",
			reftarget=dep,
			refexplicit=True,
		)
		xref += nodes.literal(text=dep)
		items += nodes.list_item("", nodes.paragraph("", "", xref))

	section += nodes.subtitle(text="Dependencies")
	section += items


def _parse_doc_fragment(doc: str | None, state) -> list[nodes.Node]:
	if not doc:
		return []
	text = _preprocess_fortran_docstring(str(doc))
	content = StringList(text.splitlines(), source="<fortran-doc>")
	return list(
		nested_parse_to_nodes(
			state,
			content,
			source="<fortran-doc>",
			offset=0,
			allow_section_headings=True,
			keep_title_context=True,
		)
	)


def _field_list(title: str, body: nodes.Element) -> nodes.field_list:
	fl = nodes.field_list()
	field = nodes.field()
	field += nodes.field_name(text=title)
	fbody = nodes.field_body()
	fbody += body
	field += fbody
	fl += field
	return fl


def _stamp_source_line(node: nodes.Node, *, source: str = "<fortran>", line: int = 1) -> None:
	# Sphinx expects certain nodes (notably definition_list_item) to have
	# a non-None .line during HTML builds.
	if getattr(node, "source", None) is None:
		node.source = source  # type: ignore[attr-defined]
	if getattr(node, "line", None) is None:
		node.line = line  # type: ignore[attr-defined]


def _append_argument_docs(section: nodes.Element, args, state) -> None:
	if not args:
		return
	rows = []
	for a in args:
		name = getattr(a, "name", "")
		decl = getattr(a, "decl", None) or ""
		doc = getattr(a, "doc", None)
		if not name:
			continue
		rows.append((name, decl, doc))
	if not rows:
		return

	dl = nodes.definition_list()
	dl["classes"].append("simple")
	_stamp_source_line(dl)
	for name, decl, doc in rows:
		item = nodes.definition_list_item()
		_stamp_source_line(item)
		term = nodes.term()
		_stamp_source_line(term)
		term += nodes.strong(text=str(name))
		item += term
		if decl:
			classifier = nodes.classifier(text=str(decl))
			_stamp_source_line(classifier)
			item += classifier

		definition = nodes.definition()
		_stamp_source_line(definition)
		for n in _parse_doc_fragment(doc, state):
			definition += n
		item += definition
		dl += item

	section += _field_list("Arguments", dl)


def _append_return_docs(section: nodes.Element, result, state) -> None:
	if not result:
		return
	name = getattr(result, "name", "")
	decl = getattr(result, "decl", None) or ""
	doc = getattr(result, "doc", None)
	if not name:
		return

	dl = nodes.definition_list()
	dl["classes"].append("simple")
	_stamp_source_line(dl)

	item = nodes.definition_list_item()
	_stamp_source_line(item)
	term = nodes.term()
	_stamp_source_line(term)
	term += nodes.strong(text=str(name))
	item += term
	if decl:
		classifier = nodes.classifier(text=str(decl))
		_stamp_source_line(classifier)
		item += classifier

	definition = nodes.definition()
	_stamp_source_line(definition)
	for n in _parse_doc_fragment(doc, state):
		definition += n
	item += definition
	dl += item

	section += _field_list("Returns", dl)


def _append_component_docs(section: nodes.Element, components, state) -> None:
	if not components:
		return
	rows = []
	for c in components:
		name = getattr(c, "name", "")
		decl = getattr(c, "decl", None) or ""
		doc = getattr(c, "doc", None)
		if not name:
			continue
		rows.append((name, decl, doc))
	if not rows:
		return

	dl = nodes.definition_list()
	dl["classes"].append("simple")
	_stamp_source_line(dl)
	for name, decl, doc in rows:
		item = nodes.definition_list_item()
		_stamp_source_line(item)
		term = nodes.term()
		_stamp_source_line(term)
		term += nodes.strong(text=str(name))
		item += term
		if decl:
			classifier = nodes.classifier(text=str(decl))
			_stamp_source_line(classifier)
			item += classifier

		definition = nodes.definition()
		_stamp_source_line(definition)
		for n in _parse_doc_fragment(doc, state):
			definition += n
		item += definition
		dl += item

	section += _field_list("Attributes", dl)


def _find_proc_by_name(procedures, name: str):
	for p in procedures or []:
		if getattr(p, "name", None) == name:
			return p
	return None


def _append_type_bound_procedures(section: nodes.Element, bindings, all_procedures, state) -> None:
	if not bindings:
		return

	items = nodes.bullet_list()
	for b in bindings:
		bname = getattr(b, "name", "")
		target = getattr(b, "target", None) or bname
		if not bname:
			continue

		proc = _find_proc_by_name(all_procedures, target)
		kind = getattr(proc, "kind", None) if proc is not None else None

		para = nodes.paragraph()
		if proc is not None and kind in {"function", "subroutine"}:
			xref = addnodes.pending_xref(
				"",
				refdomain="f",
				reftype=str(kind),
				reftarget=str(target),
				refexplicit=True,
			)
			xref += nodes.literal(text=str(bname))
			para += xref
		else:
			para += nodes.literal(text=str(bname))

		item = nodes.list_item("", para)
		items += item

	section += _field_list("Procedures", items)


def _append_object_description(
	section: nodes.Element,
	*,
	domain: str,
	objtype: str,
	name: str,
	signature: str | None,
	doc: str | None,
	state,
	args=None,
	result=None,
	components=None,
	bindings=None,
	all_procedures=None,
) -> None:
	"""Render an object in a Sphinx-like <dl class="..."> wrapper.
	"""
	desc = addnodes.desc()
	desc["domain"] = domain
	desc["objtype"] = objtype
	desc["classes"].extend([domain, objtype])

	signode = addnodes.desc_signature()
	# Keep signature rendering simple and stable: show the parsed signature text
	# as a literal inside the signature node.
	text = signature if signature else f"{objtype} {name}"
	signode += nodes.literal(text=str(text))
	desc += signode

	content = addnodes.desc_content()
	main_doc, examples_doc = _split_out_examples_sections(doc)
	_append_doc(content, main_doc, state)
	_append_argument_docs(content, args, state)
	if objtype == "function":
		_append_return_docs(content, result, state)
	_append_component_docs(content, components, state)
	_append_type_bound_procedures(content, bindings, all_procedures, state)
	# Always put Examples at the end of the object documentation.
	_append_doc(content, examples_doc, state)
	desc += content

	section += desc

class FortranObject(ObjectDescription[str]):
    """Base directive for Fortran objects (manual declarations)."""

    has_content = True
    required_arguments = 1

    def handle_signature(self, sig: str, signode: addnodes.desc_signature) -> str:
        fullname = sig.strip()
        signode += addnodes.desc_name(fullname, fullname)
        return fullname

    def add_target_and_index(self, name: str, sig: str, signode: addnodes.desc_signature) -> None:
        domain: FortranDomain = self.env.get_domain("f")  # type: ignore[assignment]
        objtype = self.objtype
        anchor = _make_object_id(objtype, name)

        if anchor not in signode["ids"]:
            signode["ids"].append(anchor)

        domain.note_object(name=name, objtype=objtype, anchor=anchor)

        index_text = f"{name} ({objtype})"
        self.indexnode["entries"].append(("single", index_text, anchor, "", None))


class FortranProgramDecl(FortranObject):
	objtype = "program"

class FortranFunction(FortranObject):
	objtype = "function"


class FortranSubroutine(FortranObject):
	objtype = "subroutine"


class FortranType(FortranObject):
	objtype = "type"


class FortranInterface(FortranObject):
	objtype = "interface"


class FortranProgram(Directive):
	required_arguments = 1
	option_spec = {
		"procedures": rst_directives.flag,
		"no-procedures": rst_directives.flag,
	}

	def run(self):
		progname = self.arguments[0]
		env = self.state.document.settings.env
		domain = env.get_domain("f")
		program = getattr(domain, "get_program")(progname)

		show_procedures = True
		if "no-procedures" in self.options:
			show_procedures = False
		if "procedures" in self.options:
			show_procedures = True

		anchor = nodes.make_id(f"f-program-{progname}")
		index = addnodes.index(entries=[("single", f"{progname} (program)", anchor, "", None)])
		section = nodes.section(ids=[anchor])
		section += nodes.title(text=f"Program {progname}")
		getattr(domain, "note_object")(name=progname, objtype="program", anchor=anchor)

		if program is None:
			return [index, nodes.warning(text=f"Fortran program '{progname}' not found (did you configure fortran_sources?)")]

		markers = _doc_markers_from_env(env)
		src = getattr(program, "source", None) or _read_program_source_from_location(getattr(program, "location", None))
		predoc: str | None = None
		if not src:
			src, predoc = _read_program_source_by_search(env, progname, doc_markers=markers)
		else:
			# If we have a usable file location, try to re-read to extract only the doc
			# block immediately preceding the program statement (important for FORD,
			# which may include in-body docs in program.doc).
			loc = getattr(program, "location", None)
			path = getattr(loc, "path", None) if loc is not None else None
			lineno = getattr(loc, "lineno", None) if loc is not None else None
			if path and lineno:
				try:
					lines = Path(str(path)).read_text(encoding="utf-8", errors="replace").splitlines()
					start = _find_program_in_file(lines, progname, start_at=max(int(lineno) - 1 - 5, 0))
					if start is not None:
						predoc = _extract_predoc_before_line(lines, start, doc_markers=markers)
				except OSError:
					pass

		# Render program-level docs right under the title.
		# Prefer only the pre-program doc block when available (prevents in-body docs
		# from being rendered separately, which is especially important for FORD).
		doc = predoc if predoc is not None else getattr(program, "doc", None)
		_append_doc(section, doc, self.state)

		if src:
			_append_fortran_code_block(section, source=src)

		deps = list(getattr(program, "dependencies", None) or [])
		if not deps and src:
			deps = _extract_use_dependencies_from_source(src)
		_append_program_dependencies(section, dependencies=deps, state=self.state)

		# Internal procedures (after `contains`) are optionally rendered after the program source.
		if show_procedures and getattr(program, "procedures", None):
			section += nodes.subtitle(text="Procedures")
			for p in program.procedures:
				kind = getattr(p, "kind", "procedure")
				fullname = f"{progname}.{p.name}"
				obj_anchor = _make_object_id(kind, fullname)
				getattr(domain, "note_object")(name=p.name, objtype=kind, anchor=obj_anchor)
				index["entries"].append(("single", f"{p.name} ({kind})", obj_anchor, "", None))

				sub = nodes.section(ids=[obj_anchor])
				sub += nodes.title(text=f"{kind.capitalize()} {p.name}")
				_append_object_description(
					sub,
					domain="f",
					objtype=str(kind),
					name=str(p.name),
					signature=getattr(p, "signature", None),
					doc=getattr(p, "doc", None),
					state=self.state,
					args=getattr(p, "arguments", None),
					result=getattr(p, "result", None),
				)
				section += sub

		return [index, section]


class FortranModule(Directive):
	required_arguments = 1

	def run(self):
		modname = self.arguments[0]
		env = self.state.document.settings.env
		domain = env.get_domain("f")
		module = getattr(domain, "get_module")(modname)

		anchor = nodes.make_id(f"f-module-{modname}")
		index = addnodes.index(entries=[("single", f"{modname} (module)", anchor, "", None)])
		section = nodes.section(ids=[anchor])
		section += nodes.title(text=f"Module {modname}")
		getattr(domain, "note_object")(name=modname, objtype="module", anchor=anchor)

		if module is None:
			return [index, nodes.warning(text=f"Fortran module '{modname}' not found (did you configure fortran_sources?)")]

		_append_doc(section, getattr(module, "doc", None), self.state)

		if getattr(module, "types", None):
			section += nodes.subtitle(text="Types")
			for t in module.types:
				fullname = f"{modname}.{t.name}"
				obj_anchor = _make_object_id("type", fullname)
				getattr(domain, "note_object")(name=t.name, objtype="type", anchor=obj_anchor)
				index["entries"].append(("single", f"{t.name} (type)", obj_anchor, "", None))

				sub = nodes.section(ids=[obj_anchor])
				sub += nodes.title(text=f"Type {t.name}")
				_append_object_description(
					sub,
					domain="f",
					objtype="type",
					name=str(t.name),
					signature=getattr(t, "signature", None),
					doc=getattr(t, "doc", None),
					state=self.state,
					components=getattr(t, "components", None),
					bindings=getattr(t, "bound_procedures", None),
					all_procedures=getattr(module, "procedures", None),
				)
				section += sub

		if getattr(module, "procedures", None):
			section += nodes.subtitle(text="Procedures")
			for p in module.procedures:
				kind = getattr(p, "kind", "procedure")
				fullname = f"{modname}.{p.name}"
				obj_anchor = _make_object_id(kind, fullname)
				getattr(domain, "note_object")(name=p.name, objtype=kind, anchor=obj_anchor)
				index["entries"].append(("single", f"{p.name} ({kind})", obj_anchor, "", None))

				sub = nodes.section(ids=[obj_anchor])
				sub += nodes.title(text=f"{kind.capitalize()} {p.name}")
				_append_object_description(
					sub,
					domain="f",
					objtype=str(kind),
					name=str(p.name),
					signature=getattr(p, "signature", None),
					doc=getattr(p, "doc", None),
					state=self.state,
					args=getattr(p, "arguments", None),
					result=getattr(p, "result", None),
				)
				section += sub

		if getattr(module, "interfaces", None):
			section += nodes.subtitle(text="Interfaces")
			for g in module.interfaces:
				fullname = f"{modname}.{g.name}"
				obj_anchor = _make_object_id("interface", fullname)
				getattr(domain, "note_object")(name=g.name, objtype="interface", anchor=obj_anchor)
				index["entries"].append(("single", f"{g.name} (interface)", obj_anchor, "", None))

				sub = nodes.section(ids=[obj_anchor])
				sub += nodes.title(text=f"Interface {g.name}")
				_append_doc(sub, getattr(g, "doc", None), self.state)
				section += sub

		return [index, section]

class FortranSubmodule(Directive):
	required_arguments = 1

	def run(self):
		submodname = self.arguments[0]
		env = self.state.document.settings.env
		domain = env.get_domain("f")
		submodule = getattr(domain, "get_submodule")(submodname)

		anchor = nodes.make_id(f"f-submodule-{submodname}")
		index = addnodes.index(entries=[("single", f"{submodname} (submodule)", anchor, "", None)])
		section = nodes.section(ids=[anchor])
		section += nodes.title(text=f"Submodule {submodname}")
		getattr(domain, "note_object")(name=submodname, objtype="submodule", anchor=anchor)

		if submodule is None:
			return [index, nodes.warning(text=f"Fortran submodule '{submodname}' not found (did you configure fortran_sources?)")]

		_append_doc(section, getattr(submodule, "doc", None), self.state)

		if getattr(submodule, "types", None):
			section += nodes.subtitle(text="Types")
			for t in submodule.types:
				fullname = f"{submodname}.{t.name}"
				obj_anchor = _make_object_id("type", fullname)
				getattr(domain, "note_object")(name=t.name, objtype="type", anchor=obj_anchor)
				index["entries"].append(("single", f"{t.name} (type)", obj_anchor, "", None))

				sub = nodes.section(ids=[obj_anchor])
				sub += nodes.title(text=f"Type {t.name}")
				_append_object_description(
					sub,
					domain="f",
					objtype="type",
					name=str(t.name),
					signature=getattr(t, "signature", None),
					doc=getattr(t, "doc", None),
					state=self.state,
					components=getattr(t, "components", None),
					bindings=getattr(t, "bound_procedures", None),
					all_procedures=getattr(submodule, "procedures", None),
				)
				section += sub

		if getattr(submodule, "procedures", None):
			section += nodes.subtitle(text="Procedures")
			for p in submodule.procedures:
				kind = getattr(p, "kind", "procedure")
				fullname = f"{submodname}.{p.name}"
				obj_anchor = _make_object_id(kind, fullname)
				getattr(domain, "note_object")(name=p.name, objtype=kind, anchor=obj_anchor)
				index["entries"].append(("single", f"{p.name} ({kind})", obj_anchor, "", None))

				sub = nodes.section(ids=[obj_anchor])
				sub += nodes.title(text=f"{kind.capitalize()} {p.name}")
				_append_object_description(
					sub,
					domain="f",
					objtype=str(kind),
					name=str(p.name),
					signature=getattr(p, "signature", None),
					doc=getattr(p, "doc", None),
					state=self.state,
					args=getattr(p, "arguments", None),
					result=getattr(p, "result", None),
				)
				section += sub

		if getattr(submodule, "interfaces", None):
			section += nodes.subtitle(text="Interfaces")
			for g in submodule.interfaces:
				fullname = f"{submodname}.{g.name}"
				obj_anchor = _make_object_id("interface", fullname)
				getattr(domain, "note_object")(name=g.name, objtype="interface", anchor=obj_anchor)
				index["entries"].append(("single", f"{g.name} (interface)", obj_anchor, "", None))

				sub = nodes.section(ids=[obj_anchor])
				sub += nodes.title(text=f"Interface {g.name}")
				_append_doc(sub, getattr(g, "doc", None), self.state)
				section += sub

		return [index, section]