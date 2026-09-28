#!/usr/bin/env python3
"""Rate-limit how often a child behavior may run.

A single decorator, :class:`Cooldown`, which enforces a minimum gap between
completions of its child.
"""

import py_trees

from .clock import Clock
from .clock import default_clock


class Cooldown(py_trees.decorators.Decorator):
    """
    Prevents a child from running again until a cooldown period has elapsed
    after its last completion.

    The child runs normally on the first tick.  Once it completes (SUCCESS or
    FAILURE), a cooldown timer starts.  During the cooldown, the child is not
    ticked and this decorator returns FAILURE (or SUCCESS if
    ``success_if_cooling=True``).  After the cooldown expires the child may
    run again.

    A child that stays RUNNING is never subject to the cooldown — the timer
    only starts once the child actually finishes.

    The cooldown timer is wall-clock based and is not reset by re-entering the
    tree, so the gap holds across separate activations.

    Args:
        child (Behaviour): The child behavior to rate-limit.
        name (str): Name of this decorator.
        duration (float): Cooldown period in seconds after each completion.
            Must be positive.
        success_if_cooling (bool): Return SUCCESS instead of FAILURE while
            cooling down.  Default False.
        clock (Clock): Time source for the cooldown timer, keyword-only.
            Defaults to the real clock; pass a
            :class:`py_branches.clock.ManualClock` to control it in tests.

    Raises:
        ValueError: If ``duration`` is not positive.

    Example:
        .. testcode::

            child = py_trees.behaviours.Success(name="Expensive")
            # Run child freely, but enforce a 5-second gap between executions.
            cooled = Cooldown(child, name="Cooldown", duration=5.0)
    """

    def __init__(
        self,
        child: py_trees.behaviour.Behaviour,
        name: str,
        duration: float,
        success_if_cooling: bool = False,
        *,
        clock: Clock | None = None,
    ):
        if duration <= 0.0:
            raise ValueError(f"duration({duration}) must be positive.")
        super().__init__(name=name, child=child)
        self._duration = duration
        self._success_if_cooling = success_if_cooling
        self._clock = clock if clock is not None else default_clock()
        self._cooling = False
        self._cool_start: float | None = None

    def tick(self):
        if self._cooling and self._cool_start is not None:
            elapsed = self._clock.time() - self._cool_start
            if elapsed < self._duration:
                if self._success_if_cooling:
                    self.stop(py_trees.common.Status.SUCCESS)
                else:
                    self.stop(py_trees.common.Status.FAILURE)
                yield self
                return
            else:
                self._cooling = False

        yield from super().tick()

    def update(self) -> py_trees.common.Status:
        status = self.decorated.status
        if status != py_trees.common.Status.RUNNING:
            self._cooling = True
            self._cool_start = self._clock.time()
        return status
