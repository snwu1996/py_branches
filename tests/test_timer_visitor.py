#!/usr/bin/env python
import time
import random

import py_trees

from py_branches.pause import PauseUniform
from py_branches.visitors import TimerVisitor


def test_timer_visitor_measures_pause_uniform_running_duration():
    random.seed(0)
    pause = PauseUniform('pause', 0.2, 0.3)
    visitor = TimerVisitor()

    while pause.status != py_trees.common.Status.SUCCESS:
        pause.tick_once()
        visitor.run(pause)
        if pause.status == py_trees.common.Status.SUCCESS:
            break
        time.sleep(0.01)

    duration = visitor.get_duration(pause)
    assert duration is not None
    assert 0.15 < duration < 0.45, f'duration={duration}'


def test_timer_visitor_returns_none_for_never_running_behaviour():
    success = py_trees.behaviours.Success('s')
    visitor = TimerVisitor()

    success.tick_once()
    visitor.run(success)

    assert visitor.get_duration(success) is None


def test_timer_visitor_accumulates_across_running_ticks():
    counter = py_trees.behaviours.TickCounter('tc', 3, py_trees.common.Status.SUCCESS)
    visitor = TimerVisitor()

    sleep_per_tick = 0.1
    while counter.status != py_trees.common.Status.SUCCESS:
        counter.tick_once()
        visitor.run(counter)
        if counter.status == py_trees.common.Status.SUCCESS:
            break
        time.sleep(sleep_per_tick)

    duration = visitor.get_duration(counter)
    assert duration is not None
    # Three RUNNING ticks separated by ~0.1s sleeps -> ~0.3s.
    assert 0.25 < duration < 0.5, f'duration={duration}'


def test_timer_visitor_integrates_with_behaviour_tree():
    random.seed(1)
    pause = PauseUniform('pause', 0.1, 0.2)
    tree = py_trees.trees.BehaviourTree(pause)
    visitor = TimerVisitor()
    tree.add_visitor(visitor)

    while pause.status != py_trees.common.Status.SUCCESS:
        tree.tick()
        if pause.status == py_trees.common.Status.SUCCESS:
            break
        time.sleep(0.01)

    duration = visitor.get_duration(pause)
    assert duration is not None
    assert 0.05 < duration < 0.35, f'duration={duration}'
