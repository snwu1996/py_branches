#!/usr/bin/env python
from __future__ import absolute_import
from __future__ import print_function
import py_trees
from py_branches.blackboard_behaviors import IncrementBlackboardVariable
from py_branches.blackboard_behaviors import IncrementBlackboardVariableIfCondition
from py_branches.blackboard_behaviors import SetBlackboardVariableIfCondition
from py_branches.blackboard_behaviors import RunIfBlackboardVariableEquals


_r = py_trees.Status.RUNNING
_s = py_trees.Status.SUCCESS
_f = py_trees.Status.FAILURE
_i = py_trees.Status.INVALID

def _tick_and_check_status(behavior, expected_status_list):
    for i, expected_status in enumerate(expected_status_list):
        behavior.tick_once()
        assert behavior.status == expected_status, \
            f'i == {i}, {behavior.status} != {expected_status}'

def test_increment_blackboard_variable():
    blackboard = py_trees.Blackboard()
    set_foo = py_trees.blackboard.SetBlackboardVariable(name="Set Foo", variable_name="foo", variable_value=1)
    set_foo.tick_once()
    assert(hasattr(blackboard, "foo"))
    assert(blackboard.foo == 1)
    assert(set_foo.status == py_trees.Status.SUCCESS) 
    
    increment_foo = IncrementBlackboardVariable(name="Increment Foo", variable_name="foo", increment_by=1)
    increment_foo.tick_once()
    assert(hasattr(blackboard, "foo"))
    assert(blackboard.foo == 2)
    assert(increment_foo.status == py_trees.Status.SUCCESS)

def test_increment_blackboard_variable_if_condition():
    blackboard = py_trees.Blackboard()
    blackboard.foo = 0.0
    success = py_trees.behaviours.Success('success')
    failure = py_trees.behaviours.Failure('failure')

    increment_blackboard_variable_if_success = \
        IncrementBlackboardVariableIfCondition(success, 'increment_blackboard_variable_if_success',
            'foo', py_trees.Status.SUCCESS, 1.0)
    increment_blackboard_variable_if_success.tick_once()
    increment_blackboard_variable_if_success.tick_once()
    increment_blackboard_variable_if_success.tick_once()
    assert(hasattr(blackboard, 'foo'))
    assert(blackboard.foo == 3.0)

    increment_blackboard_variable_if_failure = \
        IncrementBlackboardVariableIfCondition(failure, 'increment_blackboard_variable_if_failure',
            'foo', py_trees.Status.FAILURE, 2.0)
    increment_blackboard_variable_if_failure.tick_once()
    increment_blackboard_variable_if_failure.tick_once()
    increment_blackboard_variable_if_failure.tick_once()
    assert(hasattr(blackboard, 'foo'))
    assert(blackboard.foo == 9.0)

    increment_blackboard_variable_if_failure = \
        IncrementBlackboardVariableIfCondition(success, 'increment_blackboard_variable_if_failure',
            'foo', py_trees.Status.FAILURE, 100.0)
    increment_blackboard_variable_if_failure.tick_once()
    increment_blackboard_variable_if_failure.tick_once()
    increment_blackboard_variable_if_failure.tick_once()
    assert(hasattr(blackboard, 'foo'))
    assert(blackboard.foo == 9.0)

def test_set_blackboard_variable_if_condition():
    blackboard = py_trees.Blackboard()
    success = py_trees.behaviours.Success('success')
    failure = py_trees.behaviours.Failure('failure')

    set_blackboard_variable_if_success = \
        SetBlackboardVariableIfCondition(success, 'set_blackboard_variable_if_success',
            'foo', py_trees.Status.SUCCESS, 123.0)
    set_blackboard_variable_if_success.tick_once()
    assert(hasattr(blackboard, 'foo'))
    assert(blackboard.foo == 123.0)

    set_blackboard_variable_if_failure = \
        SetBlackboardVariableIfCondition(failure, 'set_blackboard_variable_if_failure',
            'bar', py_trees.Status.FAILURE, 'hello123')
    set_blackboard_variable_if_failure.tick_once()
    assert(hasattr(blackboard, 'bar'))
    assert(blackboard.bar == 'hello123')

    set_blackboard_variable_if_failure = \
        SetBlackboardVariableIfCondition(success, 'set_blackboard_variable_if_failure',
            'baz', py_trees.Status.FAILURE, 'hello123')
    set_blackboard_variable_if_failure.tick_once()
    assert(not hasattr(blackboard, 'baz'))

def test_run_if_blackboard_variable_equals():
    # Helper function to create RunIfBlackboardVariableEquals decorator
    def _create_ribve(child, bb_var, expected_val, always_success):
        return RunIfBlackboardVariableEquals(child, 'run_if_blackboard_variable_equals',
            bb_var, expected_val, always_success)

    blackboard = py_trees.Blackboard()
    blackboard.foo = 123.0
    count = py_trees.behaviours.Count('count', fail_until=0, running_until=3, success_until=4)

    # Normal operations
    ribve = _create_ribve(count, 'foo', 123.0, True)
    _tick_and_check_status(ribve, [_r, _r, _r, _s])
    assert(count.count == 4)

    # Skip behavior, always return success.
    count.count = 0
    ribve = _create_ribve(count, 'foo', 0.0, True)
    _tick_and_check_status(ribve, [_s, _s])
    assert(count.count == 0)

    # Skip behavior, always return failure
    count.count = 0
    ribve = _create_ribve(count, 'foo', 0.0, False)
    _tick_and_check_status(ribve, [_f, _f])
    assert(count.count == 0)

    # Blackboard variable went from not meeting condition to meeting condition.
    blackboard.foo = 0.0
    _tick_and_check_status(ribve, [_r, _r, _r, _s])
    assert(count.count == 4)

    # Blackboard variable doesn't exist, skip behavior, always return success.
    ribve = _create_ribve(count, 'bar', 0.0, True)
    _tick_and_check_status(ribve, [_s, _s])