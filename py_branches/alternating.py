#!/usr/bin/env python3
"""Control which behaviors run, and when.

Three decorators and a factory, covering the common shapes of "not every tick":

* :class:`ActivateBehavior` — an on/off switch a caller flips from outside the
  tree.
* :func:`run_alternating` — cycle through several behaviors, each for a fixed
  run of consecutive ticks.
* :class:`RunEveryX` — run the child once every X ticks, X re-drawn from a
  range after each execution.
* :class:`RunEveryRange` — run the child during a fixed window of a
  fixed-length cycle.

Each of the decorators takes a ``success_if_skip`` flag. It decides what a
skipped tick reports: FAILURE by default, which a parent Selector reads as
"try the next child", or SUCCESS, which makes the skip invisible to a parent
Sequence. Which one you want depends entirely on the composite above it.
"""
import py_trees
import random
from typing import List
from typing import Tuple


class ActivateBehavior(py_trees.decorators.Decorator):
    '''
    Enables activation of a behavior from an external source as long as it has a handle to
    this decorator.

    While deactivated the child is not ticked at all — neither its
    ``initialise`` nor its ``update`` runs — and this decorator reports FAILURE,
    or SUCCESS if ``success_if_skip`` is set. Flip the :attr:`activate` property
    to switch the child on and off from outside the tree.

    This is the mechanism behind :func:`run_alternating`, and it is equally
    usable on its own to gate a branch from application code.

    Args:
        child (Behaviour): The child behavior that is being activated or not
            activated.
        name (str): Name of this behavior.
        activate (bool): Whether or not to start this behavior activated or not.
        success_if_skip (bool): Return SUCCESS instead of FAILURE while
            deactivated. Default False.

    Example:
        .. code-block:: python

            child = py_trees.behaviours.Success(name="Child")
            gate = ActivateBehavior(child, name="Gate", activate=True,
                                    success_if_skip=True)

            gate.activate = False  # child is skipped, gate returns SUCCESS
            gate.activate = True   # child runs normally
    '''
    def __init__(self, child: py_trees.behaviour.Behaviour,
                       name: str,
                       activate: bool,
                       success_if_skip:bool=False):
        super(ActivateBehavior, self).__init__(name=name, child=child)
        self._activate = activate
        self._success_if_skip = success_if_skip

    @property
    def activate(self):
        return self._activate
    
    @activate.setter
    def activate(self, activate: bool):
        self._activate = activate

    def tick(self):
        if not self._activate:
            if self._success_if_skip:
                self.stop(py_trees.common.Status.SUCCESS)
            else:
                self.stop(py_trees.common.Status.FAILURE)
            yield self
        else:
            for node in super().tick():
                yield node

    def update(self) -> py_trees.common.Status:
        return self.decorated.status

class _RunAlternatingHelper(py_trees.behaviour.Behaviour):
    '''Bookkeeper that advances which ActivateBehavior is enabled.

    Always returns FAILURE so the enclosing Selector falls through to the
    wrapped behaviors after this one has updated the rotation.
    '''
    def __init__(self, name: str, activatable_behaviors: List[ActivateBehavior], counts: List[int]):
        self._counts = counts
        self._current_behavior_idx = 0
        self._current_behavior_num_consecutive_runs = 0
        self._activatable_behaviors = activatable_behaviors
        self._activatable_behaviors[0].activate = True

        super().__init__(name)

    def initialise(self) -> None:
        if self._current_behavior_num_consecutive_runs >= self._counts[self._current_behavior_idx]:
            self._activatable_behaviors[self._current_behavior_idx].activate = False
            self._current_behavior_idx = (self._current_behavior_idx + 1) % len(self._counts)
            self._activatable_behaviors[self._current_behavior_idx].activate = True
            self._current_behavior_num_consecutive_runs = 0

        self._current_behavior_num_consecutive_runs += 1

    def update(self) -> py_trees.common.Status:
        return py_trees.common.Status.FAILURE

def run_alternating(name: str, behaviors: List[py_trees.behaviour.Behaviour], counts: List[int]):
    '''
    Build a Selector that cycles through behaviors, each for a fixed run of ticks.

    The returned Selector holds a private bookkeeping behavior followed by every
    entry of ``behaviors``, each wrapped in an :class:`ActivateBehavior`. Exactly
    one wrapper is active at a time; the bookkeeper advances to the next once the
    current one has run its allotted number of ticks, and wraps around at the
    end of the list.

    Args:
        name (str): Name of the behavior.
        behaviors (List[Behaviour]): List of all the behaviors to run
            alternating.
        counts (List[int]): A list of how many times the corresponding behavior
            ought to be ran. Must be the same length as ``behaviors`` and
            contain no zeros.

    Returns:
        py_trees.composites.Selector: The alternating subtree, ready to add to
        a parent.

    Raises:
        ValueError: If ``counts`` contains a 0, or the two lists differ in
            length.

    Example:
        If ``behaviors`` is ``[behavior_a, behavior_b, behavior_c]`` and
        ``counts`` is ``[3, 2, 4]`` then behavior_a will run 3 times in a row,
        behavior_b will run 2 times in a row, and behavior_c will run 4 times in
        a row before repeating::

            A, A, A, B, B, C, C, C, C, A, A, A, B, B, ...

        .. code-block:: python

            a = py_trees.behaviours.Success(name="A")
            b = py_trees.behaviours.Success(name="B")
            c = py_trees.behaviours.Success(name="C")

            root = run_alternating("Cycle", [a, b, c], [3, 2, 4])
    '''
    if 0 in counts:
        raise ValueError(f'counts({counts}) can not have 0 in the list.')
    if len(counts) != len(behaviors):
        raise ValueError('len(counts) != len(behaviors), two lists must be of same length.')

    alternating_behaviors = []
    for idx, behavior in enumerate(behaviors):
        activate_decorator = ActivateBehavior(behavior, f'activate_{behavior.name}', False)
        alternating_behaviors.append(activate_decorator)
    run_alternating_helper = _RunAlternatingHelper(f'{name}_helper', alternating_behaviors, counts)

    children = []
    children.append(run_alternating_helper)
    children += alternating_behaviors

    run_alternating_selector = py_trees.composites.Selector(name, False, children)
    return run_alternating_selector

class RunEveryRange(py_trees.decorators.Decorator):
    '''
    Run the child only during a window of iterations within a fixed-length cycle.

    An internal counter runs from 1 to ``max_range`` and then wraps back to 1.
    The child is ticked while the counter falls inside ``run_range`` inclusive,
    and skipped otherwise. Unlike :class:`RunEveryX` the pattern is fixed, so
    the child runs on the same iterations of every cycle.

    On skipped ticks the child is not ticked and this decorator returns FAILURE,
    or SUCCESS if ``success_if_skip`` is set.

    Args:
        child (Behaviour): The child behavior that is being activated or not
            activated.
        name (str): Name of this behavior.
        max_range (int): Number of ticks in a cycle, after which the counter
            resets to 1.
        run_range (Tuple[int, int]): Inclusive range of iterations during which
            the child executes.
        success_if_skip (bool): Return SUCCESS instead of FAILURE on a skipped
            tick. Default False.

    Raises:
        ValueError: If ``run_range`` is reversed, starts below 1, or ends above
            ``max_range``.

    Example:
        E marks a tick that executes the child, S a tick that skips it. If
        ``max_range`` and ``run_range`` are::

            6 and (4,6) then the child will run on the 4th, 5th, and 6th cycle.
                S, S, S, E, E, E, S, S, S, E, E, E, S, S, S, ...
            6 and (2,4) then the child will run on the 2nd, 3rd, and 4th cycle.
                S, E, E, E, S, S, S, E, E, E, S, S, S, E, E, ...

        .. code-block:: python

            child = py_trees.behaviours.Success(name="Child")

            # Run on iterations 4, 5 and 6 of every 10-tick cycle.
            windowed = RunEveryRange(child, name="Window", max_range=10, run_range=(4, 6))
    '''
    def __init__(self, child: py_trees.behaviour.Behaviour,
                       name: str,
                       max_range: int,
                       run_range: Tuple[int, int],
                       success_if_skip: bool = False):
        if run_range[0] > run_range[1]:
            raise ValueError('run_range must be a tuple with (smaller_number, bigger_number)')
        if run_range[0] < 1:
            raise ValueError('Lower run range must be greater or equal to 1')
        if run_range[1] > max_range:
            raise ValueError(f'Upper run range must be lower or equal to {max_range}')

        super(RunEveryRange, self).__init__(name=name, child=child)
        self._max_range = max_range
        self._run_range = run_range
        self._success_if_skip = success_if_skip
        self._iteration = 1

    def tick(self):
        if self._run_range[0] <= self._iteration <= self._run_range[1]:
            for node in super().tick():
                yield node
        else:
            if self._success_if_skip:
                self.stop(py_trees.common.Status.SUCCESS)
            else:
                self.stop(py_trees.common.Status.FAILURE)
            yield self

    def terminate(self, new_status: py_trees.common.Status) -> None:
        self._iteration += 1
        if self._iteration > self._max_range:
            self._iteration = 1

    def update(self) -> py_trees.common.Status:
        return self.decorated.status

class RunEveryX(py_trees.decorators.Decorator):
    '''
    Run the child once every X ticks, where X is re-drawn after each execution.

    X is sampled from ``every_x_range`` inclusive. A fixed range like ``(5, 5)``
    gives a strict period; a wider range gives an irregular one, re-rolled every
    time the child executes, which is useful for behavior that should look
    unscheduled.

    On skipped ticks the child is not ticked and this decorator returns FAILURE,
    or SUCCESS if ``success_if_skip`` is set.

    Args:
        child (Behaviour): The child behavior that is being activated or not
            activated.
        name (str): Name of this behavior.
        every_x_range (Tuple[int, int]): Inclusive ``(min, max)`` bounds on the
            number of ticks per cycle. The lower bound must be at least 1.
        success_if_skip (bool): Return SUCCESS instead of FAILURE on a skipped
            tick. Default False.

    Raises:
        ValueError: If the bounds are reversed, or the lower bound is below 1.

    Example:
        E marks a tick that executes the child, S a tick that skips it. If
        ``every_x_range`` is::

            (1,1) then the child behavior will run every cycle.
                E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, ...
            (5,5) then the child behavior will run every 5th cycle.
                S, S, S, S, E, S, S, S, S, E, S, S, S, S, E, ...
            (1,5) then the child behavior will run randomly between every
            cycle or every 5th cycle. Changes every time the child gets
            executed.
                S, S, E, S, S, S, S, E, E, S, S, S, E, S, S, ...
                The execute cycle above goes:
                    3: S, S, E
                    5: S, S, S, S, E
                    1: E
                    4: S, S, S, E

        .. code-block:: python

            child = py_trees.behaviours.Success(name="Child")

            # Run exactly every 5th tick.
            every_5 = RunEveryX(child, name="Every5", every_x_range=(5, 5))

            # Run at a random interval between 1 and 5 ticks.
            varied = RunEveryX(child, name="Varied", every_x_range=(1, 5))
    '''
    def __init__(self, child: py_trees.behaviour.Behaviour,
                       name: str,
                       every_x_range: Tuple[int, int],
                       success_if_skip:bool=False):
        if every_x_range[0] > every_x_range[1]:
            raise ValueError('every_x_range must be a tuple with (smaller_number, bigger_number)')
        if every_x_range[0] < 1:
            raise ValueError('Can not have range be lower than 1.')

        super(RunEveryX, self).__init__(name=name, child=child)
        self._every_x_range = every_x_range
        self._cycles_remaining = random.randint(*self._every_x_range)-1
        self._success_if_skip = success_if_skip

    def initialise(self):
        self._cycles_remaining = random.randint(*self._every_x_range)-1

    def tick(self):
        if self._cycles_remaining > 0:
            self._cycles_remaining -= 1
            if self._success_if_skip:
                self.stop(py_trees.common.Status.SUCCESS)
            else:
                self.stop(py_trees.common.Status.FAILURE)
            yield self
        else:
            for node in super().tick():
                yield node

    def update(self):
        return self.decorated.status
