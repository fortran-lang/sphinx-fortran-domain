from __future__ import annotations

from pathlib import Path
import os
import tempfile
from typing import Dict, List, Optional, Sequence

from sphinx_fortran_domain.lexers import (
    FortranArgument,
    FortranInterface,
    FortranLexer,
    FortranModuleInfo,
    FortranParseResult,
    FortranProcedure,
    FortranProgramInfo,
    FortranSubmoduleInfo,
    FortranType,
    SourceLocation,
)


try:
    from ford.fortran_project import FortranSourceFile, ProjectSettings
    from ford.sourceform import (
        FortranBase as FordBase,
        FortranFunction as FordFunction,
        FortranInterface as FordInterface,
        FortranModule as FordModule,
        FortranProgram as FordProgram,
        FortranSubmodule as FordSubmodule,
        FortranSubroutine as FordSubroutine,
        FortranType as FordType,
    )

    FORD_AVAILABLE = True
except Exception:
    # Any failure to import FORD should keep this lexer unavailable.
    FORD_AVAILABLE = False


def _common_parent_dir(file_paths: Sequence[str]) -> Path:
    if not file_paths:
        return Path.cwd()
    try:
        common = os.path.commonpath([str(Path(p).resolve()) for p in file_paths])
        return Path(common).parent if Path(common).is_file() else Path(common)
    except Exception:
        return Path.cwd()


def _get_doc(item: object) -> Optional[str]:
    doc_list = getattr(item, "doc_list", None)
    if not doc_list:
        return None
    # FORD typically stores doc_list as a list of already-stripped strings.
    parts: List[str] = []
    for line in doc_list:
        if line is None:
            continue
        s = str(line)
        parts.append(s)
    doc = "\n".join(parts).strip()
    return doc or None


def _get_location(item: object) -> Optional[SourceLocation]:
    # Best-effort: FORD objects vary in what they expose.
    path = getattr(item, "filename", None) or getattr(item, "filepath", None) or getattr(item, "file", None)
    lineno = getattr(item, "line_number", None) or getattr(item, "lineno", None)
    if not path or not lineno:
        return None
    try:
        return SourceLocation(path=str(path), lineno=int(lineno))
    except Exception:
        return None


def _arg_decl_from_ford(arg: object) -> Optional[str]:
    # Try common FORD attributes.
    base: Optional[str] = None
    for attr in ("full_declaration", "declaration", "full_type", "type"):
        val = getattr(arg, attr, None)
        if not val:
            continue
        s = str(val).strip()
        if not s:
            continue
        if "::" in s:
            s = s.split("::", 1)[0].strip()
        base = s or None
        break

    # Some builds expose a coarse vartype and a separate "proto" type.
    if base is None:
        vt = getattr(arg, "vartype", None)
        if vt:
            base = str(vt).strip() or None

    attrs: List[str] = []

    intent = getattr(arg, "intent", None)
    if intent:
        attrs.append(f"intent({str(intent).strip()})")

    if getattr(arg, "optional", False):
        attrs.append("optional")

    if getattr(arg, "parameter", False):
        attrs.append("parameter")

    # Best-effort for common Fortran attributes.
    for flag in ("allocatable", "pointer", "target", "contiguous", "save"):
        if getattr(arg, flag, False):
            attrs.append(flag)

    dim = getattr(arg, "dimension", None)
    if dim:
        s = str(dim).strip()
        if s:
            attrs.append(f"dimension({s.strip('()')})")

    if base is None:
        return ", ".join(attrs) if attrs else None

    # Avoid duplicating attributes that are already in the base string.
    low = base.lower()
    deduped = [a for a in attrs if a.lower() not in low]
    if deduped:
        return f"{base}, {', '.join(deduped)}"
    return base


def _proc_signature_from_ford(proc: object) -> Optional[str]:
    # Try to build a readable signature.
    name = getattr(proc, "name", None)
    if not name:
        return None
    attribs = getattr(proc, "attribs", None) or getattr(proc, "attributes", None) or []
    if isinstance(attribs, str):
        attrib_list = [attribs]
    else:
        attrib_list = [str(a) for a in attribs if a]
    prefix = " ".join(attrib_list)
    args = [str(getattr(a, "name", "")).strip() for a in (getattr(proc, "args", None) or [])]
    args = [a for a in args if a]

    kind = "function" if isinstance(proc, FordFunction) else "subroutine" if isinstance(proc, FordSubroutine) else "procedure"
    sig = f"{kind} {name}"
    if args:
        sig += "(" + ", ".join(args) + ")"

    # Add result variable if present.
    ret = getattr(proc, "retvar", None) or getattr(proc, "result", None)
    rname = getattr(ret, "name", None) if ret is not None else None
    if kind == "function" and rname:
        sig += f" -> {rname}"

    if prefix:
        sig = f"{prefix} {sig}".strip()
    return sig


def _prepare_text_for_ford(text: str, configured_markers: Sequence[str], *, ford_marker: str) -> str:
    """Prepare source for FORD.

    - FORD doc markers must be 2 characters and must not use the same character
      for docmark/predocmark.
    - FORD also errors if doc markers appear inline (after code).

    Strategy:
    - Rewrite any *leading* configured doc marker to a single FORD-compatible marker.
    - For *inline* occurrences (code ... !> doc), split into:
        1) a doc-only line (so FORD can attach it)
        2) the original code line without the inline doc part
    """

    markers = [m for m in (configured_markers or []) if m and len(m) == 2 and m[0] == "!"]
    if not markers:
        markers = [ford_marker]

    out: List[str] = []
    for line in text.splitlines():
        stripped = line.lstrip()
        indent_len = len(line) - len(stripped)
        indent = line[:indent_len]

        replaced_leading = False
        for m in markers:
            if stripped.startswith(m):
                out.append(indent + ford_marker + stripped[len(m) :])
                replaced_leading = True
                break
        if replaced_leading:
            continue

        # Split inline occurrence (after code)
        split_at: Optional[tuple[int, str]] = None
        for m in markers:
            pos = line.find(m)
            if pos != -1 and line[:pos].strip() != "":
                # Choose the earliest match.
                if split_at is None or pos < split_at[0]:
                    split_at = (pos, m)

        if split_at is not None:
            pos, m = split_at
            code_part = line[:pos].rstrip()
            doc_part = line[pos + len(m) :].lstrip()
            if doc_part:
                out.append(indent + ford_marker + " " + doc_part)
            if code_part:
                out.append(code_part)
            continue

        out.append(line)

    return "\n".join(out)


def _choose_ford_marker(configured_markers: Sequence[str]) -> str:
    # Convention we enforce: doc markers are exactly 2 chars and start with '!'.
    markers = [m for m in (configured_markers or []) if m and len(m) == 2 and m[0] == "!"]

    # FORD cannot use docmark == predocmark (so it can't represent '!!' directly).
    for m in markers:
        if m[1] != "!":
            return m
    return "!>"


def _pick_safe_alt(preferred: str, forbidden: Sequence[str], *, fallback: str) -> str:
    if preferred and preferred not in forbidden:
        return preferred
    if fallback and fallback not in forbidden:
        return fallback
    # Last resort: scan printable ASCII.
    for code in range(33, 127):
        ch = chr(code)
        if ch not in forbidden:
            return ch
    return "#"


def _ford_settings_and_marker(doc_markers: Sequence[str], *, directory: Path) -> tuple[ProjectSettings, str]:
    ford_marker = _choose_ford_marker(doc_markers)
    if len(ford_marker) != 2 or ford_marker[0] == ford_marker[1]:
        # Shouldn't happen due to choose logic, but keep it safe.
        ford_marker = "!>"

    # We always use '!' as the comment/docmark in the FORD convention.
    # predocmark is the configured doc character (e.g. '>').
    docmark, predocmark = "!", ford_marker[1]
    docmark_alt = "*"
    predocmark_alt = "|"
    if predocmark_alt == docmark:
        predocmark_alt = "+"

    settings = ProjectSettings(
        directory=directory,
        preprocess=False,
        quiet=True,
        dbg=False,
        warn=False,
    )
    settings.docmark = docmark
    settings.predocmark = predocmark
    settings.docmark_alt = docmark_alt
    settings.predocmark_alt = predocmark_alt

    return settings, ford_marker


class FORDFortranLexer(FortranLexer):
    """Parse Fortran sources using FORD.

    Notes:
    - FORD expects doc comments on their own lines; inline `!>` docs will be rewritten
      as normal comments so parsing does not fail.
    - This lexer is dependency-optional: it only works if `ford` is installed.
    """

    name = "ford"

    def parse(self, file_paths: Sequence[str], *, doc_markers: Sequence[str]) -> FortranParseResult:
        if not FORD_AVAILABLE:
            raise ImportError("FORD is not installed. Install it and retry (e.g. `pip install ford`).")

        modules: Dict[str, FortranModuleInfo] = {}
        submodules: Dict[str, FortranSubmoduleInfo] = {}
        programs: Dict[str, FortranProgramInfo] = {}

        directory = _common_parent_dir(file_paths)
        settings, ford_marker = _ford_settings_and_marker(doc_markers, directory=directory)

        for original_path in file_paths:
            src_path = Path(original_path)
            if not src_path.exists() or not src_path.is_file():
                continue

            text = src_path.read_text(encoding=settings.encoding, errors="replace")
            prepared = _prepare_text_for_ford(text, doc_markers, ford_marker=ford_marker)

            tmp_path = None
            try:
                fd, tmp_name = tempfile.mkstemp(suffix=src_path.suffix)
                os.close(fd)
                tmp_path = Path(tmp_name)
                tmp_path.write_text(prepared, encoding=settings.encoding)

                parsed = FortranSourceFile(str(tmp_path), settings=settings)
                items = getattr(parsed, "markdownable_items", []) or []
                for item in items:
                    self._ingest_item(item, modules=modules, submodules=submodules, programs=programs)
            finally:
                if tmp_path is not None:
                    try:
                        tmp_path.unlink()
                    except OSError:
                        pass

        return FortranParseResult(modules=modules, submodules=submodules, programs=programs)

    def _ingest_item(
                        self,
                        item: object,
                        *,
                        modules: Dict[str, FortranModuleInfo],
                        submodules: Dict[str, FortranSubmoduleInfo],
                        programs: Dict[str, FortranProgramInfo],
                    ) -> None:
        name = getattr(item, "name", None)
        if not name:
            return
        name = str(name)

        doc = _get_doc(item)
        loc = _get_location(item)

        if isinstance(item, FordModule):
            modules.setdefault(
                name,
                FortranModuleInfo(name=name, doc=doc, procedures=[], types=[], interfaces=[], location=loc),
            )
            self._ingest_container_children(item, container_name=name, modules=modules)
            return

        if isinstance(item, FordSubmodule):
            parent = getattr(item, "parent", None) or getattr(item, "ancestor", None) or ""
            submodules.setdefault(
                name,
                FortranSubmoduleInfo(
                    name=name,
                    parent=str(parent),
                    doc=doc,
                    procedures=[],
                    types=[],
                    interfaces=[],
                    location=loc,
                ),
            )
            self._ingest_submodule_children(item, container_name=name, submodules=submodules)
            return

        if isinstance(item, FordProgram):
            programs.setdefault(name, FortranProgramInfo(name=name, doc=doc, location=loc))
            return

    def _ingest_container_children(self, item: FordModule, *, container_name: str, modules: Dict[str, FortranModuleInfo]) -> None:
        current = modules.get(container_name)
        if current is None:
            return

        procedures: List[FortranProcedure] = list(current.procedures)
        types: List[FortranType] = list(current.types)
        interfaces: List[FortranInterface] = list(current.interfaces)

        for f in getattr(item, "functions", []) or []:
            procedures.append(self._convert_procedure(f, kind="function"))
        for s in getattr(item, "subroutines", []) or []:
            procedures.append(self._convert_procedure(s, kind="subroutine"))
        for t in getattr(item, "types", []) or []:
            types.append(FortranType(name=str(getattr(t, "name", "")), doc=_get_doc(t), location=_get_location(t)))
        for i in getattr(item, "interfaces", []) or []:
            interfaces.append(FortranInterface(name=str(getattr(i, "name", "")), doc=_get_doc(i), location=_get_location(i)))

        # Filter empty names
        procedures = [p for p in procedures if p.name]
        types = [t for t in types if t.name]
        interfaces = [i for i in interfaces if i.name]

        modules[container_name] = FortranModuleInfo(
            name=current.name,
            doc=current.doc,
            procedures=procedures,
            types=types,
            interfaces=interfaces,
            location=current.location,
        )

    def _ingest_submodule_children(
        self, item: FordSubmodule, *, container_name: str, submodules: Dict[str, FortranSubmoduleInfo]
    ) -> None:
        current = submodules.get(container_name)
        if current is None:
            return

        procedures: List[FortranProcedure] = list(current.procedures)
        types: List[FortranType] = list(current.types)
        interfaces: List[FortranInterface] = list(current.interfaces)

        for f in getattr(item, "functions", []) or []:
            procedures.append(self._convert_procedure(f, kind="function"))
        for s in getattr(item, "subroutines", []) or []:
            procedures.append(self._convert_procedure(s, kind="subroutine"))
        for t in getattr(item, "types", []) or []:
            types.append(FortranType(name=str(getattr(t, "name", "")), doc=_get_doc(t), location=_get_location(t)))
        for i in getattr(item, "interfaces", []) or []:
            interfaces.append(FortranInterface(name=str(getattr(i, "name", "")), doc=_get_doc(i), location=_get_location(i)))

        procedures = [p for p in procedures if p.name]
        types = [t for t in types if t.name]
        interfaces = [i for i in interfaces if i.name]

        submodules[container_name] = FortranSubmoduleInfo(
            name=current.name,
            parent=current.parent,
            doc=current.doc,
            procedures=procedures,
            types=types,
            interfaces=interfaces,
            location=current.location,
        )

    def _convert_procedure(self, proc: object, *, kind: str) -> FortranProcedure:
        name = str(getattr(proc, "name", ""))
        args: List[FortranArgument] = []
        for a in getattr(proc, "args", []) or []:
            aname = str(getattr(a, "name", ""))
            if not aname:
                continue
            args.append(
                FortranArgument(
                    name=aname,
                    decl=_arg_decl_from_ford(a),
                    doc=_get_doc(a),
                    location=_get_location(a),
                )
            )

        return FortranProcedure(
            name=name,
            kind=kind,
            signature=_proc_signature_from_ford(proc),
            doc=_get_doc(proc),
            location=_get_location(proc),
            arguments=tuple(args),
        )
