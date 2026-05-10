"""Visitors for py_trees behavior trees."""

import logging
from typing import Dict, Optional

import py_trees


class StatusTransitionVisitor(py_trees.visitors.VisitorBase):
    """Print a behavior's status only when it transitions.

    Tracks the last-seen status per behavior id and emits a line when the
    status changes. Quiet by default for nodes that stay RUNNING across ticks.
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
        nid = str(behaviour.id)
        prev = self._last.get(nid)
        curr = behaviour.status
        if curr == prev:
            return
        self._last[nid] = curr
        msg = f'[{behaviour.name}] {curr.name}'
        if self._logger is not None:
            self._logger.log(self._level, msg)
        else:
            print(msg, flush=True)


__all__ = ['StatusTransitionVisitor']
