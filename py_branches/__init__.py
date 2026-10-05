"""Higher-level behaviors and decorators for py_trees.

`py_trees <https://py-trees.readthedocs.io/>`_ supplies the machinery for
behavior trees; this package supplies the patterns that keep getting rewritten
on top of it. Each module is small and independent, so importing
``py_branches`` gives access to all of them:

============================== ================================================
Module                         What it covers
============================== ================================================
:mod:`py_branches.alternating` Cycling between behaviors, and running one every
                               N ticks
:mod:`py_branches.blackboard`  Reading, writing and gating on blackboard
                               variables
:mod:`py_branches.clock`       Injectable time sources, for testable timing
:mod:`py_branches.cooldown`    Enforcing a minimum gap between runs
:mod:`py_branches.counter`     Capping the total number of runs
:mod:`py_branches.latch`       Making a first SUCCESS permanent
:mod:`py_branches.pause`       Waiting: random, sampled, keyboard or scheduled
:mod:`py_branches.random`      Probabilistic execution and weighted selection
:mod:`py_branches.retry`       Retrying a failing child, or repeating one
                               until it fails
:mod:`py_branches.runtime`     Running a tree as a process: pacing,
                               signals, exit codes and teardown
:mod:`py_branches.surgery`     Editing a tree after it is built: walk, find,
                               replace, prune, graft
:mod:`py_branches.timeout`     Failing a child that runs too long
:mod:`py_branches.visitors`    Logging status transitions and run durations
============================== ================================================

Most of the decorators take a ``success_if_skip`` flag, which decides what a
skipped tick reports to the parent composite — FAILURE reads as "try the next
child" to a Selector, SUCCESS makes the skip invisible to a Sequence.

Every behavior that measures elapsed time takes a keyword-only ``clock``, so
timing can be driven by a test instead of the wall clock — see
:mod:`py_branches.clock`.
"""

from . import alternating
from . import blackboard
from . import clock
from . import cooldown
from . import counter
from . import latch
from . import pause
from . import random
from . import retry
from . import runtime
from . import surgery
from . import timeout
from . import visitors

# Re-exported so `import py_branches` gives access to every submodule without
# a second import; listed here so the linter reads them as the public surface
# they are rather than unused imports.
__all__ = [
    "alternating",
    "blackboard",
    "clock",
    "cooldown",
    "counter",
    "latch",
    "pause",
    "random",
    "retry",
    "runtime",
    "surgery",
    "timeout",
    "visitors",
]
