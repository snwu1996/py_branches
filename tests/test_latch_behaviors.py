#!/usr/bin/env python

import py_trees

from py_branches.latch import Latch


_r = py_trees.common.Status.RUNNING
_s = py_trees.common.Status.SUCCESS
_f = py_trees.common.Status.FAILURE
_i = py_trees.common.Status.INVALID


class TrackingBehavior(py_trees.behaviour.Behaviour):
    '''Behaviour that counts how many times it has been ticked.'''
    def __init__(self, name, return_status):
        super().__init__(name=name)
        self._return_status = return_status
        self.tick_count = 0

    def update(self):
        self.tick_count += 1
        return self._return_status


def test_latch_engages_on_success():
    '''Once child returns SUCCESS, subsequent ticks never re-run the child.'''
    child = TrackingBehavior('child', _s)
    latch = Latch(child, name='latch')

    latch.tick_once()
    assert latch.status == _s
    assert child.tick_count == 1
    assert latch._latched

    for _ in range(5):
        latch.tick_once()
        assert latch.status == _s
        assert child.tick_count == 1  # child never re-ticked


def test_latch_does_not_engage_on_failure():
    '''Child returning FAILURE does not engage the latch.'''
    child = TrackingBehavior('child', _f)
    latch = Latch(child, name='latch')

    for i in range(3):
        latch.tick_once()
        assert latch.status == _f
        assert child.tick_count == i + 1  # child is re-run each tick
        assert not latch._latched


def test_latch_does_not_engage_while_running():
    '''Child returning RUNNING does not engage the latch.'''
    child = TrackingBehavior('child', _r)
    latch = Latch(child, name='latch')

    for i in range(3):
        latch.tick_once()
        assert latch.status == _r
        assert not latch._latched


def test_latch_reset_allows_rerun():
    '''reset() disengages the latch and lets the child run again.'''
    child = TrackingBehavior('child', _s)
    latch = Latch(child, name='latch')

    # Engage latch
    latch.tick_once()
    assert latch._latched
    assert child.tick_count == 1

    # Latch is active: child not re-run
    latch.tick_once()
    assert child.tick_count == 1

    # Reset: child runs again
    latch.reset()
    assert not latch._latched
    latch.tick_once()
    assert child.tick_count == 2
    assert latch._latched  # immediately re-latched since child succeeds


def test_latch_reset_multiple_cycles():
    '''Latch can be engaged, reset, and re-engaged multiple times.'''
    child = TrackingBehavior('child', _s)
    latch = Latch(child, name='latch')

    for cycle in range(3):
        latch.tick_once()
        assert child.tick_count == cycle + 1
        assert latch._latched

        # Multiple ticks: latched, child not re-run
        latch.tick_once()
        latch.tick_once()
        assert child.tick_count == cycle + 1

        latch.reset()

    assert child.tick_count == 3


def test_latch_state_persists_across_reentry():
    '''_latched is not cleared by initialise(); it persists until reset().'''
    child = TrackingBehavior('child', _s)
    latch = Latch(child, name='latch')

    # Engage
    latch.tick_once()
    assert latch._latched

    # Simulate the decorator being stopped to INVALID externally
    # (e.g. parent sequence aborted) then re-entered.
    latch.stop(py_trees.common.Status.INVALID)
    assert latch._latched  # persists

    # Re-entry without reset: still latched, child not re-run
    latch.tick_once()
    assert latch.status == _s
    assert child.tick_count == 1
