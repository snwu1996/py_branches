#!/usr/bin/env python
from __future__ import absolute_import
from __future__ import print_function
import py_trees
from py_branches.blackboard_behaviors import IncrementBlackboardVariable


def test_increment_blackboard_variable():
    print(py_trees.console.bold + "\n***********************************************" + py_trees.console.reset)
    print(py_trees.console.bold + "* Increment Blackboard Variable" + py_trees.console.reset)
    print(py_trees.console.bold + "*************************************************\n" + py_trees.console.reset)
    blackboard = py_trees.Blackboard()
    set_foo = py_trees.blackboard.SetBlackboardVariable(name="Set Foo", variable_name="foo", variable_value=1)
    print(" - Set 'foo'")
    set_foo.tick_once()
    print("\n%s" % blackboard)
    print(" - Assert blackboard.foo=1")
    assert(hasattr(blackboard, "foo"))
    assert(blackboard.foo == 1)
    print(" - Assert set_foo.status == SUCCESS")
    assert(set_foo.status == py_trees.Status.SUCCESS) 
    
    increment_foo = IncrementBlackboardVariable(name="Increment Foo", variable_name="foo", increment_by=1)
    print(" - Increment 'foo'")
    increment_foo.tick_once()
    print(" - Assert blackboard.foo=2")
    assert(hasattr(blackboard, "foo"))
    assert(blackboard.foo == 2)
    print(" - Assert set_foo.status == SUCCESS")
    assert(increment_foo.status == py_trees.Status.SUCCESS) 
