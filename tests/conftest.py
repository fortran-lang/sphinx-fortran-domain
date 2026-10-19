from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_sphinx_global_state():
	"""Undo the global docutils/Sphinx registrations left behind by in-process builds.

	Without this, every Sphinx app built after the first one warns that node
	classes are "already registered" (Sphinx 7), which breaks tests building
	with ``warningiserror=True`` depending on test order. This mirrors what
	``sphinx.testing``'s ``SphinxTestApp.cleanup`` does.
	"""
	yield
	try:
		from sphinx.testing.util import _clean_up_global_state
	except ImportError:  # pragma: no cover - older/newer Sphinx without the helper
		return
	_clean_up_global_state()
