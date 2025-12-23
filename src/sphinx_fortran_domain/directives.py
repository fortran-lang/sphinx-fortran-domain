from __future__ import annotations

import re

from docutils import nodes
from docutils.parsers.rst import Directive
from docutils.statemachine import StringList
from sphinx import addnodes
from sphinx.directives import ObjectDescription
from sphinx.util.parsing import nested_parse_to_nodes


_RE_DOC_SECTION = re.compile(r"^\s*##\s+(?P<title>\S.*?\S)\s*$")
_RE_FOOTNOTE_DEF = re.compile(r"^\s*\.\.\s*\[(?P<label>\d+|#)\]\s+")


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

	section += _field_list("Members", dl)


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

	def run(self):
		progname = self.arguments[0]
		env = self.state.document.settings.env
		domain = env.get_domain("f")
		program = getattr(domain, "get_program")(progname)

		anchor = nodes.make_id(f"f-program-{progname}")
		index = addnodes.index(entries=[("single", f"{progname} (program)", anchor, "", None)])
		section = nodes.section(ids=[anchor])
		section += nodes.title(text=f"Program {progname}")
		getattr(domain, "note_object")(name=progname, objtype="program", anchor=anchor)

		if program is None:
			return [index, nodes.warning(text=f"Fortran program '{progname}' not found (did you configure fortran_sources?)")]

		_append_doc(section, getattr(program, "doc", None), self.state)

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