#!/usr/bin/env python3
import time
import py_trees


class Retry(py_trees.decorators.Decorator):
    '''
    Retries a child behavior on FAILURE up to max_attempts times.

    Returns SUCCESS if the child ever succeeds, FAILURE once all attempts
    are exhausted.  Stays RUNNING between attempts (and during optional
    delay between retries).

    Args:
        child (Behaviour): The child behavior to retry.
        name (str): Name of this decorator.
        max_attempts (int): Maximum number of times to attempt the child.
        delay (float): Seconds to wait between retry attempts. Default 0.0.

    Example:
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
        assert max_attempts > 0, \
            f'max_attempts({max_attempts}) must be greater than 0.'
        assert delay >= 0.0, \
            f'delay({delay}) must be non-negative.'
        super(Retry, self).__init__(name=name, child=child)
        self._max_attempts = max_attempts
        self._delay = delay
        self._attempts = 0
        self._waiting = False
        self._wait_start = None

    def initialise(self) -> None:
        self._attempts = 0
        self._waiting = False
        self._wait_start = None

    def tick(self):
        if self._waiting:
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
