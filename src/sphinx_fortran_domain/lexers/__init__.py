from __future__ import annotations

from dataclasses import dataclass, field
from importlib import import_module
from typing import Callable, Dict, Iterable, List, Mapping, MutableMapping, Optional, Protocol, Sequence


@dataclass(frozen=True)
class SourceLocation:
	path: str
	lineno: int # 1-based line number in the original source file 


@dataclass(frozen=True)
class FortranArgument:
	name: str
	decl: str | None = None  # e.g. "type(vector_type), intent(in)"
	doc: str | None = None
	location: SourceLocation | None = None


@dataclass(frozen=True)
class FortranProcedure:
	name: str
	kind: str  # "function" | "subroutine"
	signature: str | None = None  # e.g. "pure function foo(a) -> res"
	doc: str | None = None
	location: SourceLocation | None = None
	arguments: Sequence[FortranArgument] = field(default_factory=tuple)
	# For functions, the result variable (e.g. `result(res)` or implicit function-name result).
	# Stored as a FortranArgument to reuse decl/doc formatting.
	result: FortranArgument | None = None


@dataclass(frozen=True)
class FortranComponent:
	"""A derived-type component (field/member)."""

	name: str
	decl: str | None = None  # e.g. "real" or "real, dimension(3,3)"
	doc: str | None = None
	location: SourceLocation | None = None


@dataclass(frozen=True)
class FortranTypeBoundProcedure:
	"""A type-bound procedure binding (method)."""

	name: str  # binding name as used in code: `x%name()`
	target: str | None = None  # concrete procedure name, if known
	doc: str | None = None
	location: SourceLocation | None = None


@dataclass(frozen=True)
class FortranType:
	name: str
	doc: str | None = None
	components: Sequence[FortranComponent] = field(default_factory=list)
	bound_procedures: Sequence[FortranTypeBoundProcedure] = field(default_factory=list)
	location: SourceLocation | None = None


@dataclass(frozen=True)
class FortranInterface:
	name: str
	doc: str | None = None
	location: SourceLocation | None = None


@dataclass(frozen=True)
class FortranModuleInfo:
	name: str
	doc: str | None = None
	procedures: Sequence[FortranProcedure] = field(default_factory=list)
	types: Sequence[FortranType] = field(default_factory=list)
	interfaces: Sequence[FortranInterface] = field(default_factory=list)
	location: SourceLocation | None = None


@dataclass(frozen=True)
class FortranSubmoduleInfo:
	name: str
	parent: str
	doc: str | None = None
	procedures: Sequence[FortranProcedure] = field(default_factory=list)
	types: Sequence[FortranType] = field(default_factory=list)
	interfaces: Sequence[FortranInterface] = field(default_factory=list)
	location: SourceLocation | None = None


@dataclass(frozen=True)
class FortranProgramInfo:
	name: str
	doc: str | None = None
	location: SourceLocation | None = None
	# Modules referenced via USE statements in the main program unit.
	dependencies: Sequence[str] = field(default_factory=tuple)
	# Internal procedures (after `contains`).
	procedures: Sequence[FortranProcedure] = field(default_factory=list)
	# Optional raw source text for the full program unit (best-effort), including
	# the `program` and `end program` lines and any internal procedures.
	source: str | None = None


@dataclass(frozen=True)
class FortranParseResult:
	modules: Mapping[str, FortranModuleInfo]
	submodules: Mapping[str, FortranSubmoduleInfo]
	programs: Mapping[str, FortranProgramInfo] = field(default_factory=dict)


class FortranLexer(Protocol):
	"""A lightweight interface for parsing Fortran sources.

	The goal is not a full compiler frontend. This is just enough structure
	to drive documentation directives and cross-references.
	"""

	name: str

	def parse(
		self,
		file_paths: Sequence[str],
		*,
		doc_markers: Sequence[str],
	) -> FortranParseResult: ...


_LEXER_REGISTRY: MutableMapping[str, Callable[[], FortranLexer]] = {}


def register_lexer(name: str, factory: Callable[[], FortranLexer]) -> None:
	"""Register a lexer factory.

	External packages can call this from their own Sphinx extension setup.
	"""

	key = name.strip().lower()
	if not key:
		raise ValueError("lexer name must be non-empty")
	_LEXER_REGISTRY[key] = factory


def available_lexers() -> List[str]:
	return sorted(_LEXER_REGISTRY.keys())


def get_lexer(name: str) -> FortranLexer:
	key = (name or "").strip().lower()
	if key not in _LEXER_REGISTRY:
		raise KeyError(
			f"Unknown Fortran lexer '{name}'. Available: {', '.join(available_lexers()) or '(none)'}"
		)
	return _LEXER_REGISTRY[key]()


def _safe_register_builtin(name: str, module: str, symbol: str) -> None:
	def _factory() -> FortranLexer:
		mod = import_module(module)
		cls = getattr(mod, symbol)
		return cls()

	register_lexer(name, _factory)


def register_builtin_lexers() -> None:
	"""Register the built-in lexers (always available in this package)."""

	if "regex" not in _LEXER_REGISTRY:
		_safe_register_builtin("regex", "sphinx_fortran_domain.lexers.lexer_regex", "RegexFortranLexer")

	# These are intentionally minimal stubs to keep the core package small.
	if "ford" not in _LEXER_REGISTRY:
		_safe_register_builtin("ford", "sphinx_fortran_domain.lexers.lexer_ford", "FORDFortranLexer")

	if "lfortran" not in _LEXER_REGISTRY:
		_safe_register_builtin("lfortran", "sphinx_fortran_domain.lexers.lexer_lfortran", "LFortranLexer")
