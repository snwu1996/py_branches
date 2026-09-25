#!/usr/bin/env python3
"""Behaviors and decorators driven by the py_trees blackboard.

The `blackboard
<https://py-trees.readthedocs.io/en/devel/blackboards.html>`_ is py_trees'
shared key-value store for communication between behaviors. This module covers
the common patterns — incrementing counters, setting flags, and gating
execution on a variable's value — so they need not be rewritten as custom
behaviors each time.

Two groups of classes live here:

* **Writers** — :class:`IncrementBlackboardVariable`,
  :class:`IncrementBlackboardVariableIfCondition` and
  :class:`SetBlackboardVariableIfCondition`.
* **Gates** — :class:`RunIfBlackboardVariableEquals`,
  :class:`RunIfBlackboardVariableLessThan` and
  :class:`RunIfBlackboardVariableGreaterThan`, which decide whether to tick
  their child at all.

Every class registers the key it touches on construction, so no manual
registration is needed for the keys used here. The variable itself must still
exist before a reader or an incrementer runs:

.. testcode::

    import py_trees

    client = py_trees.blackboard.Client(name="setup")
    client.register_key("tick_count", access=py_trees.common.Access.WRITE)
    client.tick_count = 0

A missing or wrongly-typed variable is never fatal: the affected behavior logs
a warning and reports FAILURE, or in the case of a gate, treats the condition
as unmet.

Example:
    Increment a counter every tick and run a special action once it reaches 5.

    .. testcode::

        import py_trees
        from py_branches.blackboard import IncrementBlackboardVariable
        from py_branches.blackboard import RunIfBlackboardVariableEquals

        client = py_trees.blackboard.Client(name="example_setup")
        client.register_key("tick_count", access=py_trees.common.Access.WRITE)
        client.tick_count = 0

        increment = IncrementBlackboardVariable(
            name="Tick", variable_name="tick_count", increment_by=1
        )
        special = py_trees.behaviours.Success(name="SpecialOnTick5")
        gate = RunIfBlackboardVariableEquals(
            special, name="RunAt5", variable_name="tick_count", equals=5
        )

        root = py_trees.composites.Sequence(name="Root", memory=True)
        root.add_children([increment, gate])
"""
from typing import Any
from typing import Optional
import py_trees


def _get_and_check(bb: py_trees.blackboard.Client, var: str, types: Optional[list], logger):
    """Read a blackboard variable, logging a warning instead of raising.

    Args:
        bb (Client): Blackboard client to read through.
        var (str): Key to read.
        types (Optional[list]): If given, the value's exact type must appear in
            this list. Pass None to accept any type.
        logger: Logger that receives a warning when the read fails.

    Returns:
        The value, or None if the key is missing, holds None, or is of an
        unaccepted type. Callers cannot distinguish those cases from a variable
        legitimately set to None.
    """
    try:
        value = bb.get(var)
    except KeyError:
        logger.warning(f'Tried to access blackboard variable {var} but it does not exist.')
        return None
    if value is None:
        logger.warning(f'Tried to access blackboard variable {var} but it does not exist.')
        return None
    if types is not None and type(value) not in types:
        logger.warning(f'Tried to access blackboard variable {var} ' +
            f'of type {type(value)}, variable must be one of {types}.')
        return None
    return value

class IncrementBlackboardVariable(py_trees.behaviour.Behaviour):
    """Increment a numeric blackboard variable, as a leaf behavior.

    The increment happens in ``initialise()``, i.e. once per fresh entry rather
    than once per tick, and the key is registered for WRITE access on
    construction.

    The variable must already exist and hold an int or float; this behavior
    adds to a value, it does not create one. See the module docstring for how
    to seed a key before the tree runs.

    Args:
        name (str): Name of this behavior node.
        variable_name (str): Blackboard key to increment. Must hold an int or
            a float.
        increment_by (float): Amount to add. Default 1.0.

    Returns:
        Status: SUCCESS after a successful increment; FAILURE if the variable
        is missing or is not a numeric type, in which case a warning is also
        logged.

    Example:
        .. testcode::

            counter = IncrementBlackboardVariable(
                name="IncrementCounter", variable_name="counter", increment_by=1
            )
    """
    def __init__(self, name: str, variable_name: str, increment_by: float=1.0):
        super(IncrementBlackboardVariable, self).__init__(name)
        self._variable_name = variable_name
        self._increment_by = increment_by
        self._return_sucess = False
        self._blackboard = py_trees.blackboard.Client()
        self._blackboard.register_key(key=variable_name, access=py_trees.common.Access.WRITE)

    def initialise(self):
        self._return_sucess = False
        current_value = _get_and_check(self._blackboard, self._variable_name, [int, float], self.logger)
        if current_value is None:
            self.logger.warning(
                f'Failed to increment blackboard variable {self._variable_name}: value missing or invalid.'
            )
            return
        self._blackboard.set(self._variable_name, current_value+self._increment_by)
        self._return_sucess = True

    def update(self):
        if self._return_sucess:
            return py_trees.common.Status.SUCCESS
        else:
            return py_trees.common.Status.FAILURE

class IncrementBlackboardVariableIfCondition(py_trees.decorators.Decorator):
    """Increment a blackboard variable when the child returns a given status.

    The child is always ticked and its status is always passed through
    unchanged; the increment is a side effect. Use this to count how often a
    branch succeeds or fails without disturbing the tree's control flow.

    The variable must already exist and hold an int or float. If it is missing
    or of another type, a warning is logged and the increment is skipped — the
    child's status is still returned.

    Args:
        child (Behaviour): The behavior to wrap.
        name (str): Name of this decorator node.
        variable_name (str): Blackboard key to increment.
        condition (Status): Status that triggers the increment, e.g.
            ``py_trees.common.Status.SUCCESS``.
        increment_by (float): Amount to add. Default 1.0.

    Example:
        .. testcode::

            child = py_trees.behaviours.Success(name="Child")

            # Increment "success_count" each time child returns SUCCESS.
            counter = IncrementBlackboardVariableIfCondition(
                child,
                name="CountSuccesses",
                variable_name="success_count",
                condition=py_trees.common.Status.SUCCESS,
                increment_by=1,
            )
    """
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
            if current_value is not None:
                self._blackboard.set(self._variable_name, current_value+self._increment_by, overwrite=True)

        return self.decorated.status

class SetBlackboardVariableIfCondition(py_trees.decorators.Decorator):
    """Set a blackboard variable when the child returns a given status.

    The child is always ticked and its status is always passed through
    unchanged; the assignment is a side effect. Unlike
    :class:`IncrementBlackboardVariable`, the key need not already exist — the
    write overwrites whatever is there, or creates it.

    Args:
        child (Behaviour): The behavior to wrap.
        name (str): Name of this decorator node.
        variable_name (str): Blackboard key to set.
        condition (Status): Status that triggers the assignment.
        set_to (Any): Value to write to the blackboard key.

    Example:
        .. testcode::

            child = py_trees.behaviours.Failure(name="Child")

            # Reset "is_active" to False whenever the child fails.
            reset = SetBlackboardVariableIfCondition(
                child,
                name="ResetOnFailure",
                variable_name="is_active",
                condition=py_trees.common.Status.FAILURE,
                set_to=False,
            )
    """
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
    """Run the child only when a blackboard variable equals a given value.

    The condition is evaluated on each fresh entry — that is, whenever this
    decorator was not already RUNNING — and then held for the duration of the
    child's execution. A child that returns RUNNING therefore finishes its work
    even if the variable changes underneath it mid-execution.

    When the condition is not met the child is not ticked at all, and this
    decorator returns SUCCESS or FAILURE according to ``success_if_skip``.

    Note:
        A variable that is missing from the blackboard reads as None. Passing
        ``equals=None`` therefore matches a missing variable as well as one
        explicitly set to None.

    Args:
        child (Behaviour): The behavior to wrap.
        name (str): Name of this decorator node.
        variable_name (str): Blackboard key to read.
        equals (Any): Value to compare against.
        success_if_skip (bool): Return SUCCESS instead of FAILURE when the
            condition is not met. Default True, which makes a skipped child
            transparent to a parent Sequence.

    Example:
        .. testcode::

            child = py_trees.behaviours.Success(name="SpecialAction")

            # Only run SpecialAction when "mode" equals "fast".
            gated = RunIfBlackboardVariableEquals(
                child,
                name="RunIfFast",
                variable_name="mode",
                equals="fast",
                success_if_skip=True,
            )
    """
    def __init__(self, child, name: str, variable_name: str, equals: Any, success_if_skip: bool=True):
        super(RunIfBlackboardVariableEquals, self).__init__(name=name, child=child)
        self._variable_name = variable_name
        self._equals = equals
        self._blackboard = py_trees.blackboard.Client()
        self._blackboard.register_key(key=variable_name, access=py_trees.common.Access.READ)
        self._run_child = False
        self._ret_status_on_failure = py_trees.common.Status.SUCCESS if success_if_skip else py_trees.common.Status.FAILURE

    def tick(self):
        # Re-evaluate the condition on each fresh entry; preserve it while child is RUNNING.
        if self.status != py_trees.common.Status.RUNNING:
            current_value = _get_and_check(self._blackboard, self._variable_name, None, self.logger)
            self._run_child = current_value == self._equals

        if self._run_child:
            for node in py_trees.decorators.Decorator.tick(self):
                yield node
        else:
            for node in py_trees.behaviour.Behaviour.tick(self):
                yield node

    def update(self):
        if self._run_child:
            if self.decorated.status != py_trees.common.Status.RUNNING:
                self._run_child = False
            return self.decorated.status
        else:
            self._run_child = False
            return self._ret_status_on_failure


class RunIfBlackboardVariableLessThan(py_trees.decorators.Decorator):
    """Run the child only while a blackboard variable is less than a value.

    The numeric counterpart to :class:`RunIfBlackboardVariableEquals`; see that
    class for the full description of when the condition is evaluated. The
    comparison is ``current_value < less_than``.

    A missing variable never satisfies the condition, so the child is skipped
    rather than compared against None.

    Args:
        child (Behaviour): The behavior to wrap.
        name (str): Name of this decorator node.
        variable_name (str): Blackboard key to read.
        less_than (Any): Value the variable must stay below.
        success_if_skip (bool): Return SUCCESS instead of FAILURE when the
            condition is not met. Default True.

    Example:
        .. testcode::

            child = py_trees.behaviours.Running(name="Download")

            # Keep retrying only while the attempt count is under 5.
            gated = RunIfBlackboardVariableLessThan(
                child,
                name="RunWhileUnderLimit",
                variable_name="attempts",
                less_than=5,
            )
    """
    def __init__(self, child, name: str, variable_name: str, less_than: Any, success_if_skip: bool=True):
        super(RunIfBlackboardVariableLessThan, self).__init__(name=name, child=child)
        self._variable_name = variable_name
        self._less_than = less_than
        self._blackboard = py_trees.blackboard.Client()
        self._blackboard.register_key(key=variable_name, access=py_trees.common.Access.READ)
        self._run_child = False
        self._ret_status_on_failure = py_trees.common.Status.SUCCESS if success_if_skip else py_trees.common.Status.FAILURE

    def tick(self):
        if self.status != py_trees.common.Status.RUNNING:
            current_value = _get_and_check(self._blackboard, self._variable_name, None, self.logger)
            self._run_child = current_value is not None and current_value < self._less_than

        if self._run_child:
            for node in py_trees.decorators.Decorator.tick(self):
                yield node
        else:
            for node in py_trees.behaviour.Behaviour.tick(self):
                yield node

    def update(self):
        if self._run_child:
            if self.decorated.status != py_trees.common.Status.RUNNING:
                self._run_child = False
            return self.decorated.status
        else:
            self._run_child = False
            return self._ret_status_on_failure


class RunIfBlackboardVariableGreaterThan(py_trees.decorators.Decorator):
    """Run the child only while a blackboard variable is greater than a value.

    The numeric counterpart to :class:`RunIfBlackboardVariableEquals`; see that
    class for the full description of when the condition is evaluated. The
    comparison is ``current_value > greater_than``.

    A missing variable never satisfies the condition, so the child is skipped
    rather than compared against None.

    Args:
        child (Behaviour): The behavior to wrap.
        name (str): Name of this decorator node.
        variable_name (str): Blackboard key to read.
        greater_than (Any): Value the variable must exceed.
        success_if_skip (bool): Return SUCCESS instead of FAILURE when the
            condition is not met. Default True.

    Example:
        .. testcode::

            child = py_trees.behaviours.Success(name="Celebrate")

            # Only celebrate once the score climbs above 100.
            gated = RunIfBlackboardVariableGreaterThan(
                child,
                name="RunIfWinning",
                variable_name="score",
                greater_than=100,
            )
    """
    def __init__(self, child, name: str, variable_name: str, greater_than: Any, success_if_skip: bool=True):
        super(RunIfBlackboardVariableGreaterThan, self).__init__(name=name, child=child)
        self._variable_name = variable_name
        self._greater_than = greater_than
        self._blackboard = py_trees.blackboard.Client()
        self._blackboard.register_key(key=variable_name, access=py_trees.common.Access.READ)
        self._run_child = False
        self._ret_status_on_failure = py_trees.common.Status.SUCCESS if success_if_skip else py_trees.common.Status.FAILURE

    def tick(self):
        if self.status != py_trees.common.Status.RUNNING:
            current_value = _get_and_check(self._blackboard, self._variable_name, None, self.logger)
            self._run_child = current_value is not None and current_value > self._greater_than

        if self._run_child:
            for node in py_trees.decorators.Decorator.tick(self):
                yield node
        else:
            for node in py_trees.behaviour.Behaviour.tick(self):
                yield node

    def update(self):
        if self._run_child:
            if self.decorated.status != py_trees.common.Status.RUNNING:
                self._run_child = False
            return self.decorated.status
        else:
            self._run_child = False
            return self._ret_status_on_failure
