"""Visitors for py_trees behavior trees."""

import logging
import time
import uuid
from typing import Dict, Optional

import py_trees


_ANSI_RESET = '\033[0m'
_ANSI_BY_STATUS = {
    py_trees.common.Status.SUCCESS: '\033[32m',  # green
    py_trees.common.Status.RUNNING: '\033[37m',  # white
    py_trees.common.Status.FAILURE: '\033[31m',  # red
}


class StatusTransitionVisitor(py_trees.visitors.VisitorBase):
    """Print a behavior's status only when it transitions.

    Tracks the last-seen status per behavior id and emits a line when the
    status changes. Skips INVALID. Quiet for nodes that stay RUNNING across ticks.
    """

    def __init__(
        self,
        logger: Optional[logging.Logger] = None,
        level: int = logging.INFO,
    ) -> None:
        super().__init__(full=True)
        self._last: Dict[str, py_trees.common.Status] = {}
        self._logger = logger
        self._level = level

    def run(self, behaviour: py_trees.behaviour.Behaviour) -> None:
        if behaviour.children:
            return
        nid = str(behaviour.id)
        prev = self._last.get(nid)
        curr = behaviour.status
        if curr == prev:
            return
        self._last[nid] = curr
        if curr == py_trees.common.Status.INVALID:
            return
        color = _ANSI_BY_STATUS.get(curr, '')
        msg = f'{color}[{behaviour.name}] {curr.name}{_ANSI_RESET}'
        if self._logger is not None:
            self._logger.log(self._level, msg)
        else:
            print(msg, flush=True)


class TimerVisitor(py_trees.visitors.VisitorBase):
    """Record wall-clock time each behaviour spends in the RUNNING state.

    Measures the duration from when a behaviour first ticks RUNNING until it
    transitions out (SUCCESS, FAILURE, or INVALID). Keyed by behaviour id so
    duplicate names in a tree are handled correctly.
    """

    def __init__(self) -> None:
        super().__init__(full=False)
        self._running_starts: Dict[uuid.UUID, float] = {}
        self.durations: Dict[uuid.UUID, float] = {}
        self.behaviour_names: Dict[uuid.UUID, str] = {}

    def run(self, behaviour: py_trees.behaviour.Behaviour) -> None:
        self.behaviour_names[behaviour.id] = behaviour.name
        is_running = behaviour.status == py_trees.common.Status.RUNNING

        if is_running and behaviour.id not in self._running_starts:
            self._running_starts[behaviour.id] = time.time()
        elif not is_running and behaviour.id in self._running_starts:
            start = self._running_starts.pop(behaviour.id)
            self.durations[behaviour.id] = time.time() - start

    def get_duration(self, behaviour: py_trees.behaviour.Behaviour) -> Optional[float]:
        """Return the last completed RUNNING duration, or current elapsed if still running."""
        if behaviour.id in self._running_starts:
            return time.time() - self._running_starts[behaviour.id]
        return self.durations.get(behaviour.id)


__all__ = ['StatusTransitionVisitor', 'TimerVisitor']
