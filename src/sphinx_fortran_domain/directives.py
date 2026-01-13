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

from sphinx_fortran_domain.utils import (
	collect_fortran_source_files_from_config,
	doc_markers_from_doc_chars,
	extract_predoc_before_line,
	extract_use_dependencies,
	read_lines_utf8,
	read_text_utf8,
)


_RE_DOC_SECTION = re.compile(r"^\s*##\s+(?P<title>\S.*?\S)\s*$")
_RE_FOOTNOTE_DEF = re.compile(r"^\s*\.\.\s*\[(?P<label>\d+|#)\]\s+")
_RE_END_PROGRAM = re.compile(r"^\s*end\s*program\b", re.IGNORECASE)


def _doc_markers_from_env(env) -> list[str]:
	"""Return configured Fortran doc markers (e.g. ['!>'])."""
	app = getattr(env, "app", None)
	config = getattr(app, "config", None) if app is not None else None
	try:
		return doc_markers_from_doc_chars(getattr(config, "fortran_doc_chars", None))
	except Exception:
		# Keep directives resilient even if config is malformed.
		return ["!>"]


def _collect_fortran_files_from_env(env) -> list[str]:
	app = getattr(env, "app", None)
	if app is None:
		return []
	confdir = Path(getattr(app, "confdir", os.getcwd()))
	config = getattr(app, "config", None)
	return collect_fortran_source_files_from_config(confdir=confdir, config=config)


def _find_program_in_file(lines: list[str], progname: str, *, start_at: int = 0) -> int | None:
	pat = re.compile(rf"^\s*program\s+{re.escape(str(progname))}\b", re.IGNORECASE)
	for i in range(max(start_at, 0), len(lines)):
		if pat.match(lines[i]):
			return i
	return None


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
			text = read_text_utf8(path)
		except OSError:
			continue
		lines = text.splitlines()
		start = _find_program_in_file(lines, progname)
		if start is None:
			continue

		predoc = extract_predoc_before_line(lines, start, doc_markers=doc_markers)
		buf: list[str] = []
		for i in range(start, len(lines)):
			buf.append(lines[i])
			if _RE_END_PROGRAM.match(lines[i]):
				break
		return ("\n".join(buf), predoc)

	return (None, None)


def _split_out_doc_section_blocks(text: str | None) -> tuple[str | None, str | None]:
	"""Split a docstring into (preamble, sections) based on our "## Title" markers.

	- preamble: everything before the first "##" section marker
	- sections: from the first "##" marker to the end

	This is used to control placement: the preamble stays near the top of object
	documentation, while section blocks (Notes/References/See Also/...) can be
	placed after intrinsic blocks (Arguments/Returns/Attributes/Procedures).
	"""
	if not text:
		return None, None

	lines = str(text).splitlines()
	first = None
	for i, line in enumerate(lines):
		if _RE_DOC_SECTION.match(line):
			first = i
			break

	if first is None:
		preamble = "\n".join(lines).strip() or None
		return preamble, None

	preamble = "\n".join(lines[:first]).strip() or None
	sections = "\n".join(lines[first:]).strip() or None
	return preamble, sections


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
			normalized = (title or "").strip().lower()

			# Match NumpyDoc-style rendering for "See Also" by emitting a real
			# Sphinx seealso directive (renders as an admonition with special styling).
			if normalized in {"see also", "seealso"}:
				if out and out[-1].strip() != "":
					out.append("")
				out.append(".. seealso::")
				out.append("")
				i += 1

				# Consume the See Also body until the next "##" section marker.
				# Support a lightweight "term : description" syntax (with spaces
				# around the colon) to produce a definition-list style layout.
				while i < len(lines) and not _RE_DOC_SECTION.match(lines[i]):
					body_line = lines[i]
					if not body_line.strip():
						out.append("")
						i += 1
						continue

					# Split only on " : " (spaces required) so domain roles like
					# ":f:func:`name`" are not misinterpreted.
					parts = re.split(r"\s+:\s+", body_line.strip(), maxsplit=1)
					if len(parts) == 2:
						term, desc = parts
						out.append("   " + term.strip())
						out.append("      " + desc.strip())
						out.append("")
					else:
						out.append("   " + body_line.strip())
						i += 1
						continue
					i += 1

				# Avoid accumulating extra blank lines at the end of the directive.
				while out and out[-1] == "":
					out.pop()
				out.append("")
				continue

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
		lines = read_lines_utf8(path)
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

def _append_named_decl_docs(
	section: nodes.Element,
	title: str,
	items,
	state,
	*,
	anchors_by_name: dict[str, str] | None = None,
	as_field_list: bool = True,
) -> None:
	"""Render a standard name/decl/doc definition list inside a field list.

	This is the canonical rendering used for procedure Arguments and module Variables.
	"""
	if not items:
		return
	rows = []
	for a in items:
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
		anchor = (anchors_by_name or {}).get(str(name))
		if anchor:
			# Add an invisible target so xrefs land on the correct row without
			# changing the visual rendering.
			term += nodes.target(ids=[anchor])
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

	if as_field_list:
		section += _field_list(title, dl)
	else:
		section += nodes.subtitle(text=str(title))
		section += dl


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
	text = signature if signature else f"{name} ({objtype})"
	signode += nodes.literal(text=str(text))
	desc += signode

	content = addnodes.desc_content()
	preamble_doc, section_blocks_doc = _split_out_doc_section_blocks(doc)
	# Keep the opening free-text docstring at the top.
	_append_doc(content, preamble_doc, state)
	_append_named_decl_docs(content, "Arguments", args, state)
	if objtype == "function":
		_append_return_docs(content, result, state)
	_append_component_docs(content, components, state)
	_append_type_bound_procedures(content, bindings, all_procedures, state)
	# Place all "## ..." section blocks (including "## Examples") after intrinsic blocks.
	_append_doc(content, section_blocks_doc, state)
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
		"no-show-code": rst_directives.flag,
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
		section += nodes.title(text=f"{progname} (program)")
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
						predoc = extract_predoc_before_line(lines, start, doc_markers=markers)
				except OSError:
					pass

		# Render program-level docs right under the title.
		# Prefer only the pre-program doc block when available (prevents in-body docs
		# from being rendered separately, which is especially important for FORD).
		doc = predoc if predoc is not None else getattr(program, "doc", None)
		_append_doc(section, doc, self.state)

		show_source_code = "no-show-code" not in self.options
		if src and show_source_code:
			_append_fortran_code_block(section, source=src)

		deps = list(getattr(program, "dependencies", None) or [])
		if not deps and src:
			deps = extract_use_dependencies(src)
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
				sub += nodes.title(text=f"{p.name} ({kind})")
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
		section += nodes.title(text=f"{modname} (module)")
		getattr(domain, "note_object")(name=modname, objtype="module", anchor=anchor)

		if module is None:
			return [index, nodes.warning(text=f"Fortran module '{modname}' not found (did you configure fortran_sources?)")]

		_append_doc(section, getattr(module, "doc", None), self.state)

		if getattr(module, "variables", None):
			anchors: dict[str, str] = {}
			for v in module.variables:
				name = getattr(v, "name", "")
				if not name:
					continue
				fullname = f"{modname}.{name}"
				obj_anchor = _make_object_id("variable", fullname)
				anchors[str(name)] = obj_anchor
				getattr(domain, "note_object")(name=name, objtype="variable", anchor=obj_anchor)
				index["entries"].append(("single", f"{name} (variable)", obj_anchor, "", None))
			_append_named_decl_docs(
				section,
				"Variables",
				module.variables,
				self.state,
				anchors_by_name=anchors,
				as_field_list=False,
			)

		if getattr(module, "types", None):
			section += nodes.subtitle(text="Types")
			for t in module.types:
				fullname = f"{modname}.{t.name}"
				obj_anchor = _make_object_id("type", fullname)
				getattr(domain, "note_object")(name=t.name, objtype="type", anchor=obj_anchor)
				index["entries"].append(("single", f"{t.name} (type)", obj_anchor, "", None))

				sub = nodes.section(ids=[obj_anchor])
				sub += nodes.title(text=f"{t.name} (type)")
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
				sub += nodes.title(text=f"{p.name} ({kind})")
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
				sub += nodes.title(text=f"{g.name} (interface)")
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
		section += nodes.title(text=f"{submodname} (submodule)")
		getattr(domain, "note_object")(name=submodname, objtype="submodule", anchor=anchor)

		if submodule is None:
			return [index, nodes.warning(text=f"Fortran submodule '{submodname}' not found (did you configure fortran_sources?)")]

		_append_doc(section, getattr(submodule, "doc", None), self.state)

		if getattr(submodule, "variables", None):
			anchors: dict[str, str] = {}
			for v in submodule.variables:
				name = getattr(v, "name", "")
				if not name:
					continue
				fullname = f"{submodname}.{name}"
				obj_anchor = _make_object_id("variable", fullname)
				anchors[str(name)] = obj_anchor
				getattr(domain, "note_object")(name=name, objtype="variable", anchor=obj_anchor)
				index["entries"].append(("single", f"{name} (variable)", obj_anchor, "", None))
			_append_named_decl_docs(
				section,
				"Variables",
				submodule.variables,
				self.state,
				anchors_by_name=anchors,
				as_field_list=False,
			)

		if getattr(submodule, "types", None):
			section += nodes.subtitle(text="Types")
			for t in submodule.types:
				fullname = f"{submodname}.{t.name}"
				obj_anchor = _make_object_id("type", fullname)
				getattr(domain, "note_object")(name=t.name, objtype="type", anchor=obj_anchor)
				index["entries"].append(("single", f"{t.name} (type)", obj_anchor, "", None))

				sub = nodes.section(ids=[obj_anchor])
				sub += nodes.title(text=f"{t.name} (type)")
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
				sub += nodes.title(text=f"{p.name} ({kind})")
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
				sub += nodes.title(text=f"{g.name} (interface)")
				_append_doc(sub, getattr(g, "doc", None), self.state)
				section += sub

		return [index, section]