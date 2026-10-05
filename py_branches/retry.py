#!/usr/bin/env python3
"""Re-run a child behavior, optionally with a delay between runs.

Two decorators that differ only in which outcome means "go again":
:class:`Retry` re-runs a child that fails, for flaky operations that are worth
attempting more than once; :class:`RunUntilFailed` re-runs a child that
succeeds, for work that should repeat until the child reports it is done.
"""

import logging

import py_trees

from .clock import Clock
from .clock import default_clock

logger = logging.getLogger(__name__)


class _RepeatOnStatus(py_trees.decorators.Decorator):
    """Base for decorators that re-run their child on one terminal status.

    Subclasses set :attr:`_repeat_on`. When the child finishes with that
    status the run is counted and, while under the limit, the child is
    restarted (after the optional delay); once the limit is reached the
    decorator reports FAILURE. The child finishing with the other terminal
    status ends the loop with SUCCESS. It is private: the concrete decorators
    are the public surface.
    """

    _repeat_on: py_trees.common.Status

    def __init__(
        self,
        child: py_trees.behaviour.Behaviour,
        name: str,
        limit: int,
        delay: float,
        *,
        clock: Clock | None = None,
    ):
        super().__init__(name=name, child=child)
        self._limit = limit
        self._delay = delay
        self._clock = clock if clock is not None else default_clock()
        self._attempts = 0
        self._waiting = False
        self._wait_start: float | None = None

    def initialise(self) -> None:
        self._attempts = 0
        self._waiting = False
        self._wait_start = None

    def tick(self):
        if self._waiting and self._wait_start is not None:
            elapsed = self._clock.time() - self._wait_start
            if elapsed < self._delay:
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
        elif self.decorated.status != self._repeat_on:
            return py_trees.common.Status.SUCCESS
        self._attempts += 1
        logger.debug(
            "%s: run %d/%d ended %s",
            self.name,
            self._attempts,
            self._limit,
            self._repeat_on.name,
        )
        if self._attempts < self._limit:
            if self._delay > 0.0:
                self._waiting = True
                self._wait_start = self._clock.time()
            else:
                self.decorated.stop(py_trees.common.Status.INVALID)
            return py_trees.common.Status.RUNNING
        else:
            return py_trees.common.Status.FAILURE


class Retry(_RepeatOnStatus):
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
        delay (float): Seconds to wait between retry attempts. Must be
            non-negative. Default 0.0.
        clock (Clock): Time source for the inter-attempt delay, keyword-only.
            Defaults to the real clock; pass a
            :class:`py_branches.clock.ManualClock` to control it in tests.

    Raises:
        ValueError: If ``max_attempts`` is less than 1, or ``delay`` is
            negative.

    Example:
        .. testcode::

            child = py_trees.behaviours.Failure(name="Flaky")
            # Try up to 3 times; fails permanently after 3 failures.
            retry = Retry(child, name="Retry", max_attempts=3)

            child = py_trees.behaviours.Failure(name="Flaky")
            # Try up to 3 times with 1 second between each attempt.
            retry = Retry(child, name="RetryWithDelay", max_attempts=3, delay=1.0)
    """

    _repeat_on = py_trees.common.Status.FAILURE

    def __init__(
        self,
        child: py_trees.behaviour.Behaviour,
        name: str,
        max_attempts: int,
        delay: float = 0.0,
        *,
        clock: Clock | None = None,
    ):
        if max_attempts < 1:
            raise ValueError(f"max_attempts({max_attempts}) must be greater than 0.")
        if delay < 0.0:
            raise ValueError(f"delay({delay}) must be non-negative.")
        super().__init__(child, name, max_attempts, delay, clock=clock)


class RunUntilFailed(_RepeatOnStatus):
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
        delay (float): Seconds to wait between runs. Must be non-negative.
            Default 0.0.
        clock (Clock): Time source for the inter-run delay, keyword-only.
            Defaults to the real clock; pass a
            :class:`py_branches.clock.ManualClock` to control it in tests.

    Raises:
        ValueError: If ``max_runs`` is less than 1, or ``delay`` is negative.

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

    _repeat_on = py_trees.common.Status.SUCCESS

    def __init__(
        self,
        child: py_trees.behaviour.Behaviour,
        name: str,
        max_runs: int,
        delay: float = 0.0,
        *,
        clock: Clock | None = None,
    ):
        if max_runs < 1:
            raise ValueError(f"max_runs({max_runs}) must be greater than 0.")
        if delay < 0.0:
            raise ValueError(f"delay({delay}) must be non-negative.")
        super().__init__(child, name, max_runs, delay, clock=clock)
