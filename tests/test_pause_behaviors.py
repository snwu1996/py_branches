#!/usr/bin/env python
import py_trees
import time
import datetime
import random

import numpy as np
import pytest

from py_branches.pause import PauseUniform
from py_branches.pause import PauseSchedule
from py_branches.pause import PausePDF
from py_branches.pause import PauseUntilKey


def _write_floats(path, values):
    path.write_text('\n'.join(str(v) for v in values) + '\n')


def test_pause_uniform():
    random.seed(0)
    pause_uniform = PauseUniform('pause_uniform', 0.2, 0.5)
    start_ts = time.time()
    while True:
        pause_uniform.tick_once()
        if pause_uniform.status == py_trees.common.Status.SUCCESS:
            break
        time.sleep(0.01)
    end_ts = time.time()
    t_elapse = end_ts - start_ts
    assert (0.2 < t_elapse < 0.5)


def test_pause_schedule_pauses_at_scheduled_time():
    now_dt = datetime.datetime.now()
    start_dt = now_dt + datetime.timedelta(seconds=3)
    stop_dt = now_dt + datetime.timedelta(seconds=6)
    start_t = start_dt.time()
    stop_t = stop_dt.time()

    schedule = [{
        'start_pause_time': start_t,
        'stop_pause_time': stop_t,
        'variance_time': datetime.time(0, 0, 0),
        'start_plus_variance_time': start_t,
        'stop_plus_variance_time': stop_t,
    }]

    pause_schedule = PauseSchedule('pause_schedule', schedule)

    # Before the scheduled window, should immediately succeed (not pause).
    pause_schedule.tick_once()
    assert pause_schedule.status == py_trees.common.Status.SUCCESS

    # Wait until we are inside the scheduled window, then tick.
    sleep_until_window = (start_dt - datetime.datetime.now()).total_seconds() + 0.05
    if sleep_until_window > 0:
        time.sleep(sleep_until_window)

    pause_schedule.tick_once()
    assert pause_schedule.status == py_trees.common.Status.RUNNING
    pause_start_ts = time.time()

    # Tick until SUCCESS and confirm the pause lasted ~3 seconds.
    while pause_schedule.status == py_trees.common.Status.RUNNING:
        time.sleep(0.05)
        pause_schedule.tick_once()
    pause_duration = time.time() - pause_start_ts
    assert pause_schedule.status == py_trees.common.Status.SUCCESS
    assert 2.5 < pause_duration < 3.5, f'pause_duration={pause_duration}'


def test_pause_schedule_rearms_after_window_end():
    now = datetime.datetime.now().time()
    one_second_ago = (datetime.datetime.combine(datetime.date.today(), now) -
                      datetime.timedelta(seconds=1)).time()
    one_second_later = (datetime.datetime.combine(datetime.date.today(), now) +
                        datetime.timedelta(seconds=1)).time()
    one_minute_ago = (datetime.datetime.combine(datetime.date.today(), now) -
                      datetime.timedelta(minutes=1)).time()
    one_minute_later = (datetime.datetime.combine(datetime.date.today(), now) +
                        datetime.timedelta(minutes=1)).time()

    schedule = [{
        'start_pause_time': one_second_ago,
        'stop_pause_time': one_second_later,
        'variance_time': datetime.time(0, 0, 0),
        'start_plus_variance_time': one_second_ago,
        'stop_plus_variance_time': one_second_later,
    }]

    pause_schedule = PauseSchedule('pause_schedule', schedule)

    # First tick in active window should pause (RUNNING).
    pause_schedule.tick_once()
    assert pause_schedule.status == py_trees.common.Status.RUNNING

    # Wait out the window and let it complete.
    time.sleep(1.2)
    pause_schedule.tick_once()
    assert pause_schedule.status == py_trees.common.Status.SUCCESS

    # Re-enter the same window: should not re-pause (SUCCESS immediately).
    schedule[0]['start_plus_variance_time'] = one_minute_ago
    schedule[0]['stop_plus_variance_time'] = one_minute_later
    pause_schedule.tick_once()
    assert pause_schedule.status == py_trees.common.Status.SUCCESS

    # Move outside all windows to re-arm internal state.
    schedule[0]['start_plus_variance_time'] = one_minute_later
    schedule[0]['stop_plus_variance_time'] = one_minute_ago
    pause_schedule.tick_once()
    assert pause_schedule.status == py_trees.common.Status.SUCCESS

    # Move back into active window: should pause again.
    schedule[0]['start_plus_variance_time'] = one_minute_ago
    schedule[0]['stop_plus_variance_time'] = one_minute_later
    pause_schedule.tick_once()
    assert pause_schedule.status == py_trees.common.Status.RUNNING


def test_pause_until_key():
    from pynput.keyboard import KeyCode, Key

    b = PauseUntilKey('pause_until_key', 'a')
    b.tick_once()
    assert b.status == py_trees.common.Status.RUNNING
    b.tick_once()
    assert b.status == py_trees.common.Status.RUNNING

    # Wrong key: still RUNNING.
    b._on_press(KeyCode.from_char('x'))
    b.tick_once()
    assert b.status == py_trees.common.Status.RUNNING

    # Right key: SUCCESS.
    b._on_press(KeyCode.from_char('a'))
    b.tick_once()
    assert b.status == py_trees.common.Status.SUCCESS

    b2 = PauseUntilKey('pause_until_space', 'space')
    b2.tick_once()
    assert b2.status == py_trees.common.Status.RUNNING
    b2._on_press(Key.space)
    b2.tick_once()
    assert b2.status == py_trees.common.Status.SUCCESS


def test_pause_pdf_runs_until_elapsed(tmp_path):
    fp = tmp_path / 'waits.txt'
    _write_floats(fp, [0.25] * 30)
    pause = PausePDF('pause_pdf', str(fp), kernel_bandwidth=0.01, min_t=0.1, max_t=0.5)
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
    fp = tmp_path / 'waits.txt'
    _write_floats(fp, np.linspace(0.2, 1.0, 50).tolist())
    pause = PausePDF('pause_pdf', str(fp), kernel_bandwidth=0.05, min_t=0.0, max_t=2.0)
    samples = []
    for _ in range(5):
        pause.initialise()
        samples.append(pause._pause_t)
    assert len(set(samples)) > 1


def test_pause_pdf_respects_bounds(tmp_path):
    fp = tmp_path / 'waits.txt'
    _write_floats(fp, np.linspace(0.5, 2.5, 40).tolist())
    pause = PausePDF('pause_pdf', str(fp), kernel_bandwidth=0.3, min_t=1.0, max_t=2.0)
    for _ in range(20):
        pause.initialise()
        assert 1.0 <= pause._pause_t <= 2.0


def test_pause_pdf_ignores_blank_and_comment_lines(tmp_path):
    fp = tmp_path / 'waits.txt'
    fp.write_text('# header\n0.3\n\n0.4\n# trailing\n0.5\n')
    pause = PausePDF('pause_pdf', str(fp), kernel_bandwidth=0.1, min_t=0.0, max_t=10.0)
    pause.initialise()
    assert pause._pause_t > 0


def test_pause_pdf_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        PausePDF('pause_pdf', str(tmp_path / 'nope.txt'))


def test_pause_pdf_empty_file_raises(tmp_path):
    fp = tmp_path / 'waits.txt'
    fp.write_text('# only a comment\n\n')
    with pytest.raises(AssertionError):
        PausePDF('pause_pdf', str(fp))
