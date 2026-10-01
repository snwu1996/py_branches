#!/usr/bin/env python
import logging
import random
import re
import time

import py_trees

from py_branches.clock import ManualClock
from py_branches.pause import PauseUniform
from py_branches.visitors import TimerVisitor

_DURATION_RE = re.compile(r"ran for (\d+\.\d+)s")


def _extract_duration(caplog, behaviour_name):
    for record in caplog.records:
        if f"[timer] {behaviour_name} ran for" in record.message:
            match = _DURATION_RE.search(record.message)
            if match:
                return float(match.group(1))
    return None


def test_timer_visitor_measures_pause_uniform_running_duration(caplog):
    caplog.set_level(logging.INFO, logger="py_branches.visitors")
    random.seed(0)
    pause = PauseUniform("pause", 0.2, 0.3)
    visitor = TimerVisitor()

    while pause.status != py_trees.common.Status.SUCCESS:
        pause.tick_once()
        visitor.run(pause)
        if pause.status == py_trees.common.Status.SUCCESS:
            break
        time.sleep(0.01)

    duration = _extract_duration(caplog, "pause")
    assert duration is not None
    assert 0.15 < duration < 0.45, f"duration={duration}"


def test_timer_visitor_does_not_log_for_never_running_behaviour(caplog):
    caplog.set_level(logging.INFO, logger="py_branches.visitors")
    success = py_trees.behaviours.Success("s")
    visitor = TimerVisitor()

    success.tick_once()
    visitor.run(success)

    assert _extract_duration(caplog, "s") is None


def test_timer_visitor_accumulates_across_running_ticks(caplog):
    caplog.set_level(logging.INFO, logger="py_branches.visitors")
    counter = py_trees.behaviours.TickCounter("tc", 3, py_trees.common.Status.SUCCESS)
    visitor = TimerVisitor()

    sleep_per_tick = 0.1
    while counter.status != py_trees.common.Status.SUCCESS:
        counter.tick_once()
        visitor.run(counter)
        if counter.status == py_trees.common.Status.SUCCESS:
            break
        time.sleep(sleep_per_tick)

    duration = _extract_duration(caplog, "tc")
    assert duration is not None
    # Three RUNNING ticks separated by ~0.1s sleeps -> ~0.3s.
    assert 0.25 < duration < 0.5, f"duration={duration}"


def test_timer_visitor_integrates_with_behaviour_tree(caplog):
    caplog.set_level(logging.INFO, logger="py_branches.visitors")
    random.seed(1)
    pause = PauseUniform("pause", 0.1, 0.2)
    tree = py_trees.trees.BehaviourTree(pause)
    visitor = TimerVisitor()
    tree.add_visitor(visitor)

    while pause.status != py_trees.common.Status.SUCCESS:
        tree.tick()
        if pause.status == py_trees.common.Status.SUCCESS:
            break
        time.sleep(0.01)

    duration = _extract_duration(caplog, "pause")
    assert duration is not None
    assert 0.05 < duration < 0.35, f"duration={duration}"


def test_timer_visitor_measures_exact_duration_on_manual_clock(caplog):
    """No tolerance window needed: the logged duration is the clock's delta."""
    clock = ManualClock()
    visitor = TimerVisitor(clock=clock)
    behaviour = py_trees.behaviours.Running(name="running")

    behaviour.tick_once()
    visitor.run(behaviour)  # first RUNNING sighting starts the timer

    clock.advance(12.5)
    behaviour.stop(py_trees.common.Status.SUCCESS)

    with caplog.at_level(logging.INFO):
        visitor.run(behaviour)

    assert _extract_duration(caplog, "running") == 12.5


def test_timer_visitor_accumulates_across_ticks_on_manual_clock(caplog):
    """The duration spans every RUNNING tick, not just the last gap."""
    clock = ManualClock()
    visitor = TimerVisitor(clock=clock)
    behaviour = py_trees.behaviours.Running(name="running")

    for _ in range(4):
        behaviour.tick_once()
        visitor.run(behaviour)
        clock.advance(0.25)

    behaviour.stop(py_trees.common.Status.SUCCESS)
    with caplog.at_level(logging.INFO):
        visitor.run(behaviour)

    assert _extract_duration(caplog, "running") == 1.0
