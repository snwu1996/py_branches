#!/usr/bin/env python3

import py_trees
import random
import logging
from typing import List


class RandomRun(py_trees.decorators.Decorator):
    '''
    Random chance of running the child of this decorator.
    '''
    def __init__(self, child, name, probability: float, success_if_skip: bool = False):
        super(RandomRun, self).__init__(name=name, child=child)
        assert probability >= 0 and probability <= 1.0, f'Probability == {probability} but needs to be in range [0, 1.0]'
        self._probability = probability
        self._run = random.random() <= self._probability
        self._success_if_skip = success_if_skip

    def tick(self):
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


def random_selector(name, behaviors: List[py_trees.behaviour.Behaviour], probabilities: List[float]):
    assert sum(probabilities) == 1.0, 'sum(probabilities) must add up to 1.0'
    assert len(probabilities) == len(behaviors), \
        'len(probabilities) != len(behaviors), two lists must be of same length.'

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
