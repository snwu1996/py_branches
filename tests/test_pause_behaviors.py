#!/usr/bin/env python
import datetime
import random
import time

import numpy as np
import py_trees
import pytest

from py_branches.clock import ManualClock
from py_branches.pause import PausePDF
from py_branches.pause import PauseSchedule
from py_branches.pause import PauseUniform
from py_branches.pause import PauseUntilKey


class FakeKeyboardListener:
    def __init__(self, on_press):
        self.on_press = on_press
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True


class FakeKey:
    def __init__(self, char=None, name=None):
        self.char = char
        self.name = name


def _write_floats(path, values):
    path.write_text("\n".join(str(v) for v in values) + "\n")


def test_pause_uniform():
    random.seed(0)
    clock = ManualClock()
    pause_uniform = PauseUniform("pause_uniform", 0.2, 0.5, clock=clock)

    pause_uniform.tick_once()
    assert pause_uniform.status == py_trees.common.Status.RUNNING
    sampled = pause_uniform._pause_t
    assert 0.2 < sampled < 0.5

    # One hair short of the sampled duration: still RUNNING.
    clock.advance(sampled - 0.001)
    pause_uniform.tick_once()
    assert pause_uniform.status == py_trees.common.Status.RUNNING

    # Once it elapses: SUCCESS, on the exact boundary rather than a poll loop.
    clock.advance(0.001)
    pause_uniform.tick_once()
    assert pause_uniform.status == py_trees.common.Status.SUCCESS


def test_pause_schedule_pauses_at_scheduled_time():
    # A whole-second base time: datetime_time_to_sec truncates microseconds, so
    # a schedule built off a sub-second timestamp would make t_wait off by up
    # to a second. On a ManualClock that is chosen rather than hoped for.
    base_dt = datetime.datetime.combine(datetime.date.today(), datetime.time(12, 0, 0))
    clock = ManualClock(start=base_dt.timestamp())

    start_t = (base_dt + datetime.timedelta(seconds=3)).time()
    stop_t = (base_dt + datetime.timedelta(seconds=6)).time()

    schedule = [
        {
            "start_pause_time": start_t,
            "stop_pause_time": stop_t,
            "variance_time": datetime.time(0, 0, 0),
            "start_plus_variance_time": start_t,
            "stop_plus_variance_time": stop_t,
        }
    ]

    pause_schedule = PauseSchedule("pause_schedule", schedule, clock=clock)

    # Before the scheduled window, should immediately succeed (not pause).
    pause_schedule.tick_once()
    assert pause_schedule.status == py_trees.common.Status.SUCCESS

    # Step into the scheduled window, then tick.
    clock.advance(3.05)
    pause_schedule.tick_once()
    assert pause_schedule.status == py_trees.common.Status.RUNNING
    # 12:00:03.05 -> stop at 12:00:06 is 2.95s, and the truncation to whole
    # seconds makes that exactly the remaining 3s from 12:00:03.
    assert pause_schedule._t_wait == pytest.approx(3.0)

    # Still RUNNING just short of the wait, SUCCESS once it elapses.
    clock.advance(2.95)
    pause_schedule.tick_once()
    assert pause_schedule.status == py_trees.common.Status.RUNNING

    clock.advance(0.05)
    pause_schedule.tick_once()
    assert pause_schedule.status == py_trees.common.Status.SUCCESS


def test_pause_schedule_rearms_after_window_end():
    clock = ManualClock(
        start=datetime.datetime.combine(
            datetime.date.today(), datetime.time(12, 0, 0)
        ).timestamp()
    )
    now = datetime.time(12, 0, 0)
    one_second_ago = (
        datetime.datetime.combine(datetime.date.today(), now)
        - datetime.timedelta(seconds=1)
    ).time()
    one_second_later = (
        datetime.datetime.combine(datetime.date.today(), now)
        + datetime.timedelta(seconds=1)
    ).time()
    one_minute_ago = (
        datetime.datetime.combine(datetime.date.today(), now)
        - datetime.timedelta(minutes=1)
    ).time()
    one_minute_later = (
        datetime.datetime.combine(datetime.date.today(), now)
        + datetime.timedelta(minutes=1)
    ).time()

    schedule = [
        {
            "start_pause_time": one_second_ago,
            "stop_pause_time": one_second_later,
            "variance_time": datetime.time(0, 0, 0),
            "start_plus_variance_time": one_second_ago,
            "stop_plus_variance_time": one_second_later,
        }
    ]

    pause_schedule = PauseSchedule("pause_schedule", schedule, clock=clock)

    # First tick in active window should pause (RUNNING).
    pause_schedule.tick_once()
    assert pause_schedule.status == py_trees.common.Status.RUNNING

    # Wait out the window and let it complete.
    clock.advance(1.2)
    pause_schedule.tick_once()
    assert pause_schedule.status == py_trees.common.Status.SUCCESS

    # Re-enter the same window: should not re-pause (SUCCESS immediately).
    schedule[0]["start_plus_variance_time"] = one_minute_ago
    schedule[0]["stop_plus_variance_time"] = one_minute_later
    pause_schedule.tick_once()
    assert pause_schedule.status == py_trees.common.Status.SUCCESS

    # Move outside all windows to re-arm internal state.
    schedule[0]["start_plus_variance_time"] = one_minute_later
    schedule[0]["stop_plus_variance_time"] = one_minute_ago
    pause_schedule.tick_once()
    assert pause_schedule.status == py_trees.common.Status.SUCCESS

    # Move back into active window: should pause again.
    schedule[0]["start_plus_variance_time"] = one_minute_ago
    schedule[0]["stop_plus_variance_time"] = one_minute_later
    pause_schedule.tick_once()
    assert pause_schedule.status == py_trees.common.Status.RUNNING


def test_pause_schedule_fail_outside_window():
    base_dt = datetime.datetime.combine(datetime.date.today(), datetime.time(12, 0, 0))
    clock = ManualClock(start=base_dt.timestamp())

    start_t = (base_dt + datetime.timedelta(seconds=3)).time()
    stop_t = (base_dt + datetime.timedelta(seconds=6)).time()

    schedule = [
        {
            "start_pause_time": start_t,
            "stop_pause_time": stop_t,
            "variance_time": datetime.time(0, 0, 0),
            "start_plus_variance_time": start_t,
            "stop_plus_variance_time": stop_t,
        }
    ]

    pause_schedule = PauseSchedule(
        "pause_schedule", schedule, clock=clock, fail_outside_window=True
    )

    # Outside the window: FAILURE, so a parent Selector falls through.
    pause_schedule.tick_once()
    assert pause_schedule.status == py_trees.common.Status.FAILURE

    # Inside the window: RUNNING until the stop time, then SUCCESS.
    clock.advance(3.05)
    pause_schedule.tick_once()
    assert pause_schedule.status == py_trees.common.Status.RUNNING

    # Overshoot the stop time rather than landing on it: the countdown check is
    # `t_elapse < t_wait`, and accumulated float error on the boundary itself
    # leaves the behavior RUNNING for one more tick.
    clock.advance(3.0)
    pause_schedule.tick_once()
    assert pause_schedule.status == py_trees.common.Status.SUCCESS

    # Past the window: FAILURE again.
    clock.advance(1.0)
    pause_schedule.tick_once()
    assert pause_schedule.status == py_trees.common.Status.FAILURE


def test_pause_schedule_fail_outside_window_interrupts_selector():
    base_dt = datetime.datetime.combine(datetime.date.today(), datetime.time(12, 0, 0))
    clock = ManualClock(start=base_dt.timestamp())

    start_t = (base_dt + datetime.timedelta(seconds=3)).time()
    stop_t = (base_dt + datetime.timedelta(seconds=6)).time()

    schedule = [
        {
            "start_pause_time": start_t,
            "stop_pause_time": stop_t,
            "variance_time": datetime.time(0, 0, 0),
            "start_plus_variance_time": start_t,
            "stop_plus_variance_time": stop_t,
        }
    ]

    pause_schedule = PauseSchedule(
        "pause_schedule", schedule, clock=clock, fail_outside_window=True
    )
    work = py_trees.behaviours.Running(name="work")
    root = py_trees.composites.Selector(
        name="root", memory=False, children=[pause_schedule, work]
    )

    # Outside the window the Selector reaches the work behavior.
    root.tick_once()
    assert work.status == py_trees.common.Status.RUNNING

    # Inside the window the pause pre-empts it.
    clock.advance(3.05)
    root.tick_once()
    assert pause_schedule.status == py_trees.common.Status.RUNNING
    assert work.status == py_trees.common.Status.INVALID


def test_pause_until_key():
    b = PauseUntilKey("pause_until_key", "a", listener_factory=FakeKeyboardListener)
    b.tick_once()
    assert b.status == py_trees.common.Status.RUNNING
    assert b._listener is not None
    assert b._listener.started
    b.tick_once()
    assert b.status == py_trees.common.Status.RUNNING

    # Wrong key: still RUNNING.
    b._on_press(FakeKey(char="x"))
    b.tick_once()
    assert b.status == py_trees.common.Status.RUNNING

    # Right key: SUCCESS.
    b._on_press(FakeKey(char="a"))
    b.tick_once()
    assert b.status == py_trees.common.Status.SUCCESS
    assert b._listener is None

    b2 = PauseUntilKey(
        "pause_until_space", "space", listener_factory=FakeKeyboardListener
    )
    b2.tick_once()
    assert b2.status == py_trees.common.Status.RUNNING
    b2._on_press(FakeKey(name="space"))
    b2.tick_once()
    assert b2.status == py_trees.common.Status.SUCCESS


def test_pause_pdf_runs_until_elapsed(tmp_path):
    fp = tmp_path / "waits.txt"
    _write_floats(fp, [0.25] * 30)
    pause = PausePDF("pause_pdf", str(fp), kernel_bandwidth=0.01, min_t=0.1, max_t=0.5)
    start_ts = time.time()
    pause.tick_once()
    assert pause.status == py_trees.common.Status.RUNNING
    while pause.status == py_trees.common.Status.RUNNING:
        time.sleep(0.01)
        pause.tick_once()
    t_elapse = time.time() - start_ts
    assert pause.status == py_trees.common.Status.SUCCESS
    assert 0.1 <= t_elapse <= 0.5


def test_pause_pdf_resamples_each_initialise(tmp_path):
    fp = tmp_path / "waits.txt"
    _write_floats(fp, np.linspace(0.2, 1.0, 50).tolist())
    pause = PausePDF("pause_pdf", str(fp), kernel_bandwidth=0.05, min_t=0.0, max_t=2.0)
    samples = []
    for _ in range(5):
        pause.initialise()
        samples.append(pause._pause_t)
    assert len(set(samples)) > 1


def test_pause_pdf_respects_bounds(tmp_path):
    fp = tmp_path / "waits.txt"
    _write_floats(fp, np.linspace(0.5, 2.5, 40).tolist())
    pause = PausePDF("pause_pdf", str(fp), kernel_bandwidth=0.3, min_t=1.0, max_t=2.0)
    for _ in range(20):
        pause.initialise()
        assert 1.0 <= pause._pause_t <= 2.0


def test_pause_pdf_ignores_blank_and_comment_lines(tmp_path):
    fp = tmp_path / "waits.txt"
    fp.write_text("# header\n0.3\n\n0.4\n# trailing\n0.5\n")
    pause = PausePDF("pause_pdf", str(fp), kernel_bandwidth=0.1, min_t=0.0, max_t=10.0)
    pause.initialise()
    assert pause._pause_t > 0


def test_pause_pdf_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        PausePDF("pause_pdf", str(tmp_path / "nope.txt"))


def test_pause_pdf_empty_file_raises(tmp_path):
    fp = tmp_path / "waits.txt"
    fp.write_text("# only a comment\n\n")
    with pytest.raises(AssertionError):
        PausePDF("pause_pdf", str(fp))


def test_pause_pdf_boundary_is_exact_on_manual_clock(tmp_path):
    """The sampled duration is honoured to the tick, with no real sleeping."""
    fp = tmp_path / "waits.txt"
    _write_floats(fp, [0.25] * 30)
    clock = ManualClock()
    pause = PausePDF(
        "pause_pdf",
        str(fp),
        kernel_bandwidth=0.01,
        min_t=0.1,
        max_t=0.5,
        clock=clock,
    )

    pause.tick_once()
    assert pause.status == py_trees.common.Status.RUNNING
    sampled = pause._pause_t
    assert 0.1 <= sampled <= 0.5

    clock.advance(sampled - 0.001)
    pause.tick_once()
    assert pause.status == py_trees.common.Status.RUNNING

    clock.advance(0.001)
    pause.tick_once()
    assert pause.status == py_trees.common.Status.SUCCESS
