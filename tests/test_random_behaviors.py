#!/usr/bin/env python

import random
random.seed(0)
import py_trees

from py_branches.random import RandomRun
from py_branches.random import random_selector


def test_random_run():
    bb = py_trees.blackboard.Client()
    bb.register_key(key='foo', access=py_trees.common.Access.WRITE)
    bb.foo = 1.0
    assert(bb.exists("foo"))
    assert(bb.foo == 1.0)

    set_bb = py_trees.behaviours.SetBlackboardVariable('set_bb','foo', 10.0, True)

    print('\n---------------100% probability of success---------------')
    random_run_100_success = RandomRun(set_bb, 'random_run_100_success', 1.0)
    random_run_100_success.tick_once()
    assert(bb.exists("foo"))
    assert(bb.foo == 10.0)

    print('---------------  0% probability of success---------------')
    bb.foo = 1.0
    random_run_0_success = RandomRun(set_bb, 'random_run_0_success', 0.0)
    random_run_0_success.tick_once()
    assert(bb.exists("foo"))
    assert(bb.foo == 1.0)

    print('--------------- 50% probability of success---------------')
    iterations = 10
    random.seed(0)
    expected_random = [random.random() for _ in range(iterations)]
    expected_foo = [10.0 if rand <= 0.5 else 1.0 for rand in expected_random]
    random.seed(0)
    random_run_50_success = RandomRun(set_bb, 'random_run_50_success', 0.5)
    for i in range(iterations):
        bb.foo = 1.0
        random_run_50_success.tick_once()
        assert(bb.exists("foo"))
        assert(bb.foo == expected_foo[i])
        expected_status = py_trees.common.Status.SUCCESS if expected_foo[i] == 10.0 else \
                          py_trees.common.Status.FAILURE
        assert(random_run_50_success.status == expected_status)

    print('--------------- 50% probability of success sis-----------')
    random.seed(0)
    random_run_50_success_sis = RandomRun(set_bb, 'random_run_50_success_sis', 0.5, success_if_skip=True)
    for i in range(iterations):
        bb.foo = 1.0
        random_run_50_success_sis.tick_once()
        assert(bb.exists("foo"))
        assert(bb.foo == expected_foo[i])
        assert(random_run_50_success_sis.status == py_trees.common.Status.SUCCESS)

def test_random_selector():
    bb = py_trees.blackboard.Client()
    bb.register_key(key='foo', access=py_trees.common.Access.WRITE)
    bb.foo = 1.0
    assert(bb.exists("foo"))
    assert(bb.foo == 1.0)

    set_bb_1 = py_trees.behaviours.SetBlackboardVariable('set_bb','foo', 1.0, True)
    set_bb_10 = py_trees.behaviours.SetBlackboardVariable('set_bb','foo', 10.0, True)
    set_bb_100 = py_trees.behaviours.SetBlackboardVariable('set_bb','foo', 100.0, True)
    samples = 100

    rs = random_selector('random_selector' ,[set_bb_1, set_bb_10, set_bb_100], [0.2, 0.3, 0.5])
    random.seed(0)
    foo_counts = {1.0: 0, 10.0: 0, 100.0: 0}
    for _ in range(samples):
        rs.tick_once()
        foo_counts[bb.foo] += 1
    assert(foo_counts == {1.0: 15, 10.0: 30, 100.0: 55})