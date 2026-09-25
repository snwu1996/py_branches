#!/usr/bin/env python3
"""Retry a failing child behavior, optionally with a delay.

A single decorator, :class:`Retry`, for flaky operations that are worth
attempting more than once.
"""
import time
import py_trees


class Retry(py_trees.decorators.Decorator):
    '''
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

    Raises:
        ValueError: If ``max_attempts`` is less than 1, or ``delay`` is
            negative.

    Example:
        .. code-block:: python

            child = py_trees.behaviours.Failure(name="Flaky")
            # Try up to 3 times; fails permanently after 3 failures.
            retry = Retry(child, name="Retry", max_attempts=3)

            child = py_trees.behaviours.Failure(name="Flaky")
            # Try up to 3 times with 1 second between each attempt.
            retry = Retry(child, name="RetryWithDelay", max_attempts=3, delay=1.0)
    '''
    def __init__(self, child: py_trees.behaviour.Behaviour,
                       name: str,
                       max_attempts: int,
                       delay: float = 0.0):
        if max_attempts < 1:
            raise ValueError(f'max_attempts({max_attempts}) must be greater than 0.')
        if delay < 0.0:
            raise ValueError(f'delay({delay}) must be non-negative.')
        super(Retry, self).__init__(name=name, child=child)
        self._max_attempts = max_attempts
        self._delay = delay
        self._attempts = 0
        self._waiting = False
        self._wait_start: float | None = None

    def initialise(self) -> None:
        self._attempts = 0
        self._waiting = False
        self._wait_start = None

    def tick(self):
        if self._waiting and self._wait_start is not None:
            elapsed = time.time() - self._wait_start
            if elapsed < self._delay:
                self.status = py_trees.common.Status.RUNNING
                yield self
                return
            else:
                self._waiting = False
                self.decorated.stop(py_trees.common.Status.INVALID)
        for node in super().tick():
            yield node

    def update(self) -> py_trees.common.Status:
        if self.decorated.status == py_trees.common.Status.SUCCESS:
            return py_trees.common.Status.SUCCESS
        elif self.decorated.status == py_trees.common.Status.RUNNING:
            return py_trees.common.Status.RUNNING
        else:  # FAILURE
            self._attempts += 1
            if self._attempts < self._max_attempts:
                if self._delay > 0.0:
                    self._waiting = True
                    self._wait_start = time.time()
                else:
                    self.decorated.stop(py_trees.common.Status.INVALID)
                return py_trees.common.Status.RUNNING
            else:
                return py_trees.common.Status.FAILURE
