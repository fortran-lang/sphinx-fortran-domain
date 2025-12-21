from __future__ import annotations

import re

from docutils import nodes
from docutils.parsers.rst import Directive
from docutils.statemachine import ViewList
from sphinx import addnodes
from sphinx.directives import ObjectDescription
from sphinx.util.nodes import nested_parse_with_titles


def _split_sig_name(sig: str) -> str:
	# small helper: "foo(a,b)" -> "foo"
	head = sig.strip()
	if "(" in head:
		head = head.split("(", 1)[0]
	return head.strip()

def _make_object_id(objtype: str, fullname: str) -> str:
    # ``nodes.make_id`` produces a valid HTML id fragment.
    return nodes.make_id(f"f-{objtype}-{fullname}")


def _append_doc(section: nodes.Element, doc: str | None, state) -> None:
	if not doc:
		return

	text = str(doc)
	view = ViewList()
	for i, line in enumerate(text.splitlines()):
		view.append(line, "<fortran-doc>", i + 1)

	# Parse doc as a reST fragment so Sphinx roles/directives work (e.g. .. math::).
	nested_parse_with_titles(state, view, section)


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

	section += nodes.subtitle(text="Arguments")
	for name, decl, doc in rows:
		line = nodes.paragraph()
		line += nodes.strong(text=f"{name}:")
		if decl:
			line += nodes.Text(" ")
			line += nodes.literal(text=str(decl))
		section += line
		if doc:
			_append_doc(section, str(doc), state)


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

	section += nodes.subtitle(text="Members")
	for name, decl, doc in rows:
		line = nodes.paragraph()
		line += nodes.strong(text=f"{name}:")
		if decl:
			line += nodes.Text(" ")
			line += nodes.literal(text=str(decl))
		section += line
		if doc:
			_append_doc(section, str(doc), state)


def _find_proc_by_name(procedures, name: str):
	for p in procedures or []:
		if getattr(p, "name", None) == name:
			return p
	return None


def _append_type_bound_procedures(section: nodes.Element, bindings, all_procedures, state) -> None:
	if not bindings:
		return

	section += nodes.subtitle(text="Procedures")
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

	section += items

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
				_append_doc(sub, getattr(t, "doc", None), self.state)
				_append_component_docs(sub, getattr(t, "components", None), self.state)
				_append_type_bound_procedures(sub, getattr(t, "bound_procedures", None), getattr(module, "procedures", None), self.state)
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
				sig = getattr(p, "signature", None)
				if sig:
					sub += nodes.literal_block(text=str(sig))
				_append_doc(sub, getattr(p, "doc", None), self.state)
				_append_argument_docs(sub, getattr(p, "arguments", None), self.state)
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
				_append_doc(sub, getattr(t, "doc", None), self.state)
				_append_component_docs(sub, getattr(t, "components", None), self.state)
				_append_type_bound_procedures(sub, getattr(t, "bound_procedures", None), getattr(submodule, "procedures", None), self.state)
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
				sig = getattr(p, "signature", None)
				if sig:
					sub += nodes.literal_block(text=str(sig))
				_append_doc(sub, getattr(p, "doc", None), self.state)
				_append_argument_docs(sub, getattr(p, "arguments", None), self.state)
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