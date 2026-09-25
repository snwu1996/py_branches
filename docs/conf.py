# Configuration file for the Sphinx documentation builder.
#
# Full reference: https://www.sphinx-doc.org/en/master/usage/configuration.html

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _package_version
import os
import sys

# tree_examples.py (the diagram factories) and _ext/render_trees.py (the
# extension that calls them) sit beside this file rather than in the installed
# package, so neither is importable without help.
_HERE = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, '_ext'))

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
    'render_trees',
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

# -- Doctest ------------------------------------------------------------------

# Every ``testcode`` block in a docstring or a page runs with these names
# already bound, so the examples read the way a user would write them rather
# than carrying a preamble of imports. Blocks that need to show an import for
# the reader's benefit still may - importing twice is harmless.
doctest_global_setup = """
import py_trees

from py_branches.alternating import ActivateBehavior
from py_branches.alternating import RunEveryRange
from py_branches.alternating import RunEveryX
from py_branches.alternating import run_alternating
from py_branches.blackboard import IncrementBlackboardVariable
from py_branches.blackboard import IncrementBlackboardVariableIfCondition
from py_branches.blackboard import RunIfBlackboardVariableEquals
from py_branches.blackboard import RunIfBlackboardVariableGreaterThan
from py_branches.blackboard import RunIfBlackboardVariableLessThan
from py_branches.blackboard import SetBlackboardVariableIfCondition
from py_branches.cooldown import Cooldown
from py_branches.counter import Counter
from py_branches.latch import Latch
from py_branches.pause import PauseSchedule
from py_branches.pause import PauseUniform
from py_branches.pause import PauseUntilKey
from py_branches.pause import load_schedule_file
from py_branches.random import RandomDelay
from py_branches.random import RandomRun
from py_branches.random import random_selector
from py_branches.retry import Retry
from py_branches.timeout import Timeout
from py_branches.visitors import StatusTransitionVisitor
from py_branches.visitors import TimerVisitor
"""

# Three examples in py_branches.pause stay plain code-blocks rather than
# testcode: PausePDF needs a sample data file, and load_schedule_file and
# PauseSchedule need a schedule on disk at a path relative to the caller. They
# are shown, not executed.
