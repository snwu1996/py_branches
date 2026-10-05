#!/usr/bin/env python
import logging

import py_trees

from py_branches.blackboard import IncrementBlackboardVariable
from py_branches.blackboard import IncrementBlackboardVariableIfCondition
from py_branches.blackboard import LogBlackboardVariable
from py_branches.blackboard import RunIfBlackboardVariableEquals
from py_branches.blackboard import RunIfBlackboardVariableGreaterThan
from py_branches.blackboard import RunIfBlackboardVariableLessThan
from py_branches.blackboard import SetBlackboardVariableIfCondition

_r = py_trees.common.Status.RUNNING
_s = py_trees.common.Status.SUCCESS
_f = py_trees.common.Status.FAILURE
_i = py_trees.common.Status.INVALID


def _tick_and_check_status(behavior, expected_status_list):
    for i, expected_status in enumerate(expected_status_list):
        behavior.tick_once()
        assert behavior.status == expected_status, (
            f"i == {i}, {behavior.status} != {expected_status}"
        )


def test_increment_blackboard_variable():
    blackboard = py_trees.blackboard.Client()
    blackboard.register_key(key="foo", access=py_trees.common.Access.WRITE)
    set_foo = py_trees.behaviours.SetBlackboardVariable(
        name="Set Foo", variable_name="foo", variable_value=1, overwrite=True
    )
    set_foo.tick_once()
    assert blackboard.exists("foo")
    assert blackboard.foo == 1
    assert set_foo.status == py_trees.common.Status.SUCCESS

    increment_foo = IncrementBlackboardVariable(
        name="Increment Foo", variable_name="foo", increment_by=1
    )
    increment_foo.tick_once()
    assert blackboard.exists("foo")
    assert blackboard.foo == 2
    assert increment_foo.status == py_trees.common.Status.SUCCESS


def test_increment_blackboard_variable_logs_change(caplog):
    blackboard = py_trees.blackboard.Client()
    blackboard.register_key(key="counter", access=py_trees.common.Access.WRITE)
    blackboard.counter = 2

    increment = IncrementBlackboardVariable(
        name="Increment Counter", variable_name="counter", increment_by=1
    )
    with caplog.at_level(logging.DEBUG, logger="py_branches.blackboard"):
        increment.tick_once()

    assert caplog.messages == ["Increment Counter: counter 2 -> 3"]


def test_increment_blackboard_variable_invalid_value_fails_safely():
    blackboard = py_trees.blackboard.Client()
    blackboard.register_key(key="missing_var", access=py_trees.common.Access.WRITE)
    blackboard.register_key(key="string_var", access=py_trees.common.Access.WRITE)
    blackboard.string_var = "not_a_number"

    increment_missing = IncrementBlackboardVariable(
        name="Increment Missing",
        variable_name="missing_var",
        increment_by=1,
    )
    increment_missing.tick_once()
    assert increment_missing.status == py_trees.common.Status.FAILURE
    assert not blackboard.exists("missing_var")

    increment_string = IncrementBlackboardVariable(
        name="Increment String",
        variable_name="string_var",
        increment_by=1,
    )
    increment_string.tick_once()
    assert increment_string.status == py_trees.common.Status.FAILURE
    assert blackboard.string_var == "not_a_number"


def test_increment_blackboard_variable_if_condition():
    blackboard = py_trees.blackboard.Client()
    blackboard.register_key(key="foo", access=py_trees.common.Access.WRITE)
    blackboard.foo = 0.0
    success = py_trees.behaviours.Success("success")
    failure = py_trees.behaviours.Failure("failure")

    increment_blackboard_variable_if_success = IncrementBlackboardVariableIfCondition(
        success,
        "increment_blackboard_variable_if_success",
        "foo",
        py_trees.common.Status.SUCCESS,
        1.0,
    )
    increment_blackboard_variable_if_success.tick_once()
    increment_blackboard_variable_if_success.tick_once()
    increment_blackboard_variable_if_success.tick_once()
    assert blackboard.exists("foo")
    assert blackboard.foo == 3.0

    increment_blackboard_variable_if_failure = IncrementBlackboardVariableIfCondition(
        failure,
        "increment_blackboard_variable_if_failure",
        "foo",
        py_trees.common.Status.FAILURE,
        2.0,
    )
    increment_blackboard_variable_if_failure.tick_once()
    increment_blackboard_variable_if_failure.tick_once()
    increment_blackboard_variable_if_failure.tick_once()
    assert blackboard.exists("foo")
    assert blackboard.foo == 9.0

    increment_blackboard_variable_if_failure = IncrementBlackboardVariableIfCondition(
        success,
        "increment_blackboard_variable_if_failure",
        "foo",
        py_trees.common.Status.FAILURE,
        100.0,
    )
    increment_blackboard_variable_if_failure.tick_once()
    increment_blackboard_variable_if_failure.tick_once()
    increment_blackboard_variable_if_failure.tick_once()
    assert blackboard.exists("foo")
    assert blackboard.foo == 9.0


def test_set_blackboard_variable_if_condition():
    blackboard = py_trees.blackboard.Client()
    blackboard.register_key(key="foo", access=py_trees.common.Access.READ)
    blackboard.register_key(key="bar", access=py_trees.common.Access.READ)
    blackboard.register_key(key="baz", access=py_trees.common.Access.READ)
    success = py_trees.behaviours.Success("success")
    failure = py_trees.behaviours.Failure("failure")

    set_blackboard_variable_if_success = SetBlackboardVariableIfCondition(
        success,
        "set_blackboard_variable_if_success",
        "foo",
        py_trees.common.Status.SUCCESS,
        123.0,
    )
    set_blackboard_variable_if_success.tick_once()
    assert blackboard.exists("foo")
    assert blackboard.foo == 123.0

    set_blackboard_variable_if_failure = SetBlackboardVariableIfCondition(
        failure,
        "set_blackboard_variable_if_failure",
        "bar",
        py_trees.common.Status.FAILURE,
        "hello123",
    )
    set_blackboard_variable_if_failure.tick_once()
    assert blackboard.exists("bar")
    assert blackboard.bar == "hello123"

    set_blackboard_variable_if_failure = SetBlackboardVariableIfCondition(
        success,
        "set_blackboard_variable_if_failure",
        "baz",
        py_trees.common.Status.FAILURE,
        "hello123",
    )
    set_blackboard_variable_if_failure.tick_once()
    assert not blackboard.exists("baz")


def test_run_if_blackboard_variable_equals():
    # Helper function to create RunIfBlackboardVariableEquals decorator
    def _create_ribve(child, bb_var, expected_val, success_if_skip):
        return RunIfBlackboardVariableEquals(
            child,
            "run_if_blackboard_variable_equals",
            bb_var,
            expected_val,
            success_if_skip,
        )

    blackboard = py_trees.blackboard.Client()
    blackboard.register_key(key="foo", access=py_trees.common.Access.WRITE)
    blackboard.foo = 123.0
    count = py_trees.behaviours.TickCounter(
        "tick_counter", 3, py_trees.common.Status.SUCCESS
    )

    # Normal operations
    ribve = _create_ribve(count, "foo", 123.0, True)
    _tick_and_check_status(ribve, [_r, _r, _r, _s])
    assert count.counter == 4

    # Skip behavior, always return success.
    count.counter = 0
    ribve = _create_ribve(count, "foo", 0.0, True)
    _tick_and_check_status(ribve, [_s, _s])
    assert count.counter == 0

    # Skip behavior, always return failure
    # count.count = 0
    ribve = _create_ribve(count, "foo", 0.0, False)
    _tick_and_check_status(ribve, [_f, _f])
    assert count.counter == 0

    # Blackboard variable now meets the condition.
    blackboard.foo = 0.0
    _tick_and_check_status(ribve, [_r, _r, _r, _s])
    assert count.counter == 4

    # Blackboard variable doesn't exist, skip behavior, always return success.
    ribve = _create_ribve(count, "bar", 0.0, True)
    _tick_and_check_status(ribve, [_s, _s])


def test_run_if_blackboard_variable_less_than():
    def _create_riblt(child, bb_var, less_than, success_if_skip):
        return RunIfBlackboardVariableLessThan(
            child,
            "run_if_blackboard_variable_less_than",
            bb_var,
            less_than,
            success_if_skip,
        )

    blackboard = py_trees.blackboard.Client()
    blackboard.register_key(key="foo", access=py_trees.common.Access.WRITE)
    blackboard.foo = 5.0
    count = py_trees.behaviours.TickCounter(
        "tick_counter", 3, py_trees.common.Status.SUCCESS
    )

    # 5.0 < 10.0, child runs.
    riblt = _create_riblt(count, "foo", 10.0, True)
    _tick_and_check_status(riblt, [_r, _r, _r, _s])
    assert count.counter == 4

    # 5.0 not < 5.0, skip with success.
    count.counter = 0
    riblt = _create_riblt(count, "foo", 5.0, True)
    _tick_and_check_status(riblt, [_s, _s])
    assert count.counter == 0

    # 5.0 not < 1.0, skip with failure.
    riblt = _create_riblt(count, "foo", 1.0, False)
    _tick_and_check_status(riblt, [_f, _f])
    assert count.counter == 0

    # Variable updated to satisfy condition.
    blackboard.foo = 0.0
    _tick_and_check_status(riblt, [_r, _r, _r, _s])
    assert count.counter == 4

    # Missing variable, skip with success.
    riblt = _create_riblt(count, "missing_lt_var", 0.0, True)
    _tick_and_check_status(riblt, [_s, _s])


def test_run_if_blackboard_variable_greater_than():
    def _create_ribgt(child, bb_var, greater_than, success_if_skip):
        return RunIfBlackboardVariableGreaterThan(
            child,
            "run_if_blackboard_variable_greater_than",
            bb_var,
            greater_than,
            success_if_skip,
        )

    blackboard = py_trees.blackboard.Client()
    blackboard.register_key(key="foo", access=py_trees.common.Access.WRITE)
    blackboard.foo = 5.0
    count = py_trees.behaviours.TickCounter(
        "tick_counter", 3, py_trees.common.Status.SUCCESS
    )

    # 5.0 > 1.0, child runs.
    ribgt = _create_ribgt(count, "foo", 1.0, True)
    _tick_and_check_status(ribgt, [_r, _r, _r, _s])
    assert count.counter == 4

    # 5.0 not > 5.0, skip with success.
    count.counter = 0
    ribgt = _create_ribgt(count, "foo", 5.0, True)
    _tick_and_check_status(ribgt, [_s, _s])
    assert count.counter == 0

    # 5.0 not > 10.0, skip with failure.
    ribgt = _create_ribgt(count, "foo", 10.0, False)
    _tick_and_check_status(ribgt, [_f, _f])
    assert count.counter == 0

    # Variable updated to satisfy condition.
    blackboard.foo = 20.0
    _tick_and_check_status(ribgt, [_r, _r, _r, _s])
    assert count.counter == 4

    # Missing variable, skip with success.
    ribgt = _create_ribgt(count, "missing_gt_var", 0.0, True)
    _tick_and_check_status(ribgt, [_s, _s])


def test_log_blackboard_variable_single_variable(caplog):
    blackboard = py_trees.blackboard.Client()
    blackboard.register_key(key="log_bb", access=py_trees.common.Access.WRITE)
    blackboard.log_bb = 42

    log_bb = LogBlackboardVariable(
        name="Log BB",
        variable_names="log_bb",
        message="{log_bb} is the bb variable.",
    )
    with caplog.at_level(logging.INFO, logger="py_branches.blackboard"):
        log_bb.tick_once()

    assert log_bb.status == _s
    assert "42 is the bb variable." in caplog.messages


def test_log_blackboard_variable_multiple_variables(caplog):
    blackboard = py_trees.blackboard.Client()
    blackboard.register_key(key="log_mode", access=py_trees.common.Access.WRITE)
    blackboard.register_key(key="log_score", access=py_trees.common.Access.WRITE)
    blackboard.log_mode = "fast"
    blackboard.log_score = 7

    log_both = LogBlackboardVariable(
        name="Log Both",
        variable_names=["log_mode", "log_score"],
        message="mode={log_mode} score={log_score}",
    )
    with caplog.at_level(logging.INFO, logger="py_branches.blackboard"):
        log_both.tick_once()

    assert log_both.status == _s
    assert "mode=fast score=7" in caplog.messages


def test_log_blackboard_variable_value_with_braces_is_not_reformatted(caplog):
    blackboard = py_trees.blackboard.Client()
    blackboard.register_key(key="log_braces", access=py_trees.common.Access.WRITE)
    blackboard.log_braces = "{not_a_key}"

    log_braces = LogBlackboardVariable(
        name="Log Braces",
        variable_names="log_braces",
        message="value is {log_braces}",
    )
    with caplog.at_level(logging.INFO, logger="py_branches.blackboard"):
        log_braces.tick_once()

    assert log_braces.status == _s
    assert "value is {not_a_key}" in caplog.messages


def test_log_blackboard_variable_missing_variable_fails_safely(caplog):
    log_missing = LogBlackboardVariable(
        name="Log Missing",
        variable_names="log_missing_var",
        message="{log_missing_var} should never be logged.",
    )
    with caplog.at_level(logging.INFO, logger="py_branches.blackboard"):
        log_missing.tick_once()

    assert log_missing.status == _f
    assert not any("should never be logged" in message for message in caplog.messages)


def test_log_blackboard_variable_unknown_placeholder_fails_safely():
    blackboard = py_trees.blackboard.Client()
    blackboard.register_key(key="log_known", access=py_trees.common.Access.WRITE)
    blackboard.log_known = 1

    log_bad_template = LogBlackboardVariable(
        name="Log Bad Template",
        variable_names="log_known",
        message="{log_known} and {log_unknown}",
    )
    log_bad_template.tick_once()

    assert log_bad_template.status == _f


def test_log_blackboard_variable_honours_logger_and_level(caplog):
    blackboard = py_trees.blackboard.Client()
    blackboard.register_key(key="log_custom", access=py_trees.common.Access.WRITE)
    blackboard.log_custom = "here"

    custom_logger = logging.getLogger("test_log_blackboard_variable_custom")
    log_custom = LogBlackboardVariable(
        name="Log Custom",
        variable_names="log_custom",
        message="custom {log_custom}",
        logger=custom_logger,
        level=logging.DEBUG,
    )
    with caplog.at_level(logging.DEBUG, logger=custom_logger.name):
        log_custom.tick_once()

    assert log_custom.status == _s
    records = [r for r in caplog.records if r.name == custom_logger.name]
    assert len(records) == 1
    assert records[0].levelno == logging.DEBUG
    assert records[0].getMessage() == "custom here"
