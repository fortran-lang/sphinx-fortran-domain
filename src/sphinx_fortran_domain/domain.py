from __future__ import annotations

from dataclasses import dataclass
from docutils import nodes
from sphinx import addnodes
from sphinx.domains import Domain, ObjType
from sphinx.roles import XRefRole
from sphinx.util.nodes import make_refnode

from sphinx_fortran_domain.directives import (
    FortranProgram,
    FortranModule,
    FortranSubmodule,
    FortranFunction,
    FortranSubroutine,
    FortranInterface,
    FortranType,
)

from typing import Dict, Iterable, Iterator, Optional, Tuple

from sphinx_fortran_domain.lexers import FortranModuleInfo, FortranParseResult, FortranSubmoduleInfo, FortranProgramInfo

@dataclass(frozen=True)
class FortranObjectEntry:
    docname: str
    anchor: str
    objtype: str

class FortranDomain(Domain):
    """Sphinx domain for Fortran entities."""

    name = "f"
    label = "Fortran"

    object_types = {
        "module": ObjType("module", "module", "mod"),
        "submodule": ObjType("submodule", "submodule", "submod"),
        "variable": ObjType("variable", "variable", "var"),
        "function": ObjType("function", "function", "func"),
        "subroutine": ObjType("subroutine", "subroutine", "subr"),
        "type": ObjType("type", "type"),
        "interface": ObjType("interface", "interface", "iface"),
        "program": ObjType("program", "program", "prog"),
    }

    directives = {
        "program": FortranProgram,
        "module": FortranModule,
        "submodule": FortranSubmodule,
        "function": FortranFunction,
        "subroutine": FortranSubroutine,
        "type": FortranType,
        "interface": FortranInterface,
    }

    roles = {
        "program": XRefRole(),
        "prog": XRefRole(),
        "module": XRefRole(),
        "mod": XRefRole(),
        "submodule": XRefRole(),
        "submod": XRefRole(),
        "variable": XRefRole(),
        "var": XRefRole(),
        "function": XRefRole(),
        "func": XRefRole(),
        "subroutine": XRefRole(),
        "subr": XRefRole(),
        "type": XRefRole(),
        "interface": XRefRole(),
        "iface": XRefRole(),
    }

    initial_data: Dict[str, Dict] = {
        "objects": {},  # objtype -> name -> FortranObjectEntry
        "symbols": {"modules": {}, "submodules": {}, "programs": {}},
    }

    def set_parse_result(self, result: FortranParseResult) -> None:
        self.data.setdefault("symbols", {})
        self.data["symbols"] = {
            "modules": dict(result.modules),
            "submodules": dict(result.submodules),
            "programs": dict(result.programs),
        }

    def get_module(self, name: str) -> Optional[FortranModuleInfo]:
        symbols = self.data.get("symbols", {})
        return symbols.get("modules", {}).get(name)

    def get_submodule(self, name: str) -> Optional[FortranSubmoduleInfo]:
        symbols = self.data.get("symbols", {})
        return symbols.get("submodules", {}).get(name)

    def get_program(self, name: str) -> Optional[FortranProgramInfo]:
        symbols = self.data.get("symbols", {})
        return symbols.get("programs", {}).get(name)

    _role_to_objtype = {
        "program": "program",
        "prog": "program",
        "module": "module",
        "mod": "module",
        "submodule": "submodule",
        "submod": "submodule",
        "variable": "variable",
        "var": "variable",
        "function": "function",
        "func": "function",
        "subroutine": "subroutine",
        "subr": "subroutine",
        "type": "type",
        "interface": "interface",
        "iface": "interface",
    }

    def note_object(self, name: str, objtype: str, anchor: str) -> None:
        self.data.setdefault("objects", {})
        objects_by_type: Dict[str, Dict[str, FortranObjectEntry]] = self.data["objects"]
        objects_by_type.setdefault(objtype, {})

        objects_by_type[objtype][name] = FortranObjectEntry(
            docname=self.env.docname,
            anchor=anchor,
            objtype=objtype,
        )

    def clear_doc(self, docname: str) -> None:
        objects_by_type: Dict[str, Dict[str, FortranObjectEntry]] = self.data.get("objects", {})
        for objtype, objects in list(objects_by_type.items()):
            to_delete = [name for name, entry in objects.items() if entry.docname == docname]
            for name in to_delete:
                del objects[name]
            if not objects:
                del objects_by_type[objtype]

    def resolve_xref(
        self,
        env,
        fromdocname: str,
        builder,
        typ: str,
        target: str,
        node: addnodes.pending_xref,
        contnode: nodes.Element,
    ) -> Optional[nodes.Element]:
        """Resolve cross-reference for a Fortran object."""
        objects_by_type: Dict[str, Dict[str, FortranObjectEntry]] = self.data.get("objects", {})
        objtype = self._role_to_objtype.get(typ)
        if not objtype:
            return None

        entry = objects_by_type.get(objtype, {}).get(target)
        if entry is None:
            return None

        return make_refnode(
            builder=builder,
            fromdocname=fromdocname,
            todocname=entry.docname,
            targetid=entry.anchor,
            child=contnode,
            title=target,
        )

    def get_objects(self) -> Iterator[Tuple[str, str, str, str, str, int]]:
        objects_by_type: Dict[str, Dict[str, FortranObjectEntry]] = self.data.get("objects", {})
        for objtype, objects in objects_by_type.items():
            for name, entry in objects.items():
                # (name, dispname, type, docname, anchor, priority)
                yield (name, name, objtype, entry.docname, entry.anchor, 1)

    def merge_domaindata(self, docnames: Iterable[str], otherdata: Dict) -> None:
        objects_by_type: Dict[str, Dict[str, FortranObjectEntry]] = self.data.setdefault("objects", {})
        other_objects_by_type: Dict[str, Dict[str, FortranObjectEntry]] = otherdata.get("objects", {})

        for objtype, other_objects in other_objects_by_type.items():
            objects_by_type.setdefault(objtype, {})
            for name, entry in other_objects.items():
                if entry.docname in docnames:
                    objects_by_type[objtype][name] = entry

            # Symbols are global (source-based) and are re-parsed on each build.
