#!/usr/bin/env python

import pytest
import py_trees
import py_trees.console as console
import random
from py_branches.alternating import ActivateBehavior
from py_branches.alternating import RunEveryRange
from py_branches.alternating import run_alternating
from py_branches.alternating import RunEveryX


_r = py_trees.common.Status.RUNNING
_s = py_trees.common.Status.SUCCESS
_f = py_trees.common.Status.FAILURE
_i = py_trees.common.Status.INVALID

class GuardedBehavior(py_trees.behaviour.Behaviour):
    def __init__(self, name='guarded_behavior'):
        super(GuardedBehavior, self).__init__(name=name)
        self.reset()

    def reset(self):
        self.initialised = False
        self.updated = False
        self.status = _i

    def initialise(self):
        print('\t GuardedBehavior initialising')
        self.initialised = True

    def update(self):
        print('\t GuardedBehavior updating')
        self.updated = True
        return _s

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

def check_guarded_behavior(guarded_behavior: GuardedBehavior,
                           initialised: bool,
                           updated: bool,
                           status: py_trees.common.Status):
    assert guarded_behavior.initialised == initialised
    assert guarded_behavior.updated == updated
    assert guarded_behavior.status == status

def check_guarded_behaviors(activate_list, guarded_behaviors):
    print(console.bold + f'{activate_list}: {[b.name for b in guarded_behaviors]}')
    for i, (activate, guarded_behavior_i) in enumerate(zip(activate_list, guarded_behaviors)):
        assert guarded_behavior_i.initialised == activate
        assert guarded_behavior_i.updated == activate
        if activate:
            assert guarded_behavior_i.status == _s
        else:
            assert guarded_behavior_i.status == _i

def test_activate_decorator_single():
    print(console.bold + 'test_activate_decorator_single')
    root = py_trees.composites.Selector('root', False)
    guarded_behavior = GuardedBehavior()
    activate_guarded_behavior = \
        ActivateBehavior(name='activate_guarded_behavior',
                         child=guarded_behavior,
                         activate=True)
    root.add_children([activate_guarded_behavior])
    py_trees.display.ascii_tree(root)
    visitor = py_trees.visitors.DebugVisitor()

    # Test activated behavior
    py_trees.tests.tick_tree(root, 1, 1, visitors=[visitor], print_snapshot=True)
    print("\n--------- Single Behavior - Activated ---------")
    check_guarded_behavior(guarded_behavior, True, True, _s)
    assert activate_guarded_behavior.status == _s

    # Test deactivated behavior
    activate_guarded_behavior.activate = False
    guarded_behavior.reset()
    py_trees.tests.tick_tree(root, 2, 2, visitors=[visitor], print_snapshot=True)
    print("\n--------- Single Behavior - Deactivated ---------")
    check_guarded_behavior(guarded_behavior, False, False, _i)
    assert activate_guarded_behavior.status == _f

    activate_guarded_behavior._success_if_skip = True
    guarded_behavior.reset()
    py_trees.tests.tick_tree(root, 3, 3, visitors=[visitor], print_snapshot=True)
    print("\n--------- Single Behavior - Always Success ---------")
    check_guarded_behavior(guarded_behavior, False, False, _i)
    assert activate_guarded_behavior.status == _s

def test_activate_decorator_multiple():
    print(console.bold + 'test_activate_decorator_multiple')
    root = py_trees.composites.Selector('root', False)
    activate_list = [False, False, True]
    guarded_behaviors, guarded_behavior_decorators = create_guarded_behaviors(activate_list)
    root.add_children(guarded_behavior_decorators)
    py_trees.display.ascii_tree(root)
    visitor = py_trees.visitors.DebugVisitor()

    # Test activated behavior
    py_trees.tests.tick_tree(root, 1, 1, visitors=[visitor], print_snapshot=True)
    print("\n--------- Multiple - Activated ---------")
    check_guarded_behaviors(activate_list, guarded_behaviors)
    assert root.status == _s

    # Test deactivate behaviour
    new_activate_list = [False, False, False]
    for activate, guarded_behavior_i, activate_guarded_behavior_i in \
            zip(new_activate_list, guarded_behaviors, guarded_behavior_decorators):
        guarded_behavior_i.reset()
        guarded_behavior_i.status = _i
        activate_guarded_behavior_i.activate = activate
    py_trees.tests.tick_tree(root, 2, 2, visitors=[visitor], print_snapshot=True)
    print("\n--------- Multiple - Activated ---------")
    check_guarded_behaviors(new_activate_list, guarded_behaviors)
    assert root.status == _f

def test_alternating_behaviors():
    print(console.bold + 'test_alternating_behaviors')
    root = py_trees.composites.Selector('root', False)
    guarded_behaviors, guarded_behavior_decorators = create_guarded_behaviors([False, False, False])
    counts = [1, 2, 3]
    run_alternating_test = run_alternating('run_alternating', guarded_behaviors, counts=counts)
    root.add_children([run_alternating_test])
    py_trees.display.ascii_tree(root)
    visitor = py_trees.visitors.DebugVisitor()
 
    print("\n--------- Alternating Behaviors - Success ---------")
    tick_num = 1
    for i, c in enumerate(counts):
        activate_list = [False] * len(guarded_behavior_decorators)
        activate_list[i] = True
        for _ in range(c):
            [b.reset() for b in guarded_behaviors]
            py_trees.tests.tick_tree(root, tick_num, tick_num, visitors=[visitor], print_snapshot=True)
            check_guarded_behaviors(activate_list, guarded_behaviors)
            assert run_alternating_test.status == _s
            tick_num += 1

def test_run_every_x_decorator():
    print(console.bold + 'test_run_every_x_decorator')
    root = py_trees.composites.Selector('root', False)
    guarded_behavior = GuardedBehavior()
    every_x_range = (3,3)
    run_every_x_guarded_behavior = \
        RunEveryX(name='run_every_x_guarded_behavior',
                  child=guarded_behavior,
                  every_x_range=every_x_range)
    root.add_children([run_every_x_guarded_behavior])
    py_trees.display.ascii_tree(root)
    visitor = py_trees.visitors.DebugVisitor()

    print("\n--------- Run Every X - Deterministic ---------")
    for i in range(2*every_x_range[0]):
        guarded_behavior.reset()
        py_trees.tests.tick_tree(root, i, i, visitors=[visitor], print_snapshot=True)
        if (i+1)%every_x_range[0] == 0:
            check_guarded_behavior(guarded_behavior, True, True, _s)
            assert run_every_x_guarded_behavior.status == _s
        else:
            check_guarded_behavior(guarded_behavior, False, False, _i)
            assert run_every_x_guarded_behavior.status == _f

    print("\n--------- Run Every X - Always Success ---------")
    run_every_x_guarded_behavior._success_if_skip = True
    for i in range(2*every_x_range[0]):
        guarded_behavior.reset()
        py_trees.tests.tick_tree(root, i, i, visitors=[visitor], print_snapshot=True)
        if (i+1)%every_x_range[0] == 0:
            check_guarded_behavior(guarded_behavior, True, True, _s)
        else:
            check_guarded_behavior(guarded_behavior, False, False, _i)
        assert run_every_x_guarded_behavior.status == _s
    run_every_x_guarded_behavior._success_if_skip = False

    print("\n--------- Run Every X - Random ---------")
    run_every_x_guarded_behavior._every_x_range = (1,5)
    
    # Using random.seed(0) we can garentee when the guarded_behavior will be enabled.
    iterations = 20
    random.seed(0)
    expected_successful_is = []
    i = 0
    while True:
        i += random.randint(*run_every_x_guarded_behavior._every_x_range)
        if i < iterations:
            expected_successful_is.append(i)
        else:
            break

    # We pre-calculated the expected indices at which the guarded_behavior will run.
    random.seed(0)
    run_every_x_guarded_behavior._cycles_remaining = \
        random.randint(*run_every_x_guarded_behavior._every_x_range)
    for i in range(iterations):
        guarded_behavior.reset()
        py_trees.tests.tick_tree(root, i, i, visitors=[visitor], print_snapshot=True)
        if i in expected_successful_is:
            check_guarded_behavior(guarded_behavior, True, True, _s)
            assert run_every_x_guarded_behavior.status == _s
        else:
            check_guarded_behavior(guarded_behavior, False, False, _i)
            assert run_every_x_guarded_behavior.status == _f

def test_run_every_range_decorator():
    print(console.bold + 'test_run_every_x_decorator')
    root = py_trees.composites.Selector('root', False)
    guarded_behavior = GuardedBehavior()
    max_range = 10
    run_range = (3, 5)
    run_every_range_behavior = RunEveryRange(guarded_behavior, 'run_every_range', max_range, run_range)
    root.add_children([run_every_range_behavior])
    py_trees.display.ascii_tree(root)
    visitor = py_trees.visitors.DebugVisitor()

    for i in range(1, max_range+1):
        guarded_behavior.reset()
        py_trees.tests.tick_tree(root, i, i, visitors=[visitor], print_snapshot=True)
        if run_range[0] <= i <= run_range[1]:
            check_guarded_behavior(guarded_behavior, True, True, _s)
            assert run_every_range_behavior.status == _s
        else:
            check_guarded_behavior(guarded_behavior, False, False, _i)
            assert run_every_range_behavior.status == _f
