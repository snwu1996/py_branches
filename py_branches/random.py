#!/usr/bin/env python3

import py_trees
import random
from typing import List


class RandomSuccess(py_trees.behaviour.Behaviour):
    def __init__(self, name: str, probability: float):
        super(RandomSuccess, self).__init__(name=name)
        assert probability >= 0 and probability <= 1.0, f'Probability == {probability} but needs to be in range [0, 1.0]'
        self._probability = probability

    def update(self):
        if random.random() < self._probability:
            return py_trees.Status.SUCCESS
        else:
            return py_trees.Status.FAILURE

class RandomRun(py_trees.decorators.Decorator):
    '''
    Random chance of running the child of this decorator.
    '''
    def __init__(self, child, name, probability: float, success_if_not_ran: bool = False):
        super(RandomRun, self).__init__(name=name, child=child)
        assert probability >= 0 and probability <= 1.0, f'Probability == {probability} but needs to be in range [0, 1.0]'
        self._probability = probability
        self._run = None
        self._success_if_not_ran = success_if_not_ran

    def initialise(self):
        if random.random() < self._probability:
            self._run = True
        else:
            self._run = False

    def update(self):
        if not self._run:
            if self._success_if_not_ran:
                return py_trees.Status.SUCCESS
            else:
                return py_trees.Status.FAILURE

        return self.decorated.status

class RandomSelector(py_trees.composites.Selector):
    def __init__(self, name, behaviors: List, probabilities: List[float]):
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

        logging.info(f'behaviors->new_probabilities: {[b.name for b in behaviors]}->{new_probabilities}')
        super(RandomSelector, self).__init__(name, children)