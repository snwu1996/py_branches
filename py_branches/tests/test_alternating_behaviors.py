#!/usr/bin/env python

import pytest
import py_trees
import py_trees.console as console

from py_branches.alternating_behaviors import ActivateBehavior
from py_branches.alternating_behaviors import RunAlternating


class GuardedBehavior(py_trees.behaviour.Behaviour):
    def __init__(self, name='guarded_behavior'):
        super(GuardedBehavior, self).__init__(name=name)
        self.reset()

    def reset(self):
        self.initialised = False
        self.updated = False
        self.status = py_trees.Status.INVALID

    def initialise(self):
        print('\t GuardedBehavior initialising')
        self.initialised = True

    def update(self):
        print('\t GuardedBehavior updating')
        self.updated = True
        return py_trees.Status.SUCCESS

def create_guarded_behaviors(activate_list):
    guarded_behaviors = []
    guarded_behavior_decorators = []
    for i, activate in enumerate(activate_list):
        guarded_behavior_i = GuardedBehavior(name=f'guarded_behavior_{i}')
        activate_guarded_behavior_i = \
            ActivateBehavior(name=f'activate_guarded_behavior_{i}',
                             child=guarded_behavior_i,
                             activate=activate)
        guarded_behaviors.append(guarded_behavior_i)
        guarded_behavior_decorators.append(activate_guarded_behavior_i)

    return guarded_behaviors, guarded_behavior_decorators

def check_guarded_behaviors(activate_list, guarded_behaviors):
    print(console.bold + f'{activate_list}: {[b.name for b in guarded_behaviors]}')
    for i, (activate, guarded_behavior_i) in enumerate(zip(activate_list, guarded_behaviors)):
        print(console.bold + f'guarded_behavior_{i}.initialised == {activate}')
        assert guarded_behavior_i.initialised == activate
        print(console.bold + f'guarded_behavior_{i}.updated == {activate}')
        assert guarded_behavior_i.updated == activate
        if activate:
            print(console.bold + f'guarded_behavior_{i}.status == py_trees.Status.SUCCESS')
            assert guarded_behavior_i.status == py_trees.Status.SUCCESS
        else:
            print(console.bold + f'guarded_behavior_{i}.status == py_trees.Status.INVALID')
            assert guarded_behavior_i.status == py_trees.Status.INVALID

def test_activate_decorator_single():
    print(console.bold + 'test_activate_decorator_single')
    root = py_trees.composites.Selector('root')
    guarded_behavior = GuardedBehavior()
    activate_guarded_behavior = \
        ActivateBehavior(name='activate_guarded_behavior',
                         child=guarded_behavior,
                         activate=True)
    root.add_children([activate_guarded_behavior])
    py_trees.display.print_ascii_tree(root)
    visitor = py_trees.visitors.DebugVisitor()

    # Test activated behavior
    py_trees.tests.tick_tree(root, 1, 1, visitor, print_snapshot=True)
    print("\n--------- Single Behavior - Activated ---------")
    print(console.bold + 'guarded_behavior.initialised == True')
    assert guarded_behavior.initialised == True
    print(console.bold + 'guarded_behavior.updated == True')
    assert guarded_behavior.updated == True
    print(console.bold + 'guarded_behavior.status == py_trees.Status.SUCCESS')
    assert guarded_behavior.status == py_trees.Status.SUCCESS

    # Test deactivated behavior
    activate_guarded_behavior.activate = False
    guarded_behavior.reset()
    py_trees.tests.tick_tree(root, 2, 2, visitor, print_snapshot=True)
    print("\n--------- Single Behavior - Deactivated ---------")
    print(console.bold + 'guarded_behavior.initialised == False')
    assert guarded_behavior.initialised == False
    print(console.bold + 'guarded_behavior.updated == False')
    assert guarded_behavior.updated == False
    print(console.bold + 'guarded_behavior.status == py_trees.Status.INVALID')
    assert guarded_behavior.status == py_trees.Status.INVALID

def test_activate_decorator_multiple():
    print(console.bold + 'test_activate_decorator_multiple')
    root = py_trees.composites.Selector('root')
    activate_list = [False, False, True]
    guarded_behaviors, guarded_behavior_decorators = create_guarded_behaviors(activate_list)
    root.add_children(guarded_behavior_decorators)
    py_trees.display.print_ascii_tree(root)
    visitor = py_trees.visitors.DebugVisitor()

    # Test activated behavior
    py_trees.tests.tick_tree(root, 1, 1, visitor, print_snapshot=True)
    print("\n--------- Multiple - Activated ---------")
    check_guarded_behaviors(activate_list, guarded_behaviors)
    print(console.bold + 'root.status == py_trees.Status.SUCCESS')
    assert root.status == py_trees.Status.SUCCESS

    # Test deactivate behaviour
    new_activate_list = [False, False, False]
    for activate, guarded_behavior_i, activate_guarded_behavior_i in \
            zip(new_activate_list, guarded_behaviors, guarded_behavior_decorators):
        guarded_behavior_i.reset()
        guarded_behavior_i.status = py_trees.Status.INVALID
        activate_guarded_behavior_i.activate = activate
    py_trees.tests.tick_tree(root, 2, 2, visitor, print_snapshot=True)
    print("\n--------- Multiple - Activated ---------")
    check_guarded_behaviors(new_activate_list, guarded_behaviors)
    print(console.bold + 'root.status == py_trees.Status.INVALID')
    assert root.status == py_trees.Status.FAILURE

def test_alternating_decorator():
    print(console.bold + 'test_alternating_decorator')
    root = py_trees.composites.Selector('root')
    guarded_behaviors, guarded_behavior_decorators = create_guarded_behaviors([False, False, False])
    counts = [1, 2, 3]
    run_alternating = RunAlternating('run_alternating', guarded_behaviors, counts=counts)
    root.add_children([run_alternating])
    py_trees.display.print_ascii_tree(root)
    visitor = py_trees.visitors.DebugVisitor()
 
    print("\n--------- SUCCESS ---------")
    tick_num = 1
    for i, c in enumerate(counts):
        activate_list = [False] * len(guarded_behavior_decorators)
        activate_list[i] = True
        for _ in range(c):
            [b.reset() for b in guarded_behaviors]
            py_trees.tests.tick_tree(root, tick_num, tick_num, visitor, print_snapshot=True)
            check_guarded_behaviors(activate_list, guarded_behaviors)
            print(console.bold + 'run_alternating.status == py_trees.Status.SUCCESS')
            assert run_alternating.status == py_trees.Status.SUCCESS
            tick_num += 1
