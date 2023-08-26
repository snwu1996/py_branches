#!/usr/bin/env python3
import rospy
import py_trees
from typing import List


class ActivateBehavior(py_trees.decorators.Decorator):
    '''
    Enables activation of a behavior from an external source as long as it has a handle to 
    this decorator.

    Args:
        child(Behavior): The child behavior that is being activated or not activated.
        name(str): Name of this behavior
    '''
    def __init__(self, child, name: str,
                              activate: bool):
        super(ActivateBehavior, self).__init__(name=name, child=child)
        self._activate = activate

    @property
    def activate(self):
        return self._activate
    
    @activate.setter
    def activate(self, activate: bool):
        self._activate = activate

    def tick(self):
        if not self._activate:
            self.stop(py_trees.Status.FAILURE)
            yield self
        else:
            for node in super().tick():
                yield node

    def update(self):
        return self.decorated.status

class RunAlternating(py_trees.composites.Chooser):
    '''
    Args:
        name(str): Name of the behavior
        behaviors(List[Behaviors]): List of all the behaviors to run alternating.
        count(List[int]): A list of how many times the corresponding behavior ought to be ran.

            Example:
                A if behaviors is [behavior_a, behavior_b, behavior_c] and count is [3,2,4] then 
                behavior_a will run 3 times in a row, behavior_b will run 2 times in a row, and 
                behavior_c will run 4 times in a row before repeating.
    '''
    def __init__(self, name: str, behaviors: List, counts: List[int]):
        assert 0 not in counts, \
            f'counts({counts}) can not have 0 in the list.'
        assert len(counts) == len(behaviors), \
            'len(counts) != len(behaviors), two lists must be of same length.'

        self._counts = counts
        self._current_behavior_idx = 0
        self._current_behavior_num_consecutive_runs = 0

        children = []
        for idx, behavior in enumerate(behaviors):
            activate_decorator = \
                ActivateBehavior(child=behavior, 
                                 name=f'activate_{behavior.name}',
                                 activate=True if idx == 0 else False)
            children.append(activate_decorator)

        super(RunAlternating, self).__init__(name, children)

    def initialise(self):
        if self._current_behavior_num_consecutive_runs >= self._counts[self._current_behavior_idx]:
            self.children[self._current_behavior_idx].activate = False
            self._current_behavior_idx = (self._current_behavior_idx + 1) % len(self._counts)
            self.children[self._current_behavior_idx].activate = True
            self._current_behavior_num_consecutive_runs = 0
            
        self._current_behavior_num_consecutive_runs += 1
