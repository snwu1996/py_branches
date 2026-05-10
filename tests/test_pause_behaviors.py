#!/usr/bin/env python
import py_trees
import time
import datetime
import random

from py_branches.pause import PauseUniform
from py_branches.pause import PauseSchedule


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
