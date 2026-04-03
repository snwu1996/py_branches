#!/usr/bin/env python3
import time
import py_trees


class Timeout(py_trees.decorators.Decorator):
    '''
    Fails a child behavior if it stays RUNNING beyond the specified duration.

    - If the child returns SUCCESS or FAILURE before the timeout, that
      status is passed through unchanged.
    - If the child is still RUNNING when the timeout expires, the child is
      stopped and FAILURE is returned.

    Args:
        child (Behaviour): The child behavior to wrap with a timeout.
        name (str): Name of this decorator.
        duration (float): Maximum seconds the child may remain RUNNING.

    Example:
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
        self._start_time = None

    def initialise(self) -> None:
        self._start_time = time.time()

    def update(self) -> py_trees.common.Status:
        if self.decorated.status != py_trees.common.Status.RUNNING:
            return self.decorated.status

        elapsed = time.time() - self._start_time
        if elapsed >= self._duration:
            self.decorated.stop(py_trees.common.Status.INVALID)
            return py_trees.common.Status.FAILURE
        return py_trees.common.Status.RUNNING
