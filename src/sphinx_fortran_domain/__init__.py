from __future__ import annotations

from importlib import metadata
from pathlib import Path
import glob
import hashlib
import json
import os
from typing import Iterable, List, Sequence

from sphinx.application import Sphinx
from sphinx.errors import SphinxError
from sphinx.util import logging

from sphinx_fortran_domain.domain import FortranDomain
from sphinx_fortran_domain.lexers import get_lexer, register_builtin_lexers


logger = logging.getLogger(__name__)


def _read_root_version_file() -> str | None:
	# Layout: <root>/src/sphinx_fortran_domain/__init__.py
	root = Path(__file__).resolve().parents[2]
	try:
		return (root / "VERSION").read_text(encoding="utf-8").strip()
	except OSError:
		return None


def _detect_version() -> str:
	# Prefer installed distribution metadata (works for wheels and editable installs).
	try:
		v = metadata.version("sphinx-fortran-domain")
		if v:
			return v
	except metadata.PackageNotFoundError:
		pass

	# Fallback for source checkouts without an installed dist.
	v = _read_root_version_file()
	return v or "0.0.0"


__version__ = _detect_version()


def _safe_mtime(path: Path) -> float:
	try:
		return path.stat().st_mtime
	except Exception:
		return 0.0


def _compute_fingerprint(app: Sphinx) -> str:
	"""Compute a fingerprint for the generated Fortran symbols.

	Sphinx caches doctrees aggressively; if Fortran parsing output changes but the
	RST sources do not, pages may not be re-read and will keep stale content.
	We avoid that by fingerprinting the *inputs* that affect symbol generation.

	Includes:
	- fortran config (lexer name + doc markers)
	- the collected Fortran source file mtimes
	- mtimes of this extension's own python files (so code changes invalidate)
	"""
	lexer_name = str(getattr(app.config, "fortran_lexer", "regex"))
	doc_markers = _doc_markers_from_config(app)
	files = _collect_fortran_files(app)

	package_dir = Path(__file__).resolve().parent
	ext_files = [
		package_dir / "__init__.py",
		package_dir / "directives.py",
		package_dir / "domain.py",
		package_dir / "lexers" / "__init__.py",
		package_dir / "lexers" / "lexer_regex.py",
		package_dir / "lexers" / "lexer_ford.py",
	]

	data = {
		"lexer": lexer_name,
		"doc_markers": doc_markers,
		"sources": [(p, os.path.getmtime(p) if os.path.exists(p) else 0.0) for p in files],
		"ext": [(str(p), _safe_mtime(p)) for p in ext_files],
	}
	blob = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
	return hashlib.sha1(blob).hexdigest()


def _maybe_force_reread(app: Sphinx, env, added, changed, removed):
	"""Sphinx event handler: mark docs outdated when our fingerprint changes."""
	try:
		fp = _compute_fingerprint(app)
	except Exception:
		# If fingerprinting fails for any reason, do not break the build.
		return []

	# env.domaindata stores per-domain persisted state.
	domaindata = getattr(env, "domaindata", {})
	fortran_data = domaindata.setdefault("f", {})
	prev = fortran_data.get("_fortran_fingerprint")
	if prev != fp:
		fortran_data["_fortran_fingerprint"] = fp
		# Re-read all docs so directives re-render with updated symbol data.
		try:
			docs = list(getattr(env, "found_docs", set()))
			logger.info("sphinx_fortran_domain: inputs changed; re-reading %d docs", len(docs))
			return docs
		except Exception:
			return []
	return []


def _as_list(value) -> List[str]:
	if value is None:
		return []
	if isinstance(value, str):
		return [value]
	return [str(v) for v in value]


def _as_chars(value) -> List[str]:
	"""Normalize a config value into a list of single-character strings."""
	if value is None:
		return []
	if isinstance(value, str):
		# Allow ">!@" style strings.
		return [c for c in value if c.strip()]
	return [str(v) for v in value]


def _doc_markers_from_config(app: Sphinx) -> List[str]:
	"""Return list of 2-character doc markers.

	Rule enforced:
	- A doc line is a Fortran comment line starting with '!'
	- The second character selects documentation (e.g. '>' for '!>')
	"""

	chars = _as_chars(getattr(app.config, "fortran_doc_chars", None))
	if chars:
		for c in chars:
			if len(c) != 1:
				raise SphinxError(f"fortran_doc_chars entries must be single characters, got: {c!r}")
		return ["!" + c for c in chars]

	# Backward-compatible alias.
	markers = _as_list(getattr(app.config, "fortran_doc_markers", []))
	markers = [m for m in markers if m]
	if markers:
		return markers

	# Default convention: !> doc lines
	return ["!>"]


def _collect_fortran_files(app: Sphinx) -> List[str]:
	exts = {e.lower() for e in _as_list(getattr(app.config, "fortran_file_extensions", []))}
	roots = _as_list(getattr(app.config, "fortran_sources", []))
	excludes = _as_list(getattr(app.config, "fortran_sources_exclude", []))
	if not roots:
		return []

	files: List[str] = []
	for root in roots:
		if any(ch in root for ch in "*?["):
			pattern = str((Path(app.confdir) / root))
			for match in glob.glob(pattern, recursive=True):
				p = Path(match)
				if p.is_file() and (not exts or p.suffix.lower() in exts):
					files.append(str(p))
			continue

		p = Path(root)
		if not p.is_absolute():
			p = Path(app.confdir) / p

		if p.is_dir():
			for child in p.rglob("*"):
				if child.is_file() and (not exts or child.suffix.lower() in exts):
					files.append(str(child))
		elif p.is_file():
			if not exts or p.suffix.lower() in exts:
				files.append(str(p))

	if excludes:
		def _norm(s: str) -> str:
			try:
				return os.path.normcase(str(Path(s).resolve()))
			except Exception:
				return os.path.normcase(str(Path(s)))

		exclude_files: set[str] = set()
		confdir = Path(app.confdir)
		for raw in excludes:
			pat = str(raw)
			# Glob patterns
			if any(ch in pat for ch in "*?["):
				pattern = str(confdir / pat)
				for match in glob.glob(pattern, recursive=True):
					p = Path(match)
					if p.is_dir():
						for child in p.rglob("*"):
							if child.is_file() and (not exts or child.suffix.lower() in exts):
								exclude_files.add(_norm(str(child)))
					elif p.is_file() and (not exts or p.suffix.lower() in exts):
						exclude_files.add(_norm(str(p)))
				continue

			p = Path(pat)
			if not p.is_absolute():
				p = confdir / p
			if p.is_dir():
				for child in p.rglob("*"):
					if child.is_file() and (not exts or child.suffix.lower() in exts):
						exclude_files.add(_norm(str(child)))
			elif p.is_file() and (not exts or p.suffix.lower() in exts):
				exclude_files.add(_norm(str(p)))

		if exclude_files:
			files = [f for f in files if _norm(f) not in exclude_files]

	# Deterministic order
	return sorted(set(files))


def _load_symbols(app: Sphinx) -> None:
	register_builtin_lexers()

	files = _collect_fortran_files(app)
	if not files:
		logger.info("sphinx_fortran_domain: no fortran_sources configured; skipping parse")
		return

	lexer_name = str(getattr(app.config, "fortran_lexer", "regex"))
	doc_markers = _doc_markers_from_config(app)

	try:
		lexer = get_lexer(lexer_name)
	except KeyError as exc:
		raise SphinxError(str(exc)) from exc

	try:
		result = lexer.parse(files, doc_markers=doc_markers)
	except Exception as exc:
		raise SphinxError(f"Fortran lexer '{lexer_name}' failed: {exc}") from exc

	domain = app.env.get_domain("f")
	getattr(domain, "set_parse_result")(result)
	logger.info(
		"sphinx_fortran_domain: parsed %d files (%d modules, %d submodules, %d programs) using '%s'",
		len(files),
		len(result.modules),
		len(result.submodules),
		len(result.programs),
		lexer_name,
	)


def setup(app: Sphinx):
	app.add_domain(FortranDomain)

	app.add_config_value("fortran_sources", default=[], rebuild="env")
	app.add_config_value("fortran_sources_exclude", default=[], rebuild="env")
	app.add_config_value("fortran_lexer", default="regex", rebuild="env")
	app.add_config_value("fortran_doc_chars", default=[">"], rebuild="env")
	app.add_config_value(
		"fortran_file_extensions",
		default=[
			".f", ".F",
			".for", ".FOR",
			".f90", ".F90",
			".f95", ".F95",
			".f03", ".F03",
			".f08", ".F08",
		],
		rebuild="env",
	)

	app.connect("builder-inited", _load_symbols)
	app.connect("env-get-outdated", _maybe_force_reread)

	return {
		"version": __version__,
		"parallel_read_safe": True,
		"parallel_write_safe": True,
	}
