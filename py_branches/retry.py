#!/usr/bin/env python3
"""Re-run a child behavior, optionally with a delay between runs.

Three decorators that differ only in what ends the loop: :class:`Retry`
re-runs a child that fails, for flaky operations that are worth attempting
more than once; :class:`RunUntilFailed` re-runs a child that succeeds, for
work that should repeat until the child reports it is done; and
:class:`RunUntilXSuccesses` re-runs a child until it has succeeded a given
number of times, for work that needs several good results.
"""

import logging

import py_trees

from .clock import Clock
from .clock import default_clock
from .delay import Delay
from .delay import as_delay

logger = logging.getLogger(__name__)


class _RunUntilCount(py_trees.decorators.Decorator):
    """Base for decorators that re-run their child until a count is reached.

    Every run the child finishes counts against ``max_runs``; runs that end in
    ``target_status`` also count towards ``target_count``. Reaching
    ``target_count`` reports SUCCESS, reaching ``max_runs`` first reports
    FAILURE, and anything else restarts the child (after the optional delay).
    It is private: the concrete decorators are the public surface.
    """

    def __init__(
        self,
        child: py_trees.behaviour.Behaviour,
        name: str,
        target_status: py_trees.common.Status,
        target_count: int,
        max_runs: int,
        delay: float | Delay,
        *,
        clock: Clock | None = None,
    ):
        super().__init__(name=name, child=child)
        self._target_status = target_status
        self._target_count = target_count
        self._max_runs = max_runs
        self._delay = as_delay(delay)
        self._clock = clock if clock is not None else default_clock()
        self._attempts = 0
        self._hits = 0
        self._waiting = False
        self._wait_start: float | None = None
        self._wait_t = 0.0

    def initialise(self) -> None:
        self._attempts = 0
        self._hits = 0
        self._waiting = False
        self._wait_start = None
        self._wait_t = 0.0

    def tick(self):
        if self._waiting and self._wait_start is not None:
            elapsed = self._clock.time() - self._wait_start
            if elapsed < self._wait_t:
                self.status = py_trees.common.Status.RUNNING
                yield self
                return
            else:
                self._waiting = False
                self.decorated.stop(py_trees.common.Status.INVALID)
        yield from super().tick()

    def update(self) -> py_trees.common.Status:
        if self.decorated.status == py_trees.common.Status.RUNNING:
            return py_trees.common.Status.RUNNING
        self._attempts += 1
        if self.decorated.status == self._target_status:
            self._hits += 1
        logger.debug(
            "%s: run %d/%d ended %s (%d/%d %s)",
            self.name,
            self._attempts,
            self._max_runs,
            self.decorated.status.name,
            self._hits,
            self._target_count,
            self._target_status.name,
        )
        if self._hits == self._target_count:
            return py_trees.common.Status.SUCCESS
        elif self._attempts == self._max_runs:
            return py_trees.common.Status.FAILURE
        wait = self._delay.sample(self._attempts)
        if wait > 0.0:
            logger.debug("%s: waiting %.3f s before the next run", self.name, wait)
            self._waiting = True
            self._wait_start = self._clock.time()
            self._wait_t = wait
        else:
            self.decorated.stop(py_trees.common.Status.INVALID)
        return py_trees.common.Status.RUNNING


class Retry(_RunUntilCount):
    """
    Retries a child behavior on FAILURE up to ``max_attempts`` times.

    Returns SUCCESS if the child ever succeeds, FAILURE once all attempts
    are exhausted.  Stays RUNNING between attempts (and during the optional
    delay between retries), so a retry cycle spans several ticks rather than
    blocking inside one.

    The attempt counter resets in ``initialise()``, so each fresh entry into
    this decorator gets a full budget of ``max_attempts``.

    Args:
        child (Behaviour): The child behavior to retry.
        name (str): Name of this decorator.
        max_attempts (int): Maximum number of times to attempt the child.
            Must be at least 1.
        delay (float | Delay): Wait between retry attempts: seconds, or a
            :class:`~py_branches.delay.Delay` sampled before each retry.
            A number must be non-negative. Default 0.0.
        clock (Clock): Time source for the inter-attempt delay, keyword-only.
            Defaults to the real clock; pass a
            :class:`py_branches.clock.ManualClock` to control it in tests.

    Raises:
        ValueError: If ``max_attempts`` is less than 1, or ``delay`` is a
            negative number.

    Example:
        .. testcode::

            child = py_trees.behaviours.Failure(name="Flaky")
            # Try up to 3 times; fails permanently after 3 failures.
            retry = Retry(child, name="Retry", max_attempts=3)

            child = py_trees.behaviours.Failure(name="Flaky")
            # Try up to 3 times with 1 second between each attempt.
            retry = Retry(child, name="RetryWithDelay", max_attempts=3, delay=1.0)

            from py_branches.delay import DelayExponentialBackoff

            child = py_trees.behaviours.Failure(name="Flaky")
            # Try up to 5 times, waiting 0.5, 1, 2 and 4 seconds between them.
            retry = Retry(
                child,
                name="RetryWithBackoff",
                max_attempts=5,
                delay=DelayExponentialBackoff(0.5),
            )
    """

    def __init__(
        self,
        child: py_trees.behaviour.Behaviour,
        name: str,
        max_attempts: int,
        delay: float | Delay = 0.0,
        *,
        clock: Clock | None = None,
    ):
        if max_attempts < 1:
            raise ValueError(f"max_attempts({max_attempts}) must be greater than 0.")
        super().__init__(
            child,
            name,
            py_trees.common.Status.SUCCESS,
            1,
            max_attempts,
            delay,
            clock=clock,
        )


class RunUntilFailed(_RunUntilCount):
    """
    Re-runs a child behavior on SUCCESS until it fails, up to ``max_runs`` times.

    Returns SUCCESS as soon as the child fails, since a FAILURE is how the
    child signals that the loop is done. Returns FAILURE if the child succeeds
    ``max_runs`` times without failing, because the loop never reached its
    exit condition. Stays RUNNING between runs (and during the optional delay
    between them), so the loop spans several ticks rather than blocking inside
    one.

    The run counter resets in ``initialise()``, so each fresh entry into this
    decorator gets a full budget of ``max_runs``.

    Args:
        child (Behaviour): The child behavior to repeat.
        name (str): Name of this decorator.
        max_runs (int): Maximum number of times to run the child. Must be at
            least 1.
        delay (float | Delay): Wait between runs: seconds, or a
            :class:`~py_branches.delay.Delay` sampled before each re-run.
            A number must be non-negative. Default 0.0.
        clock (Clock): Time source for the inter-run delay, keyword-only.
            Defaults to the real clock; pass a
            :class:`py_branches.clock.ManualClock` to control it in tests.

    Raises:
        ValueError: If ``max_runs`` is less than 1, or ``delay`` is a negative
            number.

    Example:
        .. testcode::

            child = py_trees.behaviours.Success(name="ProcessNextItem")
            # Process items until the child fails (queue empty), at most 100 runs.
            drain = RunUntilFailed(child, name="DrainQueue", max_runs=100)

            child = py_trees.behaviours.Success(name="ProcessNextItem")
            # As above, waiting half a second between runs.
            drain = RunUntilFailed(
                child, name="DrainQueueSlowly", max_runs=100, delay=0.5
            )
    """

    def __init__(
        self,
        child: py_trees.behaviour.Behaviour,
        name: str,
        max_runs: int,
        delay: float | Delay = 0.0,
        *,
        clock: Clock | None = None,
    ):
        if max_runs < 1:
            raise ValueError(f"max_runs({max_runs}) must be greater than 0.")
        super().__init__(
            child,
            name,
            py_trees.common.Status.FAILURE,
            1,
            max_runs,
            delay,
            clock=clock,
        )


class RunUntilXSuccesses(_RunUntilCount):
    """
    Re-runs a child behavior until it has succeeded ``num_successes`` times.

    Every run the child finishes, SUCCESS or FAILURE, counts against
    ``max_runs``. Successes are counted in total, so a FAILURE uses up a run
    without resetting the success count. Returns SUCCESS on the
    ``num_successes``-th success, and FAILURE once ``max_runs`` runs have
    finished without reaching it. There is no early exit: the child keeps
    running until the cap even after the target has become unreachable. Stays
    RUNNING between runs (and during the optional delay between them), so the
    loop spans several ticks rather than blocking inside one.

    Both counters reset in ``initialise()``, so each fresh entry into this
    decorator starts from zero successes with a full budget of ``max_runs``.
    With ``num_successes=1`` it behaves exactly like :class:`Retry`.

    Args:
        child (Behaviour): The child behavior to repeat.
        name (str): Name of this decorator.
        num_successes (int): Number of successes needed. Must be at least 1.
        max_runs (int): Maximum number of times to run the child. Must be at
            least ``num_successes``.
        delay (float | Delay): Wait between runs: seconds, or a
            :class:`~py_branches.delay.Delay` sampled before each re-run.
            A number must be non-negative. Default 0.0.
        clock (Clock): Time source for the inter-run delay, keyword-only.
            Defaults to the real clock; pass a
            :class:`py_branches.clock.ManualClock` to control it in tests.

    Raises:
        ValueError: If ``num_successes`` is less than 1, ``max_runs`` is less
            than ``num_successes``, or ``delay`` is a negative number.

    Example:
        .. testcode::

            child = py_trees.behaviours.Success(name="TakeSample")
            # Collect 3 good samples, giving up after 10 runs.
            collect = RunUntilXSuccesses(
                child, name="CollectSamples", num_successes=3, max_runs=10
            )

            child = py_trees.behaviours.Success(name="TakeSample")
            # As above, waiting half a second between runs.
            collect = RunUntilXSuccesses(
                child,
                name="CollectSamplesSlowly",
                num_successes=3,
                max_runs=10,
                delay=0.5,
            )
    """

    def __init__(
        self,
        child: py_trees.behaviour.Behaviour,
        name: str,
        num_successes: int,
        max_runs: int,
        delay: float | Delay = 0.0,
        *,
        clock: Clock | None = None,
    ):
        if num_successes < 1:
            raise ValueError(f"num_successes({num_successes}) must be greater than 0.")
        if max_runs < num_successes:
            raise ValueError(
                f"max_runs({max_runs}) must be at least num_successes({num_successes})."
            )
        super().__init__(
            child,
            name,
            py_trees.common.Status.SUCCESS,
            num_successes,
            max_runs,
            delay,
            clock=clock,
        )
