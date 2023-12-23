#!/usr/bin/env python3
import py_trees


class IncrementBlackboardVariable(py_trees.behaviours.Behaviour):
    def __init__(self, name, variable_name, increment_by=1.0):
        super(IncrementBlackboardVariable, self).__init__(name)
        self._variable_name = variable_name
        self._increment_by = increment_by
        self._return_sucess = False

    def initialise(self):
        self._blackboard = py_trees.Blackboard()
        current_value = self._blackboard.get(self._variable_name)
        if current_value is None:
            self.logger.warning(f'Tried to increment blackboard {self._variable_name} but it doens\'t exist.')
        if type(current_value) != int and type(current_value) != float:
            self.logger.warning(f'Tried to increment blackboard variable {self._variable_name} '+
                f'of type {type(current_value)}, variable must be of type float or int.')
        self._blackboard.set(self._variable_name, current_value+self._increment_by, overwrite=True)
        self._return_sucess = True

    def update(self):
        if self._return_sucess:
            return py_trees.common.Status.SUCCESS
        else:
            return py_trees.common.Status.FAILURE        