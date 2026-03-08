#!/usr/bin/env python
import py_trees
import time
import datetime
import numpy as np

from py_branches.pause import PauseUniform
from py_branches.pause import PauseSchedule
from py_branches.pause import CheckPauseSchedule


def test_pause_uniform():
    np.random.seed(0)
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


def test_check_pause_schedule_rearms_after_window_end():
    now = datetime.datetime.now().time()
    one_minute_ago = (datetime.datetime.combine(datetime.date.today(), now) -
                      datetime.timedelta(minutes=1)).time()
    one_minute_later = (datetime.datetime.combine(datetime.date.today(), now) +
                        datetime.timedelta(minutes=1)).time()

    schedule = [{
        'start_plus_variance_time': one_minute_ago,
        'stop_plus_variance_time': one_minute_later,
    }]

    check_pause_schedule = CheckPauseSchedule('check_pause_schedule', schedule)

    # First tick in active window should trigger.
    check_pause_schedule.tick_once()
    assert check_pause_schedule.status == py_trees.common.Status.SUCCESS

    # Second tick in same active window should not re-trigger.
    check_pause_schedule.tick_once()
    assert check_pause_schedule.status == py_trees.common.Status.FAILURE

    # Move outside all windows, which should re-arm internal state.
    schedule[0]['start_plus_variance_time'] = one_minute_later
    schedule[0]['stop_plus_variance_time'] = one_minute_ago
    check_pause_schedule.tick_once()
    assert check_pause_schedule.status == py_trees.common.Status.FAILURE

    # Move back into active window and verify it can trigger again.
    schedule[0]['start_plus_variance_time'] = one_minute_ago
    schedule[0]['stop_plus_variance_time'] = one_minute_later
    check_pause_schedule.tick_once()
    assert check_pause_schedule.status == py_trees.common.Status.SUCCESS
