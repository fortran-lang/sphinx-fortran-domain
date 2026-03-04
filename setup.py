"""Compatibility shim for legacy tooling that still invokes setup.py directly.

Primary project metadata lives in pyproject.toml (PEP 621). Keeping setup.py as a
thin wrapper avoids duplicated metadata drift and setuptools overwrite warnings.
"""

from setuptools import setup


setup()