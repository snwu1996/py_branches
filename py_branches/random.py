#!/usr/bin/env python3
"""Probabilistic execution and weighted selection.

:class:`RandomRun` runs its child only some of the time;
:class:`RandomDelay` runs it every time but after a random wait; and
:func:`random_selector` chooses one of several behaviors according to weights
you supply.

These compose with the rest of the library — wrapping a behavior in
:class:`RandomRun` before handing it to
:func:`py_branches.alternating.run_alternating`, for instance, makes a cycling
pattern that sometimes skips a step:

.. testcode::

    from py_branches.alternating import run_alternating
    from py_branches.random import RandomRun

    a = py_trees.behaviours.Success(name="A")
    b = py_trees.behaviours.Success(name="B")

    # B only runs half the time it is B's turn.
    b_maybe = RandomRun(b, name="MaybeB", probability=0.5, success_if_skip=True)
    root = run_alternating("AlternateWithRandom", [a, b_maybe], [3, 2])
"""

import py_trees
import random
import logging
import time
from typing import List


class RandomRun(py_trees.decorators.Decorator):
    '''
    Random chance of running the child of this decorator.

    A single draw decides whether the child runs for a whole execution. The
    first draw happens on the first tick; every later draw happens in
    ``terminate()``, so the outcome is already decided when an execution
    begins and is held for as long as the child stays RUNNING.

    When the draw says no, the child is not ticked at all and this decorator
    reports FAILURE, or SUCCESS if ``success_if_skip`` is set — the latter
    makes a skipped child transparent to a parent Sequence.

    Args:
        child (Behaviour): The behavior to wrap.
        name (str): Name of this decorator node.
        probability (float): Chance in ``[0.0, 1.0]`` that the child runs.
            0.0 never runs it, 1.0 always does.
        success_if_skip (bool): Return SUCCESS instead of FAILURE when the
            child is skipped. Default False.

    Raises:
        ValueError: If ``probability`` falls outside ``[0.0, 1.0]``.

    Example:
        .. testcode::

            child = py_trees.behaviours.Success(name="Child")

            # 70% chance the child runs; otherwise FAILURE.
            maybe = RandomRun(child, name="MaybeRun", probability=0.7)

            # 30% chance, and a skip looks like SUCCESS to the parent.
            sometimes = RandomRun(
                child, name="Sometimes", probability=0.3, success_if_skip=True
            )
    '''
    def __init__(self, child, name, probability: float, success_if_skip: bool = False):
        if not (0 <= probability <= 1.0):
            raise ValueError(f'Probability == {probability} but needs to be in range [0, 1.0]')
        super(RandomRun, self).__init__(name=name, child=child)
        self._probability = probability
        self._run = None  # rolled on first tick; terminate() handles all subsequent rolls
        self._success_if_skip = success_if_skip

    def tick(self):
        if self._run is None:
            self._run = random.random() <= self._probability
        if not self._run:
            for node in py_trees.behaviour.Behaviour.tick(self):
                yield node
        else:
            for node in super().tick():
                yield node

    def update(self):
        if self._run:
            return self.decorated.status
        else:
            if self._success_if_skip:
                return py_trees.common.Status.SUCCESS
            else:
                return py_trees.common.Status.FAILURE

    def terminate(self, new_status: py_trees.common.Status) -> None:
        self._run = random.random() <= self._probability

class RandomDelay(py_trees.decorators.Decorator):
    '''
    Waits a random duration before running the child on each fresh entry.

    On every fresh entry (i.e. when the decorator was not already RUNNING),
    a delay is sampled uniformly from ``[low, high]`` seconds.  The decorator
    stays RUNNING without ticking the child until the delay has elapsed, then
    passes through to the child normally.

    The delay is re-sampled on every new entry, so repeated executions each
    get independent jitter.  This is useful for desynchronising multiple
    agents that share the same tree structure.

    Args:
        child (Behaviour): The child behavior to delay.
        name (str): Name of this decorator.
        low (float): Minimum delay in seconds (>= 0).
        high (float): Maximum delay in seconds (>= low).

    Raises:
        ValueError: If ``low`` is negative, or greater than ``high``.

    Example:
        .. testcode::

            child = py_trees.behaviours.Success(name="Action")
            # Pause 0.5-2.0 seconds before running the child each time.
            delayed = RandomDelay(child, name="RandomDelay", low=0.5, high=2.0)
    '''
    def __init__(self, child: py_trees.behaviour.Behaviour,
                       name: str,
                       low: float,
                       high: float):
        if low < 0.0:
            raise ValueError(f'low({low}) must be >= 0.')
        if low > high:
            raise ValueError(f'low({low}) must be <= high({high}).')
        super(RandomDelay, self).__init__(name=name, child=child)
        self._low = low
        self._high = high
        self._delay = 0.0
        self._start_time: float | None = None
        self._waiting = False

    def tick(self):
        # Fresh entry: sample a new delay and start the timer.
        if self.status != py_trees.common.Status.RUNNING:
            self._delay = random.uniform(self._low, self._high)
            self._start_time = time.time()
            self._waiting = True

        if self._waiting and self._start_time is not None:
            if time.time() - self._start_time < self._delay:
                self.status = py_trees.common.Status.RUNNING
                yield self
                return
            self._waiting = False

        for node in super().tick():
            yield node

    def update(self) -> py_trees.common.Status:
        return self.decorated.status


def random_selector(name, behaviors: List[py_trees.behaviour.Behaviour], probabilities: List[float]):
    """Build a Selector that picks one child according to absolute weights.

    A plain py_trees Selector tries its children left to right and stops at the
    first SUCCESS. This wraps each behavior in a :class:`RandomRun` whose
    probability is the *conditional* probability needed for the child's
    *absolute* chance of running to match the weight you asked for.

    Given ``[0.2, 0.3, 0.5]``:

    * A is wrapped with probability ``0.2``.
    * B is wrapped with ``0.3 / 0.8 = 0.375``, conditional on A being skipped.
    * C would come out at ``0.5 / 0.5 = 1.0``, so it is added undecorated — by
      the time the selector reaches it, it must run.

    Over many ticks each behavior is therefore chosen with its intended
    frequency. List order still matters: earlier children are evaluated first,
    and the first one to succeed ends the tick.

    Args:
        name (str): Name of the root Selector node.
        behaviors (List[Behaviour]): Behaviors to choose between.
        probabilities (List[float]): Absolute probability for each behavior.
            Must sum to 1.0 (within 1e-9) and match the length of
            ``behaviors``.

    Returns:
        py_trees.composites.Selector: A selector with memory, whose children
        are the wrapped behaviors.

    Raises:
        ValueError: If ``probabilities`` does not sum to 1.0, or the two lists
            differ in length.

    Example:
        .. testcode::

            a = py_trees.behaviours.Success(name="A")
            b = py_trees.behaviours.Success(name="B")
            c = py_trees.behaviours.Success(name="C")

            # A is chosen 20% of the time, B 30%, C 50%.
            selector = random_selector("WeightedChoice", [a, b, c], [0.2, 0.3, 0.5])
    """
    if abs(sum(probabilities) - 1.0) >= 1e-9:
        raise ValueError(f'sum(probabilities) must add up to 1.0, got {sum(probabilities)}')
    if len(probabilities) != len(behaviors):
        raise ValueError('len(probabilities) != len(behaviors), two lists must be of same length.')

    children = []
    new_probabilities = []
    cumulative_prob = 0.0
    for behavior, raw_prob in zip(behaviors, probabilities):
        new_prob = raw_prob/(1.0-cumulative_prob)
        if new_prob >= 1.0:
            children.append(behavior)
            break

        new_probabilities.append(new_prob)
        decorated_behavior_name = f'random_run_{behavior.name}'
        decorated_behavior = RandomRun(name=decorated_behavior_name,
                                       child=behavior,
                                       probability=new_prob)
        children.append(decorated_behavior)

        cumulative_prob += raw_prob

    logging.debug(f'behaviors->new_probabilities: {[b.name for b in behaviors]}->{new_probabilities}')

    selector = py_trees.composites.Selector(name, True, children)
    return selector
