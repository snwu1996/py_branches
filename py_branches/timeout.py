#!/usr/bin/env python3
"""Bound how long a child behavior may stay RUNNING.

A single decorator, :class:`Timeout`, which converts an over-running child
into a FAILURE so a tree cannot stall indefinitely on one branch.
"""
import time
import py_trees


class Timeout(py_trees.decorators.Decorator):
    '''
    Fails a child behavior if it stays RUNNING beyond the specified duration.

    - If the child returns SUCCESS or FAILURE before the timeout, that
      status is passed through unchanged.
    - If the child is still RUNNING when the timeout expires, the child is
      stopped (set to INVALID) and FAILURE is returned.

    The clock starts in ``initialise()``, i.e. on each fresh entry. The
    duration therefore bounds one uninterrupted RUNNING stretch, not the
    total time the child has ever spent running.

    Args:
        child (Behaviour): The child behavior to wrap with a timeout.
        name (str): Name of this decorator.
        duration (float): Maximum seconds the child may remain RUNNING.
            Must be positive.

    Raises:
        ValueError: If ``duration`` is not positive.

    Example:
        .. code-block:: python

            child = LongRunningBehavior(name="Slow")
            # Fail if child does not complete within 5 seconds.
            guarded = Timeout(child, name="Timeout", duration=5.0)
    '''
    def __init__(self, child: py_trees.behaviour.Behaviour,
                       name: str,
                       duration: float):
        if duration <= 0.0:
            raise ValueError(f'duration({duration}) must be positive.')
        super(Timeout, self).__init__(name=name, child=child)
        self._duration = duration
        self._start_time: float | None = None

    def initialise(self) -> None:
        self._start_time = time.time()

    def update(self) -> py_trees.common.Status:
        if self.decorated.status != py_trees.common.Status.RUNNING:
            return self.decorated.status

        if self._start_time is None:
            # update() before initialise(): the clock has not started, so
            # nothing can have timed out yet.
            return py_trees.common.Status.RUNNING

        elapsed = time.time() - self._start_time
        if elapsed >= self._duration:
            self.decorated.stop(py_trees.common.Status.INVALID)
            return py_trees.common.Status.FAILURE
        return py_trees.common.Status.RUNNING
