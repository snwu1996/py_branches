#!/usr/bin/env python

import time
import py_trees

from py_branches.retry import Retry


_r = py_trees.common.Status.RUNNING
_s = py_trees.common.Status.SUCCESS
_f = py_trees.common.Status.FAILURE
_i = py_trees.common.Status.INVALID


class FailNTimesBehavior(py_trees.behaviour.Behaviour):
    '''
    Returns FAILURE for the first fail_count calls to update(), then SUCCESS.
    Does NOT reset on initialise() so the counter persists across retries,
    letting us test the cumulative retry logic.
    '''
    def __init__(self, name, fail_count):
        super().__init__(name=name)
        self._fail_count = fail_count
        self._call_count = 0

    def initialise(self):
        pass  # preserve count across retries

    def update(self):
        if self._call_count < self._fail_count:
            self._call_count += 1
            return _f
        return _s


def test_retry_all_fail():
    '''Child always fails; Retry gives up after max_attempts.'''
    child = FailNTimesBehavior('child', fail_count=10)
    retry = Retry(child, name='retry', max_attempts=3)

    retry.tick_once()
    assert retry.status == _r  # attempt 1 failed, 2 remaining

    retry.tick_once()
    assert retry.status == _r  # attempt 2 failed, 1 remaining

    retry.tick_once()
    assert retry.status == _f  # attempt 3 failed, exhausted


def test_retry_succeeds_before_max():
    '''Child fails twice then succeeds; Retry returns SUCCESS.'''
    child = FailNTimesBehavior('child', fail_count=2)
    retry = Retry(child, name='retry', max_attempts=5)

    retry.tick_once()
    assert retry.status == _r  # attempt 1 failed

    retry.tick_once()
    assert retry.status == _r  # attempt 2 failed

    retry.tick_once()
    assert retry.status == _s  # attempt 3 succeeded


def test_retry_succeeds_first_try():
    '''Child succeeds immediately; Retry returns SUCCESS on first tick.'''
    child = FailNTimesBehavior('child', fail_count=0)
    retry = Retry(child, name='retry', max_attempts=3)

    retry.tick_once()
    assert retry.status == _s


def test_retry_max_attempts_one():
    '''max_attempts=1 means a single failure returns FAILURE immediately.'''
    child = FailNTimesBehavior('child', fail_count=1)
    retry = Retry(child, name='retry', max_attempts=1)

    retry.tick_once()
    assert retry.status == _f


def test_retry_resets_on_reinitialise():
    '''After exhaustion, stopping the decorator to INVALID resets the attempt counter.'''
    child = FailNTimesBehavior('child', fail_count=10)
    retry = Retry(child, name='retry', max_attempts=3)

    # Exhaust all attempts
    for _ in range(3):
        retry.tick_once()
    assert retry.status == _f

    # Reset decorator and child state
    retry.stop(py_trees.common.Status.INVALID)
    child._call_count = 0
    child._fail_count = 2  # fail twice then succeed

    retry.tick_once()
    assert retry.status == _r  # attempt 1 failed

    retry.tick_once()
    assert retry.status == _r  # attempt 2 failed

    retry.tick_once()
    assert retry.status == _s  # attempt 3 succeeded


def test_retry_with_delay():
    '''Child fails once; delay is respected before re-running the child.'''
    child = FailNTimesBehavior('child', fail_count=1)
    delay = 0.05
    retry = Retry(child, name='retry_delay', max_attempts=2, delay=delay)

    # First tick: child fails, delay starts
    retry.tick_once()
    assert retry.status == _r
    assert child.status == _f  # child returned FAILURE this tick

    # Second tick (during delay): child NOT re-ticked, still RUNNING
    retry.tick_once()
    assert retry.status == _r
    assert child.status == _f  # child hasn't been re-run

    # Wait for delay to expire, then tick: child re-runs and succeeds
    time.sleep(delay + 0.01)
    retry.tick_once()
    assert retry.status == _s


def test_retry_running_child_passes_through():
    '''If child is RUNNING, Retry stays RUNNING without counting an attempt.'''
    running_child = py_trees.behaviours.Running(name='running')
    retry = Retry(running_child, name='retry', max_attempts=3)

    for _ in range(5):
        retry.tick_once()
        assert retry.status == _r
        assert retry._attempts == 0
