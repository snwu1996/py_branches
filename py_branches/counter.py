#!/usr/bin/env python3
import py_trees


class Counter(py_trees.decorators.Decorator):
    '''
    Runs a child behavior exactly num_runs times (total completions), then
    permanently returns completion_status without ever running the child again.

    A "completion" is any tick where the child returns SUCCESS or FAILURE.
    RUNNING ticks do not count — the counter waits for the child to finish each
    run before counting it.

    The run count and done flag persist across tree re-entries (i.e. they are
    NOT reset by initialise()).  This makes Counter suitable for one-time
    initialization sequences.  To reset and re-count, call reset() explicitly.

    Args:
        child (Behaviour): The child behavior to count.
        name (str): Name of this decorator.
        num_runs (int): Total number of child completions to allow.
        completion_status (Status): Status returned permanently once num_runs
            completions have occurred.  Default SUCCESS.

    Example:
        child = InitializationBehavior(name="Init")
        # Run Init exactly once; after it completes, always return SUCCESS.
        counted = Counter(child, name="RunOnce", num_runs=1)

        child = CalibrateStep(name="Calibrate")
        # Run calibration exactly 3 times, then always return SUCCESS.
        counted = Counter(child, name="Calibrate3x", num_runs=3)
    '''
    def __init__(self, child: py_trees.behaviour.Behaviour,
                       name: str,
                       num_runs: int,
                       completion_status: py_trees.common.Status = py_trees.common.Status.SUCCESS):
        assert num_runs > 0, \
            f'num_runs({num_runs}) must be greater than 0.'
        super(Counter, self).__init__(name=name, child=child)
        self._num_runs = num_runs
        self._completion_status = completion_status
        self._runs_completed = 0
        self._done = False

    def reset(self) -> None:
        '''Reset the run count so the child will be run num_runs times again.'''
        self._runs_completed = 0
        self._done = False

    def tick(self):
        if self._done:
            self.stop(self._completion_status)
            yield self
        else:
            for node in super().tick():
                yield node

    def update(self) -> py_trees.common.Status:
        status = self.decorated.status
        if status == py_trees.common.Status.RUNNING:
            return py_trees.common.Status.RUNNING

        # Child completed this tick (SUCCESS or FAILURE).
        self._runs_completed += 1
        if self._runs_completed >= self._num_runs:
            self._done = True
            self.decorated.stop(py_trees.common.Status.INVALID)
            return self._completion_status

        # More runs remain — reset child so it re-runs next tick.
        self.decorated.stop(py_trees.common.Status.INVALID)
        return py_trees.common.Status.RUNNING
