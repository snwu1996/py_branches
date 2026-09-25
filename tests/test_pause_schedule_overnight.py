#!/usr/bin/env python
"""Overnight (midnight-wrapping) window handling in PauseSchedule.

A window whose start is later than its stop wraps past midnight, which takes
a different branch both when matching the window and when computing the wait.
The real clock cannot exercise those branches reliably -- an overnight test
built on datetime.now() would behave differently depending on the hour CI runs
at, and the 'now is after start' case computes a wait of up to ~24 hours. So
these tests freeze the clock inside py_branches.pause instead.
"""
import datetime
import time

import py_trees
import pytest

import py_branches.pause as pause
from py_branches.pause import PauseSchedule


def _frozen_datetime_class(now_dt):
    class _FrozenDatetime(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return now_dt

    return _FrozenDatetime


class _FakeDatetimeModule:
    """Stand-in for the `datetime` module with `datetime.now()` pinned.

    Patched onto py_branches.pause only, so the real module is untouched
    everywhere else.
    """

    def __init__(self, now_dt):
        self.datetime = _frozen_datetime_class(now_dt)
        self.date = datetime.date
        self.time = datetime.time
        self.timedelta = datetime.timedelta


@pytest.fixture
def freeze_now(monkeypatch):
    def _freeze(hour, minute, second):
        now_dt = datetime.datetime.combine(
            datetime.date.today(), datetime.time(hour, minute, second)
        )
        monkeypatch.setattr(pause, 'datetime', _FakeDatetimeModule(now_dt))
        return now_dt

    return _freeze


def _schedule(start, stop):
    """One zero-variance schedule entry, as load_schedule_file would build it."""
    return [{
        'start_pause_time': start,
        'stop_pause_time': stop,
        'variance_time': datetime.time(0, 0, 0),
        'start_plus_variance_time': start,
        'stop_plus_variance_time': stop,
    }]


def test_overnight_window_matches_before_midnight(freeze_now):
    freeze_now(23, 30, 0)
    schedule = _schedule(datetime.time(23, 0, 0), datetime.time(1, 0, 0))
    pause_schedule = PauseSchedule('pause_schedule', schedule)

    pause_schedule.tick_once()

    assert pause_schedule.status == py_trees.common.Status.RUNNING
    # 23:30 -> 01:00 the next day is 1.5 hours.
    assert pause_schedule._t_wait == 1.5 * 60 * 60


def test_overnight_window_matches_after_midnight(freeze_now):
    freeze_now(0, 30, 0)
    schedule = _schedule(datetime.time(23, 0, 0), datetime.time(1, 0, 0))
    pause_schedule = PauseSchedule('pause_schedule', schedule)

    pause_schedule.tick_once()

    assert pause_schedule.status == py_trees.common.Status.RUNNING
    # Already past midnight: 00:30 -> 01:00 is half an hour, no day rollover.
    assert pause_schedule._t_wait == 30 * 60


def test_overnight_window_wait_spans_midnight_exactly(freeze_now):
    freeze_now(23, 59, 59)
    schedule = _schedule(datetime.time(23, 0, 0), datetime.time(0, 0, 1))
    pause_schedule = PauseSchedule('pause_schedule', schedule)

    pause_schedule.tick_once()

    assert pause_schedule.status == py_trees.common.Status.RUNNING
    # 23:59:59 -> 00:00:01 is two seconds. This pins the '+ 1' that turns
    # 23:59:59 into a full day's worth of seconds.
    assert pause_schedule._t_wait == 2


def test_overnight_window_does_not_match_midday(freeze_now):
    freeze_now(12, 0, 0)
    schedule = _schedule(datetime.time(23, 0, 0), datetime.time(1, 0, 0))
    pause_schedule = PauseSchedule('pause_schedule', schedule)

    pause_schedule.tick_once()

    # Midday falls in the gap between stop (01:00) and start (23:00).
    assert pause_schedule.status == py_trees.common.Status.SUCCESS
    assert pause_schedule._t_wait is None


def test_overnight_window_boundaries_are_exclusive(freeze_now):
    # Exactly on start: the match uses `now > start`, so this is outside.
    freeze_now(23, 0, 0)
    schedule = _schedule(datetime.time(23, 0, 0), datetime.time(1, 0, 0))
    pause_schedule = PauseSchedule('pause_schedule', schedule)

    pause_schedule.tick_once()

    assert pause_schedule.status == py_trees.common.Status.SUCCESS


def test_overnight_window_stop_boundary_is_exclusive(freeze_now):
    # Exactly on stop: `now < stop` is false and `now > start` is false.
    freeze_now(1, 0, 0)
    schedule = _schedule(datetime.time(23, 0, 0), datetime.time(1, 0, 0))
    pause_schedule = PauseSchedule('pause_schedule', schedule)

    pause_schedule.tick_once()

    assert pause_schedule.status == py_trees.common.Status.SUCCESS


def test_same_day_window_wait_does_not_roll_over(freeze_now):
    freeze_now(12, 0, 0)
    schedule = _schedule(datetime.time(11, 0, 0), datetime.time(13, 0, 0))
    pause_schedule = PauseSchedule('pause_schedule', schedule)

    pause_schedule.tick_once()

    assert pause_schedule.status == py_trees.common.Status.RUNNING
    # The non-wrapping counterpart: one hour, no day added.
    assert pause_schedule._t_wait == 60 * 60


def test_overnight_window_completes_after_wait_elapses(freeze_now):
    # A two-second wait that straddles midnight, short enough to wait out.
    freeze_now(23, 59, 59)
    schedule = _schedule(datetime.time(23, 0, 0), datetime.time(0, 0, 1))
    pause_schedule = PauseSchedule('pause_schedule', schedule)

    pause_schedule.tick_once()
    assert pause_schedule.status == py_trees.common.Status.RUNNING

    # Still RUNNING is driven by the real clock, so the frozen 'now' does not
    # interfere; the behaviour stays RUNNING until _t_wait seconds pass.
    time.sleep(2.2)
    pause_schedule.tick_once()
    assert pause_schedule.status == py_trees.common.Status.SUCCESS


def test_overnight_window_selects_matching_entry_among_several(freeze_now):
    freeze_now(23, 30, 0)
    schedule = _schedule(datetime.time(2, 0, 0), datetime.time(3, 0, 0))
    schedule += _schedule(datetime.time(23, 0, 0), datetime.time(1, 0, 0))
    pause_schedule = PauseSchedule('pause_schedule', schedule)

    pause_schedule.tick_once()

    assert pause_schedule.status == py_trees.common.Status.RUNNING
    assert pause_schedule._t_wait == 1.5 * 60 * 60
    assert pause_schedule._last_schedule_idx == 1
