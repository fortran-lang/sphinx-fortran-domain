# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html
import os
import sys
sys.path.insert(0, os.path.abspath('..'))
sys.path.insert(0, os.path.abspath('../src'))

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'Sphinx Fortran Domain'
copyright = '2025, Sphinx Fortran Domain maintainers'
author = 'fortran-lang community'
with open(os.path.join("..", "VERSION")) as f:
    release = f.read().strip()

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.autosummary',
    'sphinx.ext.mathjax',
    'sphinx.ext.viewcode',
    'myst_parser',
    'sphinx_fortran_domain',
]

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

# Select a lexer (built-in: "regex")
fortran_lexer = "regex"

# Doc comment markers to recognize (comment-only lines)
fortran_doc_chars = ["!", ">"]

fortran_sources = [
	"../example",
]

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'pydata_sphinx_theme'
html_static_path = ['_static']

# Keep the top-left navbar title concise.
html_title = f"{project} {release}"

# Small theme override(s).
html_css_files = [
    "custom.css",
]

# If true, the current module name will be prepended to all description
# unit titles (such as .. function::).
add_module_names = False
