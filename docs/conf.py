# Configuration file for the Sphinx documentation builder.
#
# Full reference: https://www.sphinx-doc.org/en/master/usage/configuration.html

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _package_version

# -- Project information -----------------------------------------------------

project = 'py_branches'
author = 'Shunong Wu'
copyright = '2024, Shunong Wu'  # noqa: A001 - Sphinx requires this name.

try:
    # Single source of truth: the installed package version, which poetry
    # takes from pyproject.toml. CI already enforces a version bump per
    # release PR, so hardcoding it here would just create a second place to
    # forget.
    release = _package_version('py_branches')
except PackageNotFoundError:
    # Building against a source tree that was never installed.
    release = '0.0.0+unknown'

# Short X.Y version shown in the sidebar.
version = '.'.join(release.split('.')[:2])

# -- General configuration ---------------------------------------------------

extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.napoleon',
    'sphinx.ext.intersphinx',
    'sphinx.ext.viewcode',
    'sphinx.ext.doctest',
    'sphinx.ext.graphviz',
    'sphinx_autodoc_typehints',
    'myst_parser',
]

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

# The docs are authored in Markdown; MyST handles it. reStructuredText still
# works for anything that needs a directive MyST cannot express inline.
source_suffix = {
    '.rst': 'restructuredtext',
    '.md': 'markdown',
}

# -- MyST ---------------------------------------------------------------------

myst_enable_extensions = [
    'colon_fence',
    'deflist',
    'fieldlist',
]

# Generate anchors for headings so cross-file links to sections resolve.
myst_heading_anchors = 3

# -- Autodoc ------------------------------------------------------------------

autodoc_default_options = {
    'members': True,
    # Everything here subclasses py_trees.behaviour.Behaviour or
    # py_trees.decorators.Decorator, and knowing which is load-bearing when
    # reading the API.
    'show-inheritance': True,
    'member-order': 'bysource',
    'special-members': '__init__',
    'undoc-members': True,
    # Private helpers like _RunAlternatingHelper and _get_and_check are
    # implementation detail.
    'exclude-members': '__weakref__',
}

# Signatures stay clean; types are rendered into the parameter descriptions by
# sphinx_autodoc_typehints.
autodoc_typehints = 'description'
autodoc_typehints_description_target = 'documented_params'

# Docstrings are Google-style (see py_branches/visitors.py for the reference
# shape), so napoleon parses them and NumPy-style parsing stays off.
napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_include_init_with_doc = True

# -- Intersphinx --------------------------------------------------------------

intersphinx_mapping = {
    'python': ('https://docs.python.org/3', None),
    'py_trees': ('https://py-trees.readthedocs.io/en/devel/', None),
    'numpy': ('https://numpy.org/doc/stable/', None),
}

# -- HTML output --------------------------------------------------------------

html_theme = 'sphinx_rtd_theme'
html_static_path = ['_static']
html_title = f'{project} {version}'

html_theme_options = {
    'navigation_depth': 3,
    'collapse_navigation': False,
    'sticky_navigation': True,
    'style_external_links': True,
}

# -- Graphviz -----------------------------------------------------------------

# SVG stays sharp at any zoom and keeps text selectable; the default is PNG.
graphviz_output_format = 'svg'
