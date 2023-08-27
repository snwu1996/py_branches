#!/usr/bin/env python3
import rospy
import py_trees
import random
from typing import List
from typing import Tuple


class ActivateBehavior(py_trees.decorators.Decorator):
    '''
    Enables activation of a behavior from an external source as long as it has a handle to 
    this decorator.

    Args:
        child(Behavior): The child behavior that is being activated or not activated.
        name(str): Name of this behavior
    '''
    def __init__(self, child, name: str, activate: bool, always_success:bool=False):
        super(ActivateBehavior, self).__init__(name=name, child=child)
        self._activate = activate
        self._always_success = always_success

    @property
    def activate(self):
        return self._activate
    
    @activate.setter
    def activate(self, activate: bool):
        self._activate = activate

    def tick(self):
        if not self._activate:
            if self._always_success:
                self.stop(py_trees.Status.SUCCESS)
            else:
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

class RunEveryX(py_trees.decorators.Decorator):
    '''
    Enables the activation of child every X calls where X iterations. X is a range.

    Args:
        child(Behavior): The child behavior that is being activated or not activated.
        name(str): Name of this behavior
        every_x_range(Tuple[int, int]): Run the child ever however many cycles. Number of
        cycles is within a range. Range is inclusive.

    Example:
        if every_x_range is:
            (1,1) then the child behavior will run every cycle.
            (5,5) then the child behavior will run every 5th cycle.
            (1,5) then the child behavior will run randomly between every
                cycle or every 5th cycle. Changes every times it child gets executed.
    '''
    def __init__(self, child, name: str, every_x_range: Tuple[int, int], always_success:bool=False):
        assert every_x_range[0] <= every_x_range[1], \
            'every_x_range must be a tuple with (smaller_number, bigger_number)'
        assert every_x_range[0] > 0, 'Can not have range be lower than 1.'

        super(RunEveryX, self).__init__(name=name, child=child)
        self._every_x_range = every_x_range
        self._cycles_remaining = random.randint(*self._every_x_range)-1
        self._always_success = always_success

    def initialise(self):
        self._cycles_remaining = random.randint(*self._every_x_range)-1

    def tick(self):
        if self._cycles_remaining > 0:
            self._cycles_remaining -= 1
            if self._always_success:
                self.stop(py_trees.Status.SUCCESS)
            else:
                self.stop(py_trees.Status.FAILURE)
            yield self
        else:
            for node in super().tick():
                yield node

    def update(self):
        return self.decorated.status
