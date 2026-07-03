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

    set_bb = py_trees.behaviours.SetBlackboardVariable(name='set_bb', variable_name='foo', variable_value=10.0, overwrite=True)

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

    set_bb_1 = py_trees.behaviours.SetBlackboardVariable(name='set_bb_1', variable_name='foo', variable_value=1.0, overwrite=True)
    set_bb_10 = py_trees.behaviours.SetBlackboardVariable(name='set_bb_10', variable_name='foo', variable_value=10.0, overwrite=True)
    set_bb_100 = py_trees.behaviours.SetBlackboardVariable(name='set_bb_100', variable_name='foo', variable_value=100.0, overwrite=True)
    samples = 100

    rs = random_selector('random_selector' ,[set_bb_1, set_bb_10, set_bb_100], [0.2, 0.3, 0.5])
    random.seed(0)
    foo_counts = {1.0: 0, 10.0: 0, 100.0: 0}
    for _ in range(samples):
        rs.tick_once()
        foo_counts[bb.foo] += 1
    assert(foo_counts == {1.0: 15, 10.0: 29, 100.0: 56})


class _RunningThenSuccess(py_trees.behaviour.Behaviour):
    """Returns RUNNING for `running_ticks` ticks then SUCCESS."""
    def __init__(self, name, running_ticks):
        super().__init__(name=name)
        self._running_ticks = running_ticks
        self._ticked = 0

    def initialise(self):
        self._ticked = 0

    def update(self):
        self._ticked += 1
        if self._ticked <= self._running_ticks:
            return py_trees.common.Status.RUNNING
        return py_trees.common.Status.SUCCESS


def test_random_selector_locks_branch_while_running():
    """Once a branch is chosen, it must not be re-rolled while RUNNING.

    Regression: with memory=False the inner Selector re-ticks from child 0
    on every tree tick, causing RandomRun to re-roll each tick. If an early
    child's re-roll flips from skip->run mid-flight, the previously-running
    later child gets invalidated and a different branch takes over — both
    branches end up executing within the same logical selection cycle.

    We run many trials with different seeds. For each cycle, at most one
    branch should have been ticked.
    """
    trials = 200
    running_ticks = 5
    for seed in range(trials):
        random.seed(seed)
        first = _RunningThenSuccess(name='first', running_ticks=running_ticks)
        second = _RunningThenSuccess(name='second', running_ticks=running_ticks)
        rs = random_selector('rs', [first, second], [0.5, 0.5])

        # Tick until one full selection cycle completes (SUCCESS).
        for _ in range(running_ticks + 5):
            rs.tick_once()
            if rs.status == py_trees.common.Status.SUCCESS:
                break
        else:
            raise AssertionError(f'seed={seed}: selector did not complete')

        ran_first = first._ticked > 0
        ran_second = second._ticked > 0
        assert ran_first ^ ran_second, (
            f'seed={seed}: exactly one branch should run per selection cycle, '
            f'but first._ticked={first._ticked} second._ticked={second._ticked}'
        )