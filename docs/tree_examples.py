"""Trees rendered as diagrams in the documentation.

Each factory here builds a subtree that is worth *seeing* rather than just
describing — one where the structure py_branches generates is not obvious from
the call that generates it. The ``render_trees`` Sphinx extension calls every
factory in :data:`DIAGRAMS` at build time and writes an SVG per entry into
``_static/trees/``.

The trees are built but never ticked, so behaviors that would need real
resources at runtime are safe to include.

To add a diagram: write a factory returning a root behavior, add a
:class:`Diagram` entry below, and reference
``_static/trees/<name>.svg`` from a page.
"""

from collections import namedtuple

import py_trees

from py_branches.alternating import run_alternating
from py_branches.blackboard import IncrementBlackboardVariable
from py_branches.blackboard import RunIfBlackboardVariableGreaterThan
from py_branches.random import random_selector
from py_branches.retry import Retry
from py_branches.timeout import Timeout

#: name: basename of the generated SVG.
#: factory: callable returning the root behavior.
#: with_blackboard_variables: annotate the graph with blackboard keys.
Diagram = namedtuple('Diagram', ['name', 'factory', 'with_blackboard_variables'])
Diagram.__new__.__defaults__ = (False,)


def alternating_cycle():
    """Three behaviors cycling for 3, 2 and 4 ticks respectively."""
    a = py_trees.behaviours.Success(name='A')
    b = py_trees.behaviours.Success(name='B')
    c = py_trees.behaviours.Success(name='C')
    return run_alternating('Cycle', [a, b, c], [3, 2, 4])


def weighted_selection():
    """Weighted choice between three behaviors, at 20%, 30% and 50%."""
    a = py_trees.behaviours.Success(name='Idle')
    b = py_trees.behaviours.Success(name='Patrol')
    c = py_trees.behaviours.Success(name='Investigate')
    return random_selector('WeightedChoice', [a, b, c], [0.2, 0.3, 0.5])


def blackboard_gate():
    """A counter incremented every tick, gating a behavior on its value."""
    increment = IncrementBlackboardVariable(
        name='CountTicks', variable_name='tick_count', increment_by=1
    )
    action = py_trees.behaviours.Success(name='ReportProgress')
    gate = RunIfBlackboardVariableGreaterThan(
        action,
        name='OnceAboveTen',
        variable_name='tick_count',
        greater_than=10,
    )
    root = py_trees.composites.Sequence(name='Root', memory=True)
    root.add_children([increment, gate])
    return root


def bounded_retry():
    """Retry around Timeout: each attempt is bounded, the cycle is not."""
    child = py_trees.behaviours.Running(name='FetchRemoteState')
    guarded = Timeout(child, name='PerAttemptTimeout', duration=5.0)
    return Retry(guarded, name='RetryFetch', max_attempts=3, delay=1.0)


DIAGRAMS = [
    Diagram('alternating_cycle', alternating_cycle),
    Diagram('weighted_selection', weighted_selection),
    # with_blackboard_variables stays off: py_trees reads a behaviour's attached
    # clients, and this package constructs py_trees.blackboard.Client() directly
    # rather than calling attach_blackboard_client, so there is nothing to draw.
    Diagram('blackboard_gate', blackboard_gate),
    Diagram('bounded_retry', bounded_retry),
]
