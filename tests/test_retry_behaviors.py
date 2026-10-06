#!/usr/bin/env python

import random
import time

import py_trees
import pytest

from py_branches.clock import ManualClock
from py_branches.delay import DelayConstant
from py_branches.delay import DelayExponentialBackoff
from py_branches.delay import DelayUniform
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


class CountingDelay:
    """A Delay that records every run it is sampled with."""

    def __init__(self, seconds):
        self.seconds = seconds
        self.runs = []

    def sample(self, run):
        self.runs.append(run)
        return self.seconds


def _ticks_until_child_reruns(decorator, child, clock, step=0.25, limit=100):
    """Advance the clock in steps until the child is ticked again; return the wait."""
    before = child._call_count
    waited = 0.0
    for _ in range(limit):
        clock.advance(step)
        waited += step
        decorator.tick_once()
        if child._call_count != before:
            return waited
    raise AssertionError("child never re-ran")


def test_retry_exponential_backoff_waits_1_2_4_on_manual_clock():
    child = ScriptedBehavior("child", [_f])
    clock = ManualClock()
    retry = Retry(
        child,
        name="retry",
        max_attempts=4,
        delay=DelayExponentialBackoff(1.0),
        clock=clock,
    )

    retry.tick_once()  # attempt 1 fails
    waits = [_ticks_until_child_reruns(retry, child, clock) for _ in range(3)]
    assert waits == [1.0, 2.0, 4.0]
    assert retry.status == _f


def test_retry_backoff_restarts_after_reinitialise():
    child = ScriptedBehavior("child", [_f])
    clock = ManualClock()
    delay = CountingDelay(1.0)
    retry = Retry(child, name="retry", max_attempts=3, delay=delay, clock=clock)

    retry.tick_once()
    for _ in range(2):
        _ticks_until_child_reruns(retry, child, clock)
    assert retry.status == _f
    assert delay.runs == [1, 2]

    retry.stop(py_trees.common.Status.INVALID)
    retry.tick_once()
    _ticks_until_child_reruns(retry, child, clock)
    assert delay.runs == [1, 2, 1, 2]


def test_retry_samples_once_per_gap_not_per_tick():
    child = ScriptedBehavior("child", [_f])
    clock = ManualClock()
    delay = CountingDelay(1.0)
    retry = Retry(child, name="retry", max_attempts=2, delay=delay, clock=clock)

    retry.tick_once()
    for _ in range(3):
        clock.advance(0.1)
        retry.tick_once()
    assert delay.runs == [1]


def test_retry_uniform_delay_waits_exactly_the_drawn_value():
    expected = random.Random(7).uniform(0.5, 1.5)
    child = ScriptedBehavior("child", [_f])
    clock = ManualClock()
    retry = Retry(
        child,
        name="retry",
        max_attempts=2,
        delay=DelayUniform(0.5, 1.5, rng=random.Random(7)),
        clock=clock,
    )

    retry.tick_once()
    assert retry._wait_t == expected

    clock.advance(expected - 0.001)
    retry.tick_once()
    assert child._call_count == 1

    clock.advance(0.001)
    retry.tick_once()
    assert child._call_count == 2


def test_retry_zero_sampled_delay_does_not_wait():
    child = ScriptedBehavior("child", [_f, _s])
    retry = Retry(child, name="retry", max_attempts=2, delay=DelayConstant(0.0))

    retry.tick_once()
    assert not retry._waiting
    retry.tick_once()
    assert retry.status == _s


def test_run_until_failed_accepts_a_delay():
    child = ScriptedBehavior("child", [_s, _s, _f])
    clock = ManualClock()
    loop = RunUntilFailed(
        child,
        name="loop",
        max_runs=5,
        delay=DelayExponentialBackoff(1.0),
        clock=clock,
    )

    loop.tick_once()
    waits = [_ticks_until_child_reruns(loop, child, clock) for _ in range(2)]
    assert waits == [1.0, 2.0]
    assert loop.status == _s


def test_run_until_x_successes_accepts_a_delay():
    child = ScriptedBehavior("child", [_s, _f, _s])
    clock = ManualClock()
    delay = CountingDelay(0.5)
    loop = RunUntilXSuccesses(
        child, name="loop", num_successes=2, max_runs=3, delay=delay, clock=clock
    )

    loop.tick_once()
    for _ in range(2):
        _ticks_until_child_reruns(loop, child, clock)
    assert loop.status == _s
    assert delay.runs == [1, 2]


def test_rerun_decorators_reject_non_delay_values():
    child = py_trees.behaviours.Success(name="success")
    with pytest.raises(TypeError):
        Retry(child, name="retry", max_attempts=2, delay="1.0")  # type: ignore[arg-type]
