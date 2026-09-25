"""Render the documentation's behavior-tree diagrams at build time.

py_trees can draw any tree via Graphviz, which means the diagrams in these docs
can be generated from the same code that the docs describe rather than drawn by
hand and left to rot. This extension calls every factory in
:data:`tree_examples.DIAGRAMS` on ``builder-inited`` and writes one SVG per
entry into ``_static/trees/``.

Requires the ``dot`` binary on PATH (the ``graphviz`` apt package on Read the
Docs). A render that fails logs a Sphinx warning and leaves the SVG missing,
which surfaces again as an image-not-readable warning from the page that
references it — and fails the build outright under ``-W``.
"""

import os

from sphinx.util import logging as sphinx_logging

logger = sphinx_logging.getLogger(__name__)

#: Relative to the Sphinx source directory.
OUTPUT_SUBDIR = os.path.join('_static', 'trees')

#: render_dot_tree writes one file per format; only the SVG is referenced.
UNUSED_FORMATS = ('.dot', '.png')


def _render_one(diagram, target_directory):
    """Write a single diagram's SVG. Returns True on success."""
    import py_trees

    try:
        root = diagram.factory()
    except Exception as exc:  # noqa: BLE001 - a bad factory must not abort the build
        logger.warning(
            'render_trees: building tree %r failed: %s', diagram.name, exc
        )
        return False

    try:
        py_trees.display.render_dot_tree(
            root,
            name=diagram.name,
            target_directory=target_directory,
            with_blackboard_variables=diagram.with_blackboard_variables,
        )
    except TypeError as exc:
        # A py_trees release that changed render_dot_tree's signature.
        logger.warning(
            'render_trees: render_dot_tree rejected our arguments (%s); '
            'the installed py_trees may be incompatible with this extension',
            exc,
        )
        return False
    except Exception as exc:  # noqa: BLE001 - most likely a missing dot binary
        logger.warning(
            'render_trees: rendering %r failed: %s. Is graphviz installed?',
            diagram.name,
            exc,
        )
        return False

    for extension in UNUSED_FORMATS:
        stale = os.path.join(target_directory, diagram.name + extension)
        if os.path.exists(stale):
            os.remove(stale)

    return True


def render_trees(app):
    """builder-inited handler: regenerate every diagram."""
    try:
        import tree_examples
    except ImportError as exc:
        logger.warning('render_trees: could not import tree_examples: %s', exc)
        return

    target_directory = os.path.join(app.srcdir, OUTPUT_SUBDIR)
    os.makedirs(target_directory, exist_ok=True)

    rendered = sum(
        _render_one(diagram, target_directory) for diagram in tree_examples.DIAGRAMS
    )
    logger.info(
        'render_trees: wrote %d of %d diagrams to %s',
        rendered,
        len(tree_examples.DIAGRAMS),
        OUTPUT_SUBDIR,
    )


def setup(app):
    app.connect('builder-inited', render_trees)
    return {
        'version': '1.0',
        'parallel_read_safe': True,
        'parallel_write_safe': True,
    }
