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
        activate(bool): Whether or not to start this behavior activated or not.
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
    Args:
        name(str): Name of the behavior
        behaviors(List[Behaviors]): List of all the behaviors to run alternating.
        count(List[int]): A list of how many times the corresponding behavior ought to be ran.

            Example:
                A if behaviors is [behavior_a, behavior_b, behavior_c] and count is [3,2,4] then
                behavior_a will run 3 times in a row, behavior_b will run 2 times in a row, and
                behavior_c will run 4 times in a row before repeating.
    '''
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

class RunEveryRange(py_trees.decorators.Decorator):
    '''
    Enables the activation of child every for a range of calls within

    Args:
        child(Behavior): The child behavior that is being activated or not activated.
        name(str): Name of this behavior.
        max_range(int): Maximum number of runs before the iterations resets to 1.
        run_range(Tuple[int, int]): Determines which range of iterations that the child
            will execute for. Range is inclusive.

    Example:
        E: Executes that cycle.
        S: Skips that cycle.
        if max_range and run_range is:
            6 and (4,6) the the child will run on the 4th, 5th, and 6th cycle.
                S, S, S, E, E, E, S, S, S, E, E, E, S, S, S, ...
            6 and (2,4) then the child will run on the 2nd, 3rd, and 4th cycle.
                S, E, E, E, S, S, S, E, E, E, S, S, S, E, E, ...
    '''
    def __init__(self, child: py_trees.behaviour.Behaviour,
                       name: str,
                       max_range: int,
                       run_range: Tuple[int, int],
                       success_if_skip: bool = False):
        assert run_range[0] <= run_range[1], \
            'run_range must be a tuple with (smaller_number, bigger_number)'
        assert 1 <= run_range[0], 'Lower run range must be greater or equal to 1'
        assert run_range[0] <= max_range, f'Upper run range must be lower or equal to {max_range}'

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
    def __init__(self, child: py_trees.behaviour.Behaviour,
                       name: str,
                       every_x_range: Tuple[int, int],
                       success_if_skip:bool=False):
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

    def update(self):
        return self.decorated.status
