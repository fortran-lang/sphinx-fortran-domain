from __future__ import annotations

import glob
import os
import re
from pathlib import Path
from typing import Iterable, Optional, Sequence


_WILDCARDS = "*?["


def _has_wildcards(s: str) -> bool:
	return any(ch in s for ch in _WILDCARDS)



def as_list(value) -> list[str]:
	"""Normalize a config value into a list of strings."""
	if value is None:
		return []
	if isinstance(value, str):
		return [value]
	return [str(v) for v in value]


def as_chars(value) -> list[str]:
	"""Normalize a config value into a list of single-character strings."""
	if value is None:
		return []
	if isinstance(value, str):
		# Allow ">!@" style strings.
		return [c for c in value if c.strip()]
	return [str(v) for v in value]

def doc_markers_from_doc_chars(doc_chars) -> list[str]:
	"""Convert `fortran_doc_chars` to concrete doc markers.

	Configured `fortran_doc_chars` is a collection of single characters like `['>']`.
	A doc marker is the two-character string that must appear at the start of a
	comment line, like `!>`.

	Raises ValueError if any entry is not a single character.
	"""
	chars = as_chars(doc_chars)
	if chars:
		for c in chars:
			if len(c) != 1:
				raise ValueError(f"fortran_doc_chars entries must be single characters, got: {c!r}")
		return ["!" + c for c in chars]

	# Default convention: !> doc lines
	return ["!>"]


def _norm_path(path: str) -> str:
	"""Normalize a path for comparison across platforms."""
	try:
		return os.path.normcase(str(Path(path).resolve()))
	except Exception:
		return os.path.normcase(str(Path(path)))


def read_text_utf8(path: str | Path) -> str:
	"""Read a text file as UTF-8, replacing invalid sequences."""
	return Path(path).read_text(encoding="utf-8", errors="replace")


def read_lines_utf8(path: str | Path) -> list[str]:
	"""Read a text file as UTF-8 lines, replacing invalid sequences."""
	return read_text_utf8(path).splitlines()


def strip_inline_comment(line: str) -> str:
	"""Remove a trailing Fortran comment introduced by '!' (best-effort)."""
	if "!" not in line:
		return line
	# Keep it simple: stop at the first '!' (not trying to handle strings).
	return line.split("!", 1)[0]


def is_doc_line(line: str, doc_markers: Sequence[str]) -> Optional[str]:
	"""Return doc text if the line is a doc line, else None."""
	stripped = line.lstrip()
	for marker in doc_markers:
		if stripped.startswith(marker):
			return stripped[len(marker) :].lstrip(" \t")
	return None


def find_inline_doc(line: str, doc_markers: Sequence[str]) -> Optional[tuple[int, str]]:
	"""Return (pos, marker) for the earliest inline doc marker, else None."""
	best: Optional[tuple[int, str]] = None
	for m in doc_markers:
		if not m:
			continue
		# Inline docs live in Fortran comments (introduced by '!').
		# Ignore markers that don't include '!' so we don't mis-detect operators like `=>`.
		if "!" not in m:
			continue
		pos = line.find(m)
		if pos == -1:
			continue
		if line[:pos].strip() == "":
			# Leading marker is handled by is_doc_line.
			continue
		if best is None or pos < best[0]:
			best = (pos, m)
	return best


def extract_predoc_before_line(lines: Sequence[str], idx: int, *, doc_markers: Sequence[str]) -> str | None:
	"""Extract contiguous doc lines immediately preceding `idx` (0-based)."""
	if idx <= 0:
		return None
	markers = [m for m in (doc_markers or []) if m and str(m).strip()]
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


_RE_END_PROGRAM = re.compile(r"^\s*end\s*program\b", re.IGNORECASE)
_RE_CONTAINS = re.compile(r"^\s*contains\b", re.IGNORECASE)
_RE_USE = re.compile(
	r"^\s*use\b\s*(?:,\s*(?:non_intrinsic|intrinsic)\s*)?(?:\s*::\s*)?([A-Za-z_]\w*)\b",
	re.IGNORECASE,
)


def extract_use_dependencies(source: str) -> list[str]:
	"""Extract unique module names from USE statements (best-effort)."""
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


def collect_fortran_source_files_from_config(*, confdir: Path, config) -> list[str]:
	"""Collect sources using standard Sphinx config names.

	This is intentionally Sphinx-independent: `config` can be any object with
	`fortran_sources`, `fortran_sources_exclude`, and `fortran_file_extensions` attributes.
	"""
	extensions = {e.lower() for e in as_list(getattr(config, "fortran_file_extensions", []))}
	roots = as_list(getattr(config, "fortran_sources", []))
	excludes = as_list(getattr(config, "fortran_sources_exclude", []))
	return collect_fortran_source_files(
		confdir=Path(confdir),
		roots=roots,
		extensions=extensions,
		excludes=excludes,
	)


def collect_fortran_source_files(
	*,
	confdir: Path,
	roots: Sequence[str],
	extensions: set[str],
	excludes: Sequence[str] = (),
) -> list[str]:
	"""Collect Fortran source files from roots, honoring excludes.

	- roots may be files, directories, or glob patterns (relative to confdir).
	- excludes may be files, directories, or glob patterns (relative to confdir).
	- extensions is a set of allowed suffixes (lower-cased). Empty means "allow any".
	
	Returns a deterministic sorted list of file paths as strings.
	"""
	if not roots:
		return []

	confdir = Path(confdir)
	files: list[str] = []

	def _accept(p: Path) -> bool:
		return p.is_file() and (not extensions or p.suffix.lower() in extensions)

	def _add_from_dir(d: Path) -> None:
		for child in d.rglob("*"):
			if _accept(child):
				files.append(str(child))

	for raw_root in roots:
		root = str(raw_root)
		if _has_wildcards(root):
			pattern = str(confdir / root)
			for match in glob.glob(pattern, recursive=True):
				p = Path(match)
				if _accept(p):
					files.append(str(p))
			continue

		p = Path(root)
		if not p.is_absolute():
			p = confdir / p
		if p.is_dir():
			_add_from_dir(p)
		elif _accept(p):
			files.append(str(p))

	if excludes:
		exclude_files: set[str] = set()

		def _exclude_path(p: Path) -> None:
			if p.is_dir():
				for child in p.rglob("*"):
					if _accept(child):
						exclude_files.add(_norm_path(str(child)))
			elif _accept(p):
				exclude_files.add(_norm_path(str(p)))

		for raw_ex in excludes:
			pat = str(raw_ex)
			if _has_wildcards(pat):
				pattern = str(confdir / pat)
				for match in glob.glob(pattern, recursive=True):
					_exclude_path(Path(match))
				continue

			p = Path(pat)
			if not p.is_absolute():
				p = confdir / p
			_exclude_path(p)

		if exclude_files:
			files = [f for f in files if _norm_path(f) not in exclude_files]

	# Deterministic order
	return sorted(set(files))
