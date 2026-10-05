#!/usr/bin/env python

import time

import py_trees
import pytest

from py_branches.clock import ManualClock
from py_branches.retry import Retry
from py_branches.retry import RunUntilFailed
from py_branches.retry import RunUntilXSuccesses

_r = py_trees.common.Status.RUNNING
_s = py_trees.common.Status.SUCCESS
_f = py_trees.common.Status.FAILURE
_i = py_trees.common.Status.INVALID


class FailNTimesBehavior(py_trees.behaviour.Behaviour):
    """
    Returns FAILURE for the first fail_count calls to update(), then SUCCESS.
    Does NOT reset on initialise() so the counter persists across retries,
    letting us test the cumulative retry logic.
    """

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
    """Child always fails; Retry gives up after max_attempts."""
    child = FailNTimesBehavior("child", fail_count=10)
    retry = Retry(child, name="retry", max_attempts=3)

    retry.tick_once()
    assert retry.status == _r  # attempt 1 failed, 2 remaining

    retry.tick_once()
    assert retry.status == _r  # attempt 2 failed, 1 remaining

    retry.tick_once()
    assert retry.status == _f  # attempt 3 failed, exhausted


def test_retry_succeeds_before_max():
    """Child fails twice then succeeds; Retry returns SUCCESS."""
    child = FailNTimesBehavior("child", fail_count=2)
    retry = Retry(child, name="retry", max_attempts=5)

    retry.tick_once()
    assert retry.status == _r  # attempt 1 failed

    retry.tick_once()
    assert retry.status == _r  # attempt 2 failed

    retry.tick_once()
    assert retry.status == _s  # attempt 3 succeeded


def test_retry_succeeds_first_try():
    """Child succeeds immediately; Retry returns SUCCESS on first tick."""
    child = FailNTimesBehavior("child", fail_count=0)
    retry = Retry(child, name="retry", max_attempts=3)

    retry.tick_once()
    assert retry.status == _s


def test_retry_max_attempts_one():
    """max_attempts=1 means a single failure returns FAILURE immediately."""
    child = FailNTimesBehavior("child", fail_count=1)
    retry = Retry(child, name="retry", max_attempts=1)

    retry.tick_once()
    assert retry.status == _f


def test_retry_resets_on_reinitialise():
    """After exhaustion, stopping the decorator to INVALID resets the attempt counter."""
    child = FailNTimesBehavior("child", fail_count=10)
    retry = Retry(child, name="retry", max_attempts=3)

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
    """Child fails once; delay is respected before re-running the child."""
    child = FailNTimesBehavior("child", fail_count=1)
    delay = 0.05
    retry = Retry(child, name="retry_delay", max_attempts=2, delay=delay)

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
    """If child is RUNNING, Retry stays RUNNING without counting an attempt."""
    running_child = py_trees.behaviours.Running(name="running")
    retry = Retry(running_child, name="retry", max_attempts=3)

    for _ in range(5):
        retry.tick_once()
        assert retry.status == _r
        assert retry._attempts == 0


def test_retry_waits_exactly_delay_between_attempts_on_manual_clock():
    """The child is not re-ticked until the delay has elapsed."""
    child = py_trees.behaviours.Failure(name="failure")
    clock = ManualClock()
    retry = Retry(child, name="retry", max_attempts=2, delay=1.0, clock=clock)

    # First attempt fails; the decorator waits rather than retrying at once.
    retry.tick_once()
    assert retry.status == _r
    assert retry._waiting
    assert retry._attempts == 1

    # Part-way through the delay: still waiting, no further attempt spent.
    clock.advance(0.999)
    retry.tick_once()
    assert retry.status == _r
    assert retry._attempts == 1

    # Delay elapsed: the second (and final) attempt runs and exhausts the budget.
    clock.advance(0.001)
    retry.tick_once()
    assert retry.status == _f
    assert retry._attempts == 2


def test_retry_zero_delay_does_not_wait_on_manual_clock():
    """delay=0.0 keeps the old behaviour: attempts back-to-back, no timer."""
    child = py_trees.behaviours.Failure(name="failure")
    clock = ManualClock()
    retry = Retry(child, name="retry", max_attempts=3, delay=0.0, clock=clock)

    retry.tick_once()
    assert retry.status == _r
    assert not retry._waiting

    retry.tick_once()
    assert retry.status == _r

    # Three attempts spent across three ticks, with no clock movement at all.
    retry.tick_once()
    assert retry.status == _f
    assert clock.time() == 0.0


class SucceedNTimesBehavior(py_trees.behaviour.Behaviour):
    """
    Returns SUCCESS for the first succeed_count calls to update(), then FAILURE.
    Does NOT reset on initialise() so the counter persists across runs.
    """

    def __init__(self, name, succeed_count):
        super().__init__(name=name)
        self._succeed_count = succeed_count
        self._call_count = 0

    def initialise(self):
        pass  # preserve count across runs

    def update(self):
        if self._call_count < self._succeed_count:
            self._call_count += 1
            return _s
        return _f


def test_run_until_failed_fails_first_run():
    """Child fails immediately; RunUntilFailed returns SUCCESS on first tick."""
    child = SucceedNTimesBehavior("child", succeed_count=0)
    loop = RunUntilFailed(child, name="loop", max_runs=3)

    loop.tick_once()
    assert loop.status == _s


def test_run_until_failed_succeeds_then_fails():
    """Child succeeds twice then fails; RunUntilFailed returns SUCCESS."""
    child = SucceedNTimesBehavior("child", succeed_count=2)
    loop = RunUntilFailed(child, name="loop", max_runs=5)

    loop.tick_once()
    assert loop.status == _r  # run 1 succeeded

    loop.tick_once()
    assert loop.status == _r  # run 2 succeeded

    loop.tick_once()
    assert loop.status == _s  # run 3 failed, loop done


def test_run_until_failed_cap_reached():
    """Child always succeeds; RunUntilFailed returns FAILURE after max_runs."""
    child = SucceedNTimesBehavior("child", succeed_count=10)
    loop = RunUntilFailed(child, name="loop", max_runs=3)

    loop.tick_once()
    assert loop.status == _r

    loop.tick_once()
    assert loop.status == _r

    loop.tick_once()
    assert loop.status == _f
    assert child._call_count == 3


def test_run_until_failed_max_runs_one():
    """max_runs=1 means a single success returns FAILURE immediately."""
    child = SucceedNTimesBehavior("child", succeed_count=1)
    loop = RunUntilFailed(child, name="loop", max_runs=1)

    loop.tick_once()
    assert loop.status == _f


def test_run_until_failed_resets_on_reinitialise():
    """After hitting the cap, stopping the decorator to INVALID resets the run counter."""
    child = SucceedNTimesBehavior("child", succeed_count=10)
    loop = RunUntilFailed(child, name="loop", max_runs=3)

    for _ in range(3):
        loop.tick_once()
    assert loop.status == _f

    loop.stop(py_trees.common.Status.INVALID)
    child._call_count = 0
    child._succeed_count = 2  # succeed twice then fail

    loop.tick_once()
    assert loop.status == _r

    loop.tick_once()
    assert loop.status == _r

    loop.tick_once()
    assert loop.status == _s


def test_run_until_failed_running_child_passes_through():
    """If child is RUNNING, RunUntilFailed stays RUNNING without counting a run."""
    running_child = py_trees.behaviours.Running(name="running")
    loop = RunUntilFailed(running_child, name="loop", max_runs=3)

    for _ in range(5):
        loop.tick_once()
        assert loop.status == _r
        assert loop._attempts == 0


def test_run_until_failed_waits_exactly_delay_between_runs_on_manual_clock():
    """The child is not re-ticked until the delay has elapsed."""
    child = py_trees.behaviours.Success(name="success")
    clock = ManualClock()
    loop = RunUntilFailed(child, name="loop", max_runs=2, delay=1.0, clock=clock)

    loop.tick_once()
    assert loop.status == _r
    assert loop._waiting
    assert loop._attempts == 1

    clock.advance(0.999)
    loop.tick_once()
    assert loop.status == _r
    assert loop._attempts == 1

    clock.advance(0.001)
    loop.tick_once()
    assert loop.status == _f
    assert loop._attempts == 2


def test_run_until_failed_zero_delay_does_not_wait_on_manual_clock():
    """delay=0.0 runs back-to-back, no timer."""
    child = py_trees.behaviours.Success(name="success")
    clock = ManualClock()
    loop = RunUntilFailed(child, name="loop", max_runs=3, clock=clock)

    loop.tick_once()
    assert loop.status == _r
    assert not loop._waiting

    loop.tick_once()
    assert loop.status == _r

    loop.tick_once()
    assert loop.status == _f
    assert clock.time() == 0.0


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"max_runs": 0}, r"max_runs\(0\)"),
        ({"max_runs": 3, "delay": -1.0}, r"delay\(-1.0\)"),
    ],
)
def test_run_until_failed_rejects_invalid_arguments(kwargs, message):
    child = py_trees.behaviours.Success(name="success")
    with pytest.raises(ValueError, match=message):
        RunUntilFailed(child, name="loop", **kwargs)


@pytest.mark.parametrize("succeed_count", [0, 1, 2, 3, 4, 10])
def test_run_until_failed_matches_retry_of_inverted_child(succeed_count):
    """RunUntilFailed is Retry(Inverter(child)) under another name."""
    child = SucceedNTimesBehavior("child", succeed_count=succeed_count)
    loop = RunUntilFailed(child, name="loop", max_runs=4)

    oracle_child = SucceedNTimesBehavior("oracle_child", succeed_count=succeed_count)
    oracle = Retry(
        py_trees.decorators.Inverter(name="invert", child=oracle_child),
        name="oracle",
        max_attempts=4,
    )

    for _ in range(6):
        loop.tick_once()
        oracle.tick_once()
        assert loop.status == oracle.status


class ScriptedBehavior(py_trees.behaviour.Behaviour):
    """
    Returns the statuses in ``script`` one per call to update(), repeating the
    last one once the script runs out. Does NOT reset on initialise().
    """

    def __init__(self, name, script):
        super().__init__(name=name)
        self._script = list(script)
        self._call_count = 0

    def initialise(self):
        pass  # preserve position across runs

    def update(self):
        status = self._script[min(self._call_count, len(self._script) - 1)]
        self._call_count += 1
        return status


def test_run_until_x_successes_all_succeed():
    """Child always succeeds; SUCCESS on exactly the num_successes-th tick."""
    child = ScriptedBehavior("child", [_s])
    loop = RunUntilXSuccesses(child, name="loop", num_successes=3, max_runs=5)

    loop.tick_once()
    assert loop.status == _r

    loop.tick_once()
    assert loop.status == _r

    loop.tick_once()
    assert loop.status == _s
    assert child._call_count == 3


def test_run_until_x_successes_failures_do_not_reset_count():
    """S F S S reaches three successes in total on run 4."""
    child = ScriptedBehavior("child", [_s, _f, _s, _s])
    loop = RunUntilXSuccesses(child, name="loop", num_successes=3, max_runs=5)

    for _ in range(3):
        loop.tick_once()
        assert loop.status == _r

    loop.tick_once()
    assert loop.status == _s


def test_run_until_x_successes_cap_reached():
    """Too few successes; FAILURE on exactly the max_runs-th tick."""
    child = ScriptedBehavior("child", [_s, _f])
    loop = RunUntilXSuccesses(child, name="loop", num_successes=2, max_runs=4)

    for _ in range(3):
        loop.tick_once()
        assert loop.status == _r

    loop.tick_once()
    assert loop.status == _f
    assert child._call_count == 4


def test_run_until_x_successes_uses_every_run_when_target_unreachable():
    """Two failures make 3-of-4 impossible after run 2, but all runs still happen."""
    child = ScriptedBehavior("child", [_f, _f, _s, _s])
    loop = RunUntilXSuccesses(child, name="loop", num_successes=3, max_runs=4)

    for _ in range(3):
        loop.tick_once()
        assert loop.status == _r

    loop.tick_once()
    assert loop.status == _f
    assert child._call_count == 4
    assert loop._hits == 2


def test_run_until_x_successes_num_successes_equals_max_runs():
    """With no slack, a single failure means FAILURE at the cap."""
    child = ScriptedBehavior("child", [_s, _f, _s])
    loop = RunUntilXSuccesses(child, name="loop", num_successes=3, max_runs=3)

    loop.tick_once()
    assert loop.status == _r

    loop.tick_once()
    assert loop.status == _r

    loop.tick_once()
    assert loop.status == _f


def test_run_until_x_successes_resets_on_reinitialise():
    """Stopping the decorator to INVALID resets both counters."""
    child = ScriptedBehavior("child", [_f])
    loop = RunUntilXSuccesses(child, name="loop", num_successes=2, max_runs=3)

    for _ in range(3):
        loop.tick_once()
    assert loop.status == _f

    loop.stop(py_trees.common.Status.INVALID)
    child._script = [_s]

    loop.tick_once()
    assert loop.status == _r
    assert loop._attempts == 1
    assert loop._hits == 1

    loop.tick_once()
    assert loop.status == _s


def test_run_until_x_successes_running_child_passes_through():
    """If child is RUNNING, the decorator stays RUNNING without counting a run."""
    running_child = py_trees.behaviours.Running(name="running")
    loop = RunUntilXSuccesses(running_child, name="loop", num_successes=2, max_runs=3)

    for _ in range(5):
        loop.tick_once()
        assert loop.status == _r
        assert loop._attempts == 0
        assert loop._hits == 0


def test_run_until_x_successes_waits_exactly_delay_on_manual_clock():
    """The delay applies after a FAILURE as well as after a SUCCESS."""
    child = ScriptedBehavior("child", [_f, _s, _s])
    clock = ManualClock()
    loop = RunUntilXSuccesses(
        child, name="loop", num_successes=2, max_runs=3, delay=1.0, clock=clock
    )

    loop.tick_once()  # run 1 fails
    assert loop.status == _r
    assert loop._waiting

    clock.advance(0.999)
    loop.tick_once()
    assert loop.status == _r
    assert child._call_count == 1

    clock.advance(0.001)
    loop.tick_once()  # run 2 succeeds
    assert loop.status == _r
    assert child._call_count == 2
    assert loop._waiting

    clock.advance(0.999)
    loop.tick_once()
    assert child._call_count == 2

    clock.advance(0.001)
    loop.tick_once()  # run 3 succeeds
    assert loop.status == _s
    assert child._call_count == 3


def test_run_until_x_successes_zero_delay_does_not_wait_on_manual_clock():
    """delay=0.0 runs back-to-back, no timer."""
    child = ScriptedBehavior("child", [_s])
    clock = ManualClock()
    loop = RunUntilXSuccesses(
        child, name="loop", num_successes=2, max_runs=2, clock=clock
    )

    loop.tick_once()
    assert loop.status == _r
    assert not loop._waiting

    loop.tick_once()
    assert loop.status == _s
    assert clock.time() == 0.0


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"num_successes": 0, "max_runs": 3}, r"num_successes\(0\)"),
        ({"num_successes": 4, "max_runs": 3}, r"max_runs\(3\) must be at least"),
        ({"num_successes": 1, "max_runs": 3, "delay": -1.0}, r"delay\(-1.0\)"),
    ],
)
def test_run_until_x_successes_rejects_invalid_arguments(kwargs, message):
    child = py_trees.behaviours.Success(name="success")
    with pytest.raises(ValueError, match=message):
        RunUntilXSuccesses(child, name="loop", **kwargs)


@pytest.mark.parametrize(
    "script",
    [[_s], [_f], [_f, _s], [_f, _f, _s], [_f, _f, _f, _s], [_f, _s, _f]],
)
def test_run_until_x_successes_with_one_success_matches_retry(script):
    """num_successes=1 is Retry under another name."""
    child = ScriptedBehavior("child", script)
    loop = RunUntilXSuccesses(child, name="loop", num_successes=1, max_runs=3)

    oracle_child = ScriptedBehavior("oracle_child", script)
    oracle = Retry(oracle_child, name="oracle", max_attempts=3)

    for _ in range(5):
        loop.tick_once()
        oracle.tick_once()
        assert loop.status == oracle.status
