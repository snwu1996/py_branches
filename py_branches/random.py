#!/usr/bin/env python3

import py_trees
import random
import logging
import time
from typing import List


class RandomRun(py_trees.decorators.Decorator):
    '''
    Random chance of running the child of this decorator.
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
    a delay is sampled uniformly from [low, high] seconds.  The decorator
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

    Example:
        child = py_trees.behaviours.Success(name="Action")
        # Pause 0.5–2.0 seconds before running the child each time.
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
        self._start_time = None
        self._waiting = False

    def tick(self):
        # Fresh entry: sample a new delay and start the timer.
        if self.status != py_trees.common.Status.RUNNING:
            self._delay = random.uniform(self._low, self._high)
            self._start_time = time.time()
            self._waiting = True

        if self._waiting:
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

    selector = py_trees.composites.Selector(name, False, children)
    return selector
