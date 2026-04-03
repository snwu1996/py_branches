#!/usr/bin/env python

import time
import py_trees

from py_branches.random import RandomDelay


_r = py_trees.common.Status.RUNNING
_s = py_trees.common.Status.SUCCESS
_f = py_trees.common.Status.FAILURE
_i = py_trees.common.Status.INVALID


class TrackingBehavior(py_trees.behaviour.Behaviour):
    '''Returns a fixed status and counts how many times it has been ticked.'''
    def __init__(self, name, return_status):
        super().__init__(name=name)
        self._return_status = return_status
        self.tick_count = 0

    def update(self):
        self.tick_count += 1
        return self._return_status


def test_random_delay_zero():
    '''low=high=0 means no delay; child runs on the very first tick.'''
    child = TrackingBehavior('child', _s)
    rd = RandomDelay(child, name='rd', low=0.0, high=0.0)

    rd.tick_once()
    assert rd.status == _s
    assert child.tick_count == 1


def test_random_delay_blocks_child_during_wait():
    '''Child is not ticked until the delay has elapsed.'''
    child = TrackingBehavior('child', _s)
    duration = 0.1
    rd = RandomDelay(child, name='rd', low=duration, high=duration)

    # Ticks during delay: RUNNING, child never ticked.
    rd.tick_once()
    assert rd.status == _r
    assert child.tick_count == 0

    rd.tick_once()
    assert rd.status == _r
    assert child.tick_count == 0

    # After delay: child runs and its status is passed through.
    time.sleep(duration + 0.01)
    rd.tick_once()
    assert rd.status == _s
    assert child.tick_count == 1


def test_random_delay_passes_through_failure():
    '''FAILURE from child is passed through after the delay.'''
    child = TrackingBehavior('child', _f)
    duration = 0.05
    rd = RandomDelay(child, name='rd', low=duration, high=duration)

    rd.tick_once()
    assert rd.status == _r

    time.sleep(duration + 0.01)
    rd.tick_once()
    assert rd.status == _f
    assert child.tick_count == 1


def test_random_delay_resamples_on_reentry():
    '''A new delay is sampled on each fresh entry, not reused across runs.'''
    child = TrackingBehavior('child', _s)
    duration = 0.05
    rd = RandomDelay(child, name='rd', low=duration, high=duration)

    # First run.
    rd.tick_once()
    assert rd.status == _r
    time.sleep(duration + 0.01)
    rd.tick_once()
    assert rd.status == _s
    assert child.tick_count == 1

    # Re-entry: decorator is no longer RUNNING, so delay restarts.
    rd.tick_once()
    assert rd.status == _r       # waiting again
    assert child.tick_count == 1  # child not re-run yet

    time.sleep(duration + 0.01)
    rd.tick_once()
    assert rd.status == _s
    assert child.tick_count == 2


def test_random_delay_running_child_passes_through():
    '''While child stays RUNNING, the decorator stays RUNNING without re-delaying.'''
    class RunThenSucceed(py_trees.behaviour.Behaviour):
        def __init__(self):
            super().__init__(name='run_then_succeed')
            self._ticks = 0

        def initialise(self):
            self._ticks = 0

        def update(self):
            self._ticks += 1
            return _r if self._ticks < 3 else _s

    child = RunThenSucceed()
    duration = 0.05
    rd = RandomDelay(child, name='rd', low=duration, high=duration)

    # Wait out the delay.
    rd.tick_once()
    assert rd.status == _r
    time.sleep(duration + 0.01)

    # Child now runs for 3 ticks (RUNNING x2, then SUCCESS).
    rd.tick_once()
    assert rd.status == _r   # child tick 1: RUNNING

    rd.tick_once()
    assert rd.status == _r   # child tick 2: RUNNING

    rd.tick_once()
    assert rd.status == _s   # child tick 3: SUCCESS
    assert child._ticks == 3


def test_random_delay_sampled_within_range():
    '''The sampled delay always falls within [low, high].'''
    child = py_trees.behaviours.Success(name='success')
    low, high = 0.02, 0.08
    rd = RandomDelay(child, name='rd', low=low, high=high)

    for _ in range(10):
        rd.stop(py_trees.common.Status.INVALID)
        rd.tick_once()  # triggers fresh entry and samples a new delay
        assert low <= rd._delay <= high
