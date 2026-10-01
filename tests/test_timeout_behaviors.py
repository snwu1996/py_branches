#!/usr/bin/env python

import time

import py_trees

from py_branches.clock import ManualClock
from py_branches.timeout import Timeout

_r = py_trees.common.Status.RUNNING
_s = py_trees.common.Status.SUCCESS
_f = py_trees.common.Status.FAILURE
_i = py_trees.common.Status.INVALID


class RunningThenBehavior(py_trees.behaviour.Behaviour):
    """
    Stays RUNNING for run_ticks ticks, then returns final_status.
    Resets on initialise().
    """

    def __init__(self, name, run_ticks, final_status):
        super().__init__(name=name)
        self._run_ticks = run_ticks
        self._final_status = final_status
        self._ticks = 0

    def initialise(self):
        self._ticks = 0

    def update(self):
        if self._ticks < self._run_ticks:
            self._ticks += 1
            return _r
        return self._final_status


def test_timeout_child_succeeds_immediately():
    """Child returns SUCCESS before timeout; Timeout passes SUCCESS through."""
    child = py_trees.behaviours.Success(name="success")
    timeout = Timeout(child, name="timeout", duration=5.0)

    timeout.tick_once()
    assert timeout.status == _s


def test_timeout_child_fails_immediately():
    """Child returns FAILURE before timeout; Timeout passes FAILURE through."""
    child = py_trees.behaviours.Failure(name="failure")
    timeout = Timeout(child, name="timeout", duration=5.0)

    timeout.tick_once()
    assert timeout.status == _f


def test_timeout_child_completes_before_deadline():
    """Child stays RUNNING briefly then succeeds; Timeout returns SUCCESS."""
    child = RunningThenBehavior("child", run_ticks=2, final_status=_s)
    timeout = Timeout(child, name="timeout", duration=5.0)

    timeout.tick_once()
    assert timeout.status == _r

    timeout.tick_once()
    assert timeout.status == _r

    timeout.tick_once()
    assert timeout.status == _s


def test_timeout_expires_while_running():
    """Child stays RUNNING past the timeout; Timeout returns FAILURE."""
    child = RunningThenBehavior("child", run_ticks=100, final_status=_s)
    duration = 0.05
    timeout = Timeout(child, name="timeout", duration=duration)

    timeout.tick_once()
    assert timeout.status == _r

    time.sleep(duration + 0.01)

    timeout.tick_once()
    assert timeout.status == _f
    assert child.status == _i  # child was stopped


def test_timeout_resets_on_reinitialise():
    """After a timeout, the timer resets when the decorator is re-entered."""
    child = RunningThenBehavior("child", run_ticks=100, final_status=_s)
    duration = 0.05
    timeout = Timeout(child, name="timeout", duration=duration)

    # First run: let the timeout expire
    timeout.tick_once()
    assert timeout.status == _r
    time.sleep(duration + 0.01)
    timeout.tick_once()
    assert timeout.status == _f

    # Re-enter: timer should reset; long duration this time
    timeout.stop(py_trees.common.Status.INVALID)
    timeout._duration = 10.0

    timeout.tick_once()
    assert timeout.status == _r  # not timed out on fresh entry

    timeout.tick_once()
    assert timeout.status == _r  # still RUNNING, well within 10s


def test_timeout_fires_exactly_at_duration_on_manual_clock():
    """Not a tick before the duration, and FAILURE on the tick it is reached."""
    child = py_trees.behaviours.Running(name="running")
    clock = ManualClock()
    guarded = Timeout(child, name="timeout", duration=5.0, clock=clock)

    guarded.tick_once()
    assert guarded.status == _r

    clock.advance(4.999)
    guarded.tick_once()
    assert guarded.status == _r
    assert child.status == _r

    clock.advance(0.001)
    guarded.tick_once()
    assert guarded.status == _f
    assert child.status == _i  # stopped, not left dangling


def test_timeout_bounds_one_running_stretch_not_total_on_manual_clock():
    """The clock restarts in initialise(), so a fresh entry gets a full budget."""
    child = py_trees.behaviours.Running(name="running")
    clock = ManualClock()
    guarded = Timeout(child, name="timeout", duration=5.0, clock=clock)

    guarded.tick_once()
    clock.advance(4.0)
    guarded.tick_once()
    assert guarded.status == _r

    # Fresh entry: the 4 seconds already spent do not carry over.
    guarded.stop(py_trees.common.Status.INVALID)
    guarded.tick_once()
    clock.advance(4.0)
    guarded.tick_once()
    assert guarded.status == _r

    clock.advance(1.0)
    guarded.tick_once()
    assert guarded.status == _f
