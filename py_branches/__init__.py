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
:mod:`py_branches.cooldown`    Enforcing a minimum gap between runs
:mod:`py_branches.counter`     Capping the total number of runs
:mod:`py_branches.latch`       Making a first SUCCESS permanent
:mod:`py_branches.pause`       Waiting: random, sampled, keyboard or scheduled
:mod:`py_branches.random`      Probabilistic execution and weighted selection
:mod:`py_branches.retry`       Retrying a failing child
:mod:`py_branches.timeout`     Failing a child that runs too long
:mod:`py_branches.visitors`    Logging status transitions and run durations
============================== ================================================

Most of the decorators take a ``success_if_skip`` flag, which decides what a
skipped tick reports to the parent composite — FAILURE reads as "try the next
child" to a Selector, SUCCESS makes the skip invisible to a Sequence.
"""
from . import alternating
from . import blackboard
from . import cooldown
from . import counter
from . import latch
from . import pause
from . import random
from . import retry
from . import timeout
from . import visitors
