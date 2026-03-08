#!/usr/bin/env python

import py_trees

from py_branches.counter import Counter


_r = py_trees.common.Status.RUNNING
_s = py_trees.common.Status.SUCCESS
_f = py_trees.common.Status.FAILURE
_i = py_trees.common.Status.INVALID


class TrackingBehavior(py_trees.behaviour.Behaviour):
    '''Returns a fixed status and tracks how many times it has been ticked.'''
    def __init__(self, name, return_status):
        super().__init__(name=name)
        self._return_status = return_status
        self.tick_count = 0

    def update(self):
        self.tick_count += 1
        return self._return_status


def test_counter_run_once():
    '''num_runs=1: child runs once, then permanently SUCCESS.'''
    child = TrackingBehavior('child', _s)
    counter = Counter(child, name='counter', num_runs=1)

    counter.tick_once()
    assert counter.status == _s
    assert child.tick_count == 1
    assert counter._done

    # Permanently done: child never re-run
    for _ in range(5):
        counter.tick_once()
        assert counter.status == _s
        assert child.tick_count == 1


def test_counter_run_three_times():
    '''Child runs exactly 3 times, then returns SUCCESS permanently.'''
    child = TrackingBehavior('child', _s)
    counter = Counter(child, name='counter', num_runs=3)

    # Run 1 and 2: RUNNING (more runs remain)
    counter.tick_once()
    assert counter.status == _r
    assert child.tick_count == 1

    counter.tick_once()
    assert counter.status == _r
    assert child.tick_count == 2

    # Run 3: done
    counter.tick_once()
    assert counter.status == _s
    assert child.tick_count == 3
    assert counter._done

    # Permanently done
    counter.tick_once()
    assert counter.status == _s
    assert child.tick_count == 3


def test_counter_completion_status_failure():
    '''completion_status=FAILURE: permanently returns FAILURE after num_runs.'''
    child = TrackingBehavior('child', _s)
    counter = Counter(child, name='counter', num_runs=2,
                      completion_status=py_trees.common.Status.FAILURE)

    counter.tick_once()
    assert counter.status == _r  # first run, more remain

    counter.tick_once()
    assert counter.status == _f  # done; permanently FAILURE

    counter.tick_once()
    assert counter.status == _f
    assert child.tick_count == 2


def test_counter_counts_failure_completions():
    '''Child FAILURE also counts toward num_runs.'''
    child = TrackingBehavior('child', _f)
    counter = Counter(child, name='counter', num_runs=2)

    counter.tick_once()
    assert counter.status == _r  # failure counted, 1 more run left

    counter.tick_once()
    assert counter.status == _s  # 2 runs complete; completion_status=SUCCESS


def test_counter_running_child_not_counted():
    '''RUNNING ticks do not count toward num_runs.'''
    class RunThenSucceed(py_trees.behaviour.Behaviour):
        def __init__(self):
            super().__init__(name='run_then_succeed')
            self._ticks = 0

        def initialise(self):
            self._ticks = 0

        def update(self):
            self._ticks += 1
            return _r if self._ticks < 3 else _s

    child = RunThenSucceed()
    counter = Counter(child, name='counter', num_runs=2)

    # Ticks 1-2: child is RUNNING — not counted
    counter.tick_once()
    assert counter.status == _r
    assert counter._runs_completed == 0

    counter.tick_once()
    assert counter.status == _r
    assert counter._runs_completed == 0

    # Tick 3: child completes (SUCCESS) — run 1 counted, child reset
    counter.tick_once()
    assert counter.status == _r   # 1 run done, 1 more to go
    assert counter._runs_completed == 1

    # Ticks 4-5: child RUNNING again (re-initialised after reset)
    counter.tick_once()
    assert counter.status == _r
    assert counter._runs_completed == 1

    counter.tick_once()
    assert counter.status == _r
    assert counter._runs_completed == 1

    # Tick 6: child completes — run 2 counted; done
    counter.tick_once()
    assert counter.status == _s
    assert counter._runs_completed == 2


def test_counter_reset_allows_recount():
    '''reset() clears the count so the child runs num_runs times again.'''
    child = TrackingBehavior('child', _s)
    counter = Counter(child, name='counter', num_runs=2)

    counter.tick_once()  # run 1
    counter.tick_once()  # run 2; done
    assert counter._done
    assert child.tick_count == 2

    counter.reset()
    assert not counter._done
    assert counter._runs_completed == 0

    counter.tick_once()  # run 1 again
    assert counter.status == _r
    assert child.tick_count == 3

    counter.tick_once()  # run 2 again; done
    assert counter.status == _s
    assert child.tick_count == 4


def test_counter_done_persists_across_reentry():
    '''_done is not cleared by initialise(); it persists until reset().'''
    child = TrackingBehavior('child', _s)
    counter = Counter(child, name='counter', num_runs=1)

    counter.tick_once()
    assert counter._done

    # Simulate external stop (e.g. parent aborted)
    counter.stop(py_trees.common.Status.INVALID)
    assert counter._done  # persists

    # Re-entry: still done, child not re-run
    counter.tick_once()
    assert counter.status == _s
    assert child.tick_count == 1
