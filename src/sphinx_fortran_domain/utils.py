from __future__ import annotations

import glob
import os
from pathlib import Path
from typing import Iterable, Sequence


_WILDCARDS = "*?["


def _has_wildcards(s: str) -> bool:
	return any(ch in s for ch in _WILDCARDS)


def _as_list(value) -> list[str]:
	"""Normalize a config value into a list of strings."""
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


def _norm_path(path: str) -> str:
	"""Normalize a path for comparison across platforms."""
	try:
		return os.path.normcase(str(Path(path).resolve()))
	except Exception:
		return os.path.normcase(str(Path(path)))


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
