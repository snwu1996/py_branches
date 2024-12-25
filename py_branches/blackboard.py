#!/usr/bin/env python3
from typing import Any
from typing import Optional
import py_trees


def _get_and_check(bb: py_trees.blackboard.Client, var: str, types: Optional[list], logger):
    value = bb.get(var)
    if value is None:
        logger.warning(f'Tried to increment blackboard {var} but it doens\'t exist.')
    if types is not None and type(value) not in types:
        logger.warning(f'Tried to increment blackboard variable {var} '+
            f'of type {type(value)}, variable must be of type {types}.')
    return value

class IncrementBlackboardVariable(py_trees.behaviour.Behaviour):
    def __init__(self, name: str, variable_name: str, increment_by: float=1.0):
        super(IncrementBlackboardVariable, self).__init__(name)
        self._variable_name = variable_name
        self._increment_by = increment_by
        self._return_sucess = False
        self._blackboard = py_trees.blackboard.Client()
        self._blackboard.register_key(key=variable_name, access=py_trees.common.Access.WRITE)

    def initialise(self):
        current_value = _get_and_check(self._blackboard, self._variable_name, [int, float], self.logger)
        self._blackboard.set(self._variable_name, current_value+self._increment_by)
        self._return_sucess = True

    def update(self):
        if self._return_sucess:
            return py_trees.common.Status.SUCCESS
        else:
            return py_trees.common.Status.FAILURE

class IncrementBlackboardVariableIfCondition(py_trees.decorators.Decorator):
    def __init__(self, child, name: str, variable_name: str, condition: py_trees.common.Status, increment_by: float=1.0):
        super(IncrementBlackboardVariableIfCondition, self).__init__(name=name, child=child)
        self._variable_name = variable_name
        self._condition = condition
        self._increment_by = increment_by
        self._blackboard = py_trees.blackboard.Client()
        self._blackboard.register_key(key=variable_name, access=py_trees.common.Access.WRITE)

    def update(self):
        if self.decorated.status == self._condition:
            current_value = _get_and_check(self._blackboard, self._variable_name, [int, float], self.logger)
            self._blackboard.set(self._variable_name, current_value+self._increment_by, overwrite=True)

        return self.decorated.status

class SetBlackboardVariableIfCondition(py_trees.decorators.Decorator):
    def __init__(self, child, name: str, variable_name: str, condition: py_trees.common.Status, set_to: Any):
        super(SetBlackboardVariableIfCondition, self).__init__(name=name, child=child)
        self._variable_name = variable_name
        self._condition = condition
        self._set_to = set_to
        self._blackboard = py_trees.blackboard.Client()
        self._blackboard.register_key(key=variable_name, access=py_trees.common.Access.WRITE)

    def update(self):
        if self.decorated.status == self._condition:
            self._blackboard.set(self._variable_name, self._set_to, overwrite=True)

        return self.decorated.status

class RunIfBlackboardVariableEquals(py_trees.decorators.Decorator):
    def __init__(self, child, name: str, variable_name: str, equals: Any, success_if_skip: bool=True):
        super(RunIfBlackboardVariableEquals, self).__init__(name=name, child=child)
        self._variable_name = variable_name
        self._equals = equals
        self._blackboard = py_trees.blackboard.Client()
        self._blackboard.register_key(key=variable_name, access=py_trees.common.Access.READ)
        self._run_child = False
        self._initialized = False
        self._ret_status_on_failure = py_trees.common.Status.SUCCESS if success_if_skip else py_trees.common.Status.FAILURE

    def initialise(self):
        current_value = _get_and_check(self._blackboard, self._variable_name, None, self.logger)
        self._run_child = current_value == self._equals
        self._initialized = True

    def tick(self):
        if not self._initialized:
            self.initialise()

        if self._run_child:
            # Run Decorator tick method which will tick the child nodes.
            for node in py_trees.decorators.Decorator.tick(self):
                yield node
        else:
            # Run passthrough tick method defined by the default Behaviour tick.
            for node in py_trees.behaviour.Behaviour.tick(self):
                yield node

    def update(self):
        if self._run_child:
            if self.decorated.status != py_trees.common.Status.RUNNING:
                self._reset()
            return self.decorated.status
        else:
            self._reset()
            return self._ret_status_on_failure

    def _reset(self):
        self._run_child = False
        self._initialized = False
