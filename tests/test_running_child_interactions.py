#!/usr/bin/env python
"""How skip-style decorators behave when their child stays RUNNING.

Most of the suite drives children that complete on their first tick, so the
multi-tick paths are barely exercised. These tests pin what currently happens
when a child needs several ticks to finish and the decorator above it decides
to skip, advance, or latch in the meantime.

Several of these document behaviour that may not be intended -- see the
comments on individual tests.
"""
import py_trees

from py_branches.alternating import RunEveryRange
from py_branches.alternating import RunEveryX
from py_branches.alternating import run_alternating
from py_branches.latch import Latch


_r = py_trees.common.Status.RUNNING
_s = py_trees.common.Status.SUCCESS
_f = py_trees.common.Status.FAILURE


class MultiTickBehavior(py_trees.behaviour.Behaviour):
    """RUNNING for `running_ticks` ticks, then `final_status`.

    Counts ticks and completions separately so a test can tell "the child was
    ticked" apart from "the child finished a run".
    """

    def __init__(self, name, running_ticks, final_status=_s):
        super(MultiTickBehavior, self).__init__(name=name)
        self._running_ticks = running_ticks
        self._final_status = final_status
        self.update_count = 0
        self.completion_count = 0
        self.initialise_count = 0
        self._ticks_this_run = 0

    def initialise(self):
        self.initialise_count += 1
        self._ticks_this_run = 0

    def update(self):
        self.update_count += 1
        self._ticks_this_run += 1
        if self._ticks_this_run > self._running_ticks:
            self.completion_count += 1
            return self._final_status
        return _r


def test_multi_tick_behavior_helper():
    # The harness itself, so a failure elsewhere is not misread.
    behavior = MultiTickBehavior('slow', running_ticks=2)

    behavior.tick_once()
    assert behavior.status == _r
    behavior.tick_once()
    assert behavior.status == _r
    behavior.tick_once()
    assert behavior.status == _s

    assert behavior.update_count == 3
    assert behavior.completion_count == 1
    # initialise only fires on fresh entry, not on each RUNNING tick.
    assert behavior.initialise_count == 1


def test_latch_passes_running_through_without_latching():
    slow = MultiTickBehavior('slow', running_ticks=2)
    latch = Latch(slow, name='latch')

    latch.tick_once()
    assert latch.status == _r
    latch.tick_once()
    assert latch.status == _r

    # Still unlatched: the child has not succeeded yet.
    assert slow.completion_count == 0


def test_latch_engages_only_after_running_child_completes():
    slow = MultiTickBehavior('slow', running_ticks=2)
    latch = Latch(slow, name='latch')

    for _ in range(3):
        latch.tick_once()

    assert latch.status == _s
    assert slow.completion_count == 1
    assert slow.update_count == 3

    # Latched: further ticks short-circuit and the child is never ticked again.
    latch.tick_once()
    latch.tick_once()
    assert latch.status == _s
    assert slow.update_count == 3


def test_latch_never_engages_for_a_child_that_only_fails():
    slow = MultiTickBehavior('slow', running_ticks=1, final_status=_f)
    latch = Latch(slow, name='latch')

    latch.tick_once()
    assert latch.status == _r
    latch.tick_once()
    assert latch.status == _f

    # A FAILURE completion does not latch, so the child runs again.
    latch.tick_once()
    assert slow.update_count == 3
    assert slow.initialise_count == 2


def test_run_every_x_abandons_a_child_that_is_still_running():
    '''The skip branch fires on cycle count alone, mid-run or not.

    RunEveryX.tick checks _cycles_remaining before delegating, so a child left
    RUNNING from the previous tick is dropped rather than allowed to finish.
    '''
    slow = MultiTickBehavior('slow', running_ticks=3)
    every_x = RunEveryX(slow, name='every_x', every_x_range=(2, 2))

    # Cycle 1: skipped.
    every_x.tick_once()
    assert every_x.status == _f
    assert slow.update_count == 0

    # Cycle 2: the child runs and goes RUNNING.
    every_x.tick_once()
    assert every_x.status == _r
    assert slow.update_count == 1

    # Cycle 3: skipped again while the child is still mid-run.
    every_x.tick_once()
    assert every_x.status == _f
    assert slow.update_count == 1
    assert slow.completion_count == 0


def test_run_every_range_counts_an_external_invalidation_as_a_cycle():
    '''terminate() advances the cycle on any stop, including INVALID.

    A parent composite invalidating this decorator mid-run therefore consumes
    a cycle that the child never got to use.
    '''
    slow = MultiTickBehavior('slow', running_ticks=5)
    every_range = RunEveryRange(slow, name='every_range', max_range=3, run_range=(1, 1))

    every_range.tick_once()
    assert every_range.status == _r
    assert every_range._iteration == 1

    # Simulate a parent invalidating the subtree while the child is RUNNING.
    every_range.stop(py_trees.common.Status.INVALID)
    assert every_range._iteration == 2

    # Cycle 2 is outside run_range, so the child does not resume.
    every_range.tick_once()
    assert every_range.status == _f
    assert slow.update_count == 1
    assert slow.completion_count == 0


def test_run_alternating_counts_ticks_not_completions():
    '''A RUNNING child spends one "run" per tick, not one per completion.

    _RunAlternatingHelper increments its counter in initialise(), and the
    selector is built without memory, so every tick re-enters the helper and
    charges another run to the active behavior -- even though that behavior
    has not finished once. With counts=[2, 2] a child needing three ticks is
    therefore dropped before it ever completes.

    This pins current behaviour; whether it is the intended reading of
    "run this behavior N times" is an open question.
    '''
    slow = MultiTickBehavior('slow', running_ticks=2)
    quick = py_trees.behaviours.Success('quick')
    root = run_alternating('run_alternating', [slow, quick], counts=[2, 2])

    root.tick_once()
    assert root.status == _r
    assert slow.update_count == 1

    root.tick_once()
    assert root.status == _r
    assert slow.update_count == 2

    # Third tick: the helper has already counted two "runs", so it advances to
    # the next behavior and deactivates the slow one mid-flight.
    root.tick_once()
    assert slow.update_count == 2
    assert slow.completion_count == 0
    assert quick.status == _s


def test_run_alternating_completes_children_that_finish_in_one_tick():
    # The contrast case: single-tick children do get their full count.
    first = MultiTickBehavior('first', running_ticks=0)
    second = MultiTickBehavior('second', running_ticks=0)
    root = run_alternating('run_alternating', [first, second], counts=[2, 1])

    for _ in range(3):
        root.tick_once()

    assert first.completion_count == 2
    assert second.completion_count == 1
