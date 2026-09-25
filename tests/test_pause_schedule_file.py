#!/usr/bin/env python
import datetime
import logging

import py_trees
import pytest

from py_branches.pause import PauseSchedule
from py_branches.pause import add_variance_to_datetime_time
from py_branches.pause import datetime_time_to_sec
from py_branches.pause import load_schedule_file


_SCHEDULE_KEYS = {
    'start_pause_time',
    'stop_pause_time',
    'variance_time',
    'start_plus_variance_time',
    'stop_plus_variance_time',
}


def _write_schedule(path, entries):
    """Write a schedule YAML file.

    Times are quoted so YAML reads them as strings; an unquoted ``9:00:00``
    would be parsed as a sexagesimal integer.
    """
    lines = []
    for entry in entries:
        lines.append(f"- start_pause_time: '{entry[0]}'")
        lines.append(f"  stop_pause_time: '{entry[1]}'")
        lines.append(f"  variance: '{entry[2]}'")
    path.write_text('\n'.join(lines) + '\n')
    return str(path)


def _load(path):
    """load_schedule_file narrowed to a list.

    The real function returns None for a file YAML reads as empty; every test
    using this helper writes entries, so None here is itself a failure.
    """
    schedule = load_schedule_file(path)
    assert schedule is not None
    return schedule


def test_load_schedule_file_parses_times(tmp_path):
    fp = _write_schedule(tmp_path / 'schedule.yaml',
                         [('09:30:00', '17:45:30', '00:00:00')])

    schedule = _load(fp)

    assert len(schedule) == 1
    element = schedule[0]
    assert set(element) == _SCHEDULE_KEYS
    assert element['start_pause_time'] == datetime.time(9, 30, 0)
    assert element['stop_pause_time'] == datetime.time(17, 45, 30)
    assert element['variance_time'] == datetime.time(0, 0, 0)
    assert all(isinstance(v, datetime.time) for v in element.values())


def test_load_schedule_file_zero_variance_leaves_times_unchanged(tmp_path):
    fp = _write_schedule(tmp_path / 'schedule.yaml',
                         [('09:30:00', '17:45:30', '00:00:00')])

    element = _load(fp)[0]

    assert element['start_plus_variance_time'] == element['start_pause_time']
    assert element['stop_plus_variance_time'] == element['stop_pause_time']


def test_load_schedule_file_applies_variance_within_bounds(tmp_path):
    fp = _write_schedule(tmp_path / 'schedule.yaml',
                         [('09:30:00', '17:45:30', '00:10:00')])

    element = _load(fp)[0]

    for base_key, varied_key in (('start_pause_time', 'start_plus_variance_time'),
                                 ('stop_pause_time', 'stop_plus_variance_time')):
        base = datetime.datetime.combine(datetime.date.today(), element[base_key])
        varied = datetime.datetime.combine(datetime.date.today(), element[varied_key])
        assert base <= varied <= base + datetime.timedelta(minutes=10)


def test_load_schedule_file_preserves_entry_order(tmp_path):
    fp = _write_schedule(tmp_path / 'schedule.yaml', [
        ('01:00:00', '02:00:00', '00:00:00'),
        ('03:00:00', '04:00:00', '00:00:00'),
        ('05:00:00', '06:00:00', '00:00:00'),
    ])

    schedule = _load(fp)

    assert [e['start_pause_time'] for e in schedule] == [
        datetime.time(1, 0, 0),
        datetime.time(3, 0, 0),
        datetime.time(5, 0, 0),
    ]


def test_load_schedule_file_handles_overnight_window(tmp_path):
    fp = _write_schedule(tmp_path / 'schedule.yaml',
                         [('23:00:00', '01:00:00', '00:00:00')])

    element = _load(fp)[0]

    # A window that wraps past midnight is stored as-is, start later than stop.
    assert element['start_pause_time'] == datetime.time(23, 0, 0)
    assert element['stop_pause_time'] == datetime.time(1, 0, 0)
    assert element['start_pause_time'] > element['stop_pause_time']


def test_load_schedule_file_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_schedule_file(str(tmp_path / 'nope.yaml'))


def test_load_schedule_file_malformed_time_raises(tmp_path):
    fp = _write_schedule(tmp_path / 'schedule.yaml',
                         [('9am', '17:45:30', '00:00:00')])

    with pytest.raises(ValueError):
        load_schedule_file(fp)


def test_load_schedule_file_empty_file_returns_none(tmp_path, caplog):
    # An empty file is not an error: the loader logs and returns None so the
    # caller decides what to do.
    fp = tmp_path / 'schedule.yaml'
    fp.write_text('')

    with caplog.at_level(logging.ERROR):
        assert load_schedule_file(str(fp)) is None

    assert 'Failed to load schedule_file' in caplog.text


def test_load_schedule_file_comments_only_returns_none(tmp_path):
    # YAML reads a comment-only file as empty, same as a blank one.
    fp = tmp_path / 'schedule.yaml'
    fp.write_text('# no entries yet\n')

    assert load_schedule_file(str(fp)) is None


def test_load_schedule_file_missing_key_raises(tmp_path):
    fp = tmp_path / 'schedule.yaml'
    fp.write_text("- start_pause_time: '09:30:00'\n"
                  "  stop_pause_time: '17:45:30'\n")

    with pytest.raises(KeyError):
        load_schedule_file(str(fp))


def test_load_schedule_file_output_drives_pause_schedule(tmp_path):
    # A window one minute in the future, so 'now' is outside it.
    now = datetime.datetime.now()
    start = (now + datetime.timedelta(minutes=1)).time()
    stop = (now + datetime.timedelta(minutes=2)).time()
    fp = _write_schedule(tmp_path / 'schedule.yaml', [(
        start.strftime('%H:%M:%S'),
        stop.strftime('%H:%M:%S'),
        '00:00:00',
    )])

    pause_schedule = PauseSchedule('pause_schedule', _load(fp))
    pause_schedule.tick_once()

    # Outside every window, so no pause is scheduled.
    assert pause_schedule.status == py_trees.common.Status.SUCCESS


def test_datetime_time_to_sec():
    assert datetime_time_to_sec(datetime.time(0, 0, 0)) == 0
    assert datetime_time_to_sec(datetime.time(0, 0, 1)) == 1
    assert datetime_time_to_sec(datetime.time(1, 2, 3)) == 3723
    assert datetime_time_to_sec(datetime.time(23, 59, 59)) == 86399


def test_datetime_time_to_sec_ignores_microseconds():
    assert datetime_time_to_sec(datetime.time(0, 0, 1, 500000)) == 1


def test_add_variance_to_datetime_time_zero_variance_is_identity():
    t = datetime.time(12, 0, 0)

    assert add_variance_to_datetime_time(t, datetime.time(0, 0, 0)) == t


def test_add_variance_to_datetime_time_stays_within_bounds():
    t = datetime.time(12, 0, 0)
    variance = datetime.time(0, 0, 10)
    base = datetime.datetime.combine(datetime.date.today(), t)

    for _ in range(50):
        result = add_variance_to_datetime_time(t, variance)
        result_dt = datetime.datetime.combine(datetime.date.today(), result)
        assert base <= result_dt <= base + datetime.timedelta(seconds=10)


def test_add_variance_to_datetime_time_varies():
    t = datetime.time(12, 0, 0)
    variance = datetime.time(1, 0, 0)

    results = {add_variance_to_datetime_time(t, variance) for _ in range(20)}

    # Sampled from a continuous range; identical draws would mean variance
    # is being ignored.
    assert len(results) > 1
