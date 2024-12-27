#!/usr/bin/env python3
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
    def __init__(self, child, name: str, activate: bool, success_if_skip:bool=False):
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
    assert 0 not in counts, \
        f'counts({counts}) can not have 0 in the list.'
    assert len(counts) == len(behaviors), \
        'len(counts) != len(behaviors), two lists must be of same length.'

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

# class RunEveryXOfY(py_trees.decorators.Decorator):
#     pass

class RunEveryX(py_trees.decorators.Decorator):
    '''
    Enables the activation of child every X calls. X can falls within a range
    and gets recalculated every success.

    Args:
        child(Behavior): The child behavior that is being activated or not activated.
        name(str): Name of this behavior
        every_x_range(Tuple[int, int]): Run the child ever however many cycles. Number of
        cycles is within a range. Range is inclusive.

    Example:
        E: Executes that cycle.
        S: Skips that cycle.
        if every_x_range is:
            (1,1) then the child behavior will run every cycle.
                E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, ...
            (5,5) then the child behavior will run every 5th cycle.
                S, S, S, S, E, S, S, S, S, E, S, S, S, S, E, ...
            (1,5) then the child behavior will run randomly between every
            cycle or every 5th cycle. Changes every times it child gets executed.
                S, S, E, S, S, S, S, E, E, S, S, S, E, S, S, ...
                The execute cycle above goes:
                    3: S, S, E
                    5: S, S, S, S, E
                    1: E
                    4: S, S, S, E
    '''
    def __init__(self, child, name: str, every_x_range: Tuple[int, int], success_if_skip:bool=False):
        assert every_x_range[0] <= every_x_range[1], \
            'every_x_range must be a tuple with (smaller_number, bigger_number)'
        assert every_x_range[0] > 0, 'Can not have range be lower than 1.'

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

    def update(self) -> py_trees.common.Status:
        return self.decorated.status
