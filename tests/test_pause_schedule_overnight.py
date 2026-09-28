#!/usr/bin/env python
"""Overnight (midnight-wrapping) window handling in PauseSchedule.

A window whose start is later than its stop wraps past midnight, which takes
a different branch both when matching the window and when computing the wait.
The real clock cannot exercise those branches reliably -- an overnight test
built on the real time of day would behave differently depending on the hour CI
runs at, and the 'now is after start' case computes a wait of up to ~24 hours.
So these tests hand PauseSchedule a ManualClock pinned to the hour under test.
"""

import datetime

import py_trees
import pytest

from py_branches.clock import ManualClock
from py_branches.pause import PauseSchedule


@pytest.fixture
def clock_at():
    """Return a factory for a ManualClock pinned to a local time of day."""

    def _at(hour, minute, second):
        now_dt = datetime.datetime.combine(
            datetime.date.today(), datetime.time(hour, minute, second)
        )
        return ManualClock(start=now_dt.timestamp())

    return _at


def _schedule(start, stop):
    """One zero-variance schedule entry, as load_schedule_file would build it."""
    return [
        {
            "start_pause_time": start,
            "stop_pause_time": stop,
            "variance_time": datetime.time(0, 0, 0),
            "start_plus_variance_time": start,
            "stop_plus_variance_time": stop,
        }
    ]


def test_overnight_window_matches_before_midnight(clock_at):
    clock = clock_at(23, 30, 0)
    schedule = _schedule(datetime.time(23, 0, 0), datetime.time(1, 0, 0))
    pause_schedule = PauseSchedule("pause_schedule", schedule, clock=clock)

    pause_schedule.tick_once()

    assert pause_schedule.status == py_trees.common.Status.RUNNING
    # 23:30 -> 01:00 the next day is 1.5 hours.
    assert pause_schedule._t_wait == 1.5 * 60 * 60


def test_overnight_window_matches_after_midnight(clock_at):
    clock = clock_at(0, 30, 0)
    schedule = _schedule(datetime.time(23, 0, 0), datetime.time(1, 0, 0))
    pause_schedule = PauseSchedule("pause_schedule", schedule, clock=clock)

    pause_schedule.tick_once()

    assert pause_schedule.status == py_trees.common.Status.RUNNING
    # Already past midnight: 00:30 -> 01:00 is half an hour, no day rollover.
    assert pause_schedule._t_wait == 30 * 60


def test_overnight_window_wait_spans_midnight_exactly(clock_at):
    clock = clock_at(23, 59, 59)
    schedule = _schedule(datetime.time(23, 0, 0), datetime.time(0, 0, 1))
    pause_schedule = PauseSchedule("pause_schedule", schedule, clock=clock)

    pause_schedule.tick_once()

    assert pause_schedule.status == py_trees.common.Status.RUNNING
    # 23:59:59 -> 00:00:01 is two seconds. This pins the '+ 1' that turns
    # 23:59:59 into a full day's worth of seconds.
    assert pause_schedule._t_wait == 2


def test_overnight_window_does_not_match_midday(clock_at):
    clock = clock_at(12, 0, 0)
    schedule = _schedule(datetime.time(23, 0, 0), datetime.time(1, 0, 0))
    pause_schedule = PauseSchedule("pause_schedule", schedule, clock=clock)

    pause_schedule.tick_once()

    # Midday falls in the gap between stop (01:00) and start (23:00).
    assert pause_schedule.status == py_trees.common.Status.SUCCESS
    assert pause_schedule._t_wait is None


def test_overnight_window_boundaries_are_exclusive(clock_at):
    # Exactly on start: the match uses `now > start`, so this is outside.
    clock = clock_at(23, 0, 0)
    schedule = _schedule(datetime.time(23, 0, 0), datetime.time(1, 0, 0))
    pause_schedule = PauseSchedule("pause_schedule", schedule, clock=clock)

    pause_schedule.tick_once()

    assert pause_schedule.status == py_trees.common.Status.SUCCESS


def test_overnight_window_stop_boundary_is_exclusive(clock_at):
    # Exactly on stop: `now < stop` is false and `now > start` is false.
    clock = clock_at(1, 0, 0)
    schedule = _schedule(datetime.time(23, 0, 0), datetime.time(1, 0, 0))
    pause_schedule = PauseSchedule("pause_schedule", schedule, clock=clock)

    pause_schedule.tick_once()

    assert pause_schedule.status == py_trees.common.Status.SUCCESS


def test_same_day_window_wait_does_not_roll_over(clock_at):
    clock = clock_at(12, 0, 0)
    schedule = _schedule(datetime.time(11, 0, 0), datetime.time(13, 0, 0))
    pause_schedule = PauseSchedule("pause_schedule", schedule, clock=clock)

    pause_schedule.tick_once()

    assert pause_schedule.status == py_trees.common.Status.RUNNING
    # The non-wrapping counterpart: one hour, no day added.
    assert pause_schedule._t_wait == 60 * 60


def test_overnight_window_completes_after_wait_elapses(clock_at):
    # A two-second wait that straddles midnight, waited out on the manual clock.
    clock = clock_at(23, 59, 59)
    schedule = _schedule(datetime.time(23, 0, 0), datetime.time(0, 0, 1))
    pause_schedule = PauseSchedule("pause_schedule", schedule, clock=clock)

    pause_schedule.tick_once()
    assert pause_schedule.status == py_trees.common.Status.RUNNING

    # The countdown is measured in elapsed clock time, so advancing past
    # _t_wait ends the pause -- instantly, and without a real 2.2s sleep.
    clock.advance(2.2)
    pause_schedule.tick_once()
    assert pause_schedule.status == py_trees.common.Status.SUCCESS


def test_overnight_window_stays_running_until_wait_elapses(clock_at):
    # The other side of the boundary: one tick short of _t_wait is still RUNNING.
    clock = clock_at(23, 59, 59)
    schedule = _schedule(datetime.time(23, 0, 0), datetime.time(0, 0, 1))
    pause_schedule = PauseSchedule("pause_schedule", schedule, clock=clock)

    pause_schedule.tick_once()
    assert pause_schedule.status == py_trees.common.Status.RUNNING

    clock.advance(1.999)
    pause_schedule.tick_once()
    assert pause_schedule.status == py_trees.common.Status.RUNNING

    clock.advance(0.001)
    pause_schedule.tick_once()
    assert pause_schedule.status == py_trees.common.Status.SUCCESS


def test_overnight_window_selects_matching_entry_among_several(clock_at):
    clock = clock_at(23, 30, 0)
    schedule = _schedule(datetime.time(2, 0, 0), datetime.time(3, 0, 0))
    schedule += _schedule(datetime.time(23, 0, 0), datetime.time(1, 0, 0))
    pause_schedule = PauseSchedule("pause_schedule", schedule, clock=clock)

    pause_schedule.tick_once()

    assert pause_schedule.status == py_trees.common.Status.RUNNING
    assert pause_schedule._t_wait == 1.5 * 60 * 60
    assert pause_schedule._last_schedule_idx == 1
