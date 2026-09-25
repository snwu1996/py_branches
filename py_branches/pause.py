#!/usr/bin/env python3
"""Behaviors that hold a tree still for a while.

Four leaf behaviors, differing in where the pause duration comes from:

* :class:`PauseUniform` — a duration drawn uniformly between two bounds.
* :class:`PausePDF` — a duration drawn from a kernel density estimate fitted
  to recorded samples, for pauses that mimic observed timing.
* :class:`PauseUntilKey` — no duration at all; waits for a key press.
* :class:`PauseSchedule` — waits out a wall-clock window loaded from a YAML
  file, for behavior that should idle overnight or over lunch.

All of them return RUNNING while the pause is active and SUCCESS once it is
over, so they tick cooperatively rather than blocking the tree.

:func:`load_schedule_file` turns a YAML schedule into the form
:class:`PauseSchedule` expects; :func:`datetime_time_to_sec` and
:func:`add_variance_to_datetime_time` are the time helpers behind it.
"""
import logging
import time
import py_trees
import datetime
import random
import yaml
import os
from typing import Dict
from typing import List

import numpy as np
from sklearn.neighbors import KernelDensity


HOUR2SEC = 3600
MIN2SEC = 60


def _create_keyboard_listener(on_press):
    # Import lazily so headless CI can import this module without an X server.
    from pynput import keyboard
    return keyboard.Listener(on_press=on_press)


class PauseUniform(py_trees.behaviour.Behaviour):
    """Pause for a duration drawn uniformly from ``[low, high]``.

    A new duration is sampled on each fresh entry, using :func:`random.uniform`
    from the standard library.

    The bounds are not validated; ``low`` greater than ``high`` yields samples
    from the reversed interval, as :func:`random.uniform` permits.

    Args:
        name (str): Name of this behavior node.
        low (float): Minimum pause duration in seconds.
        high (float): Maximum pause duration in seconds.

    Returns:
        Status: RUNNING until the sampled duration elapses, then SUCCESS.

    Example:
        .. code-block:: python

            # Pause for between 2 and 5 seconds.
            pause = PauseUniform(name="ShortPause", low=2.0, high=5.0)
    """
    def __init__(self, name: str, low: float, high: float):
        super(PauseUniform, self).__init__(name=name)
        self._high = high
        self._low = low

    def initialise(self):
        self._pause_t = random.uniform(self._low, self._high)
        self._start_t = time.time()

    def update(self):
        t_elapse = time.time() - self._start_t
        if t_elapse < self._pause_t:
            return py_trees.common.Status.RUNNING
        else:
            return py_trees.common.Status.SUCCESS

class PausePDF(py_trees.behaviour.Behaviour):
    """Pause for a duration sampled from a KDE fit to a file of float samples.

    The file holds one float per line, in seconds; blank lines and lines
    starting with ``#`` are ignored. A Gaussian kernel density estimate is
    fitted to those samples once, at construction, and each entry draws a new
    duration from it.

    Sampling is rejected and retried until the draw falls within
    ``[min_t, max_t]``, which is what keeps a Gaussian kernel from ever
    producing a negative pause.

    Warning:
        The rejection loop has no iteration limit. Bounds that exclude
        essentially all of the fitted distribution's mass will hang
        ``initialise()``, so keep ``min_t`` and ``max_t`` consistent with the
        sample data.

    Args:
        name (str): Name of this behavior node.
        filepath (str): Path to the newline-separated sample file.
        kernel_bandwidth (float): Bandwidth of the Gaussian kernel. Larger
            values smooth the fitted distribution. Default 1.0.
        min_t (float): Lower bound on the sampled pause, in seconds.
            Default 0.0.
        max_t (float): Upper bound on the sampled pause, in seconds. Default
            unbounded.

    Returns:
        Status: RUNNING until the sampled duration elapses, then SUCCESS.

    Raises:
        FileNotFoundError: If ``filepath`` is not a file.
        AssertionError: If the file contains no usable samples.

    Example:
        .. code-block:: python

            # Draw human-like think times from recorded data, clamped to
            # between 1 and 30 seconds.
            pause = PausePDF(
                name="ThinkTime",
                filepath="data/think_times.txt",
                min_t=1.0,
                max_t=30.0,
            )
    """

    def __init__(
        self,
        name: str,
        filepath: str,
        kernel_bandwidth: float = 1.0,
        min_t: float = 0.0,
        max_t: float = float('inf'),
    ):
        super(PausePDF, self).__init__(name=name)
        if not os.path.isfile(filepath):
            raise FileNotFoundError(f'filepath: {filepath} is not a valid file')

        samples = []
        with open(filepath, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                samples.append(float(line))
        assert len(samples), f'filepath: {filepath} contains no float samples'

        self._min_t = min_t
        self._max_t = max_t
        self._model = KernelDensity(bandwidth=kernel_bandwidth, kernel='gaussian')
        self._model.fit(np.asarray(samples).reshape(-1, 1))

    def initialise(self):
        t_wait = self._min_t - 1.0
        while not (self._min_t <= t_wait <= self._max_t):
            t_wait = float(self._model.sample(1)[0][0]) # pyright: ignore
        self._pause_t = t_wait
        self._start_t = time.time()
        self.logger.debug(f'{self.name} sampled pause {self._pause_t:.3f} sec')

    def update(self):
        t_elapse = time.time() - self._start_t
        if t_elapse < self._pause_t:
            return py_trees.common.Status.RUNNING
        return py_trees.common.Status.SUCCESS


class PauseUntilKey(py_trees.behaviour.Behaviour):
    """Pause (RUNNING) until the configured key is pressed, then SUCCESS.

    ``key`` is a pynput key string: a single character like ``'a'``, or a
    special key name like ``'space'``, ``'enter'``, ``'esc'`` (matching
    ``pynput.keyboard.Key`` names).

    A fresh listener is started on each entry and stopped on termination, so
    key presses that arrive while this behavior is not running are ignored.

    pynput is imported only when a listener is created, which keeps this module
    importable on a headless machine; constructing and ticking this behavior
    does still require an accessible input device.

    Args:
        name (str): Name of this behavior node.
        key (str): Key to wait for.
        listener_factory: Callable taking an ``on_press`` keyword and returning
            an object with ``start()`` and ``stop()``. Defaults to a real
            pynput listener; override it to supply a fake in tests.

    Returns:
        Status: RUNNING until the key is pressed, then SUCCESS.

    Example:
        .. code-block:: python

            # Hold the tree until the operator presses space.
            gate = PauseUntilKey(name="WaitForSpace", key="space")
    """

    def __init__(self, name: str, key: str, listener_factory=_create_keyboard_listener):
        super(PauseUntilKey, self).__init__(name=name)
        self._key = key
        self._listener_factory = listener_factory
        self._listener = None
        self._pressed = False

    def _matches(self, key) -> bool:
        char = getattr(key, 'char', None)
        if char is not None and char == self._key:
            return True
        name = getattr(key, 'name', None)
        if name is not None and name == self._key:
            return True
        return False

    def _on_press(self, key):
        if self._matches(key):
            self._pressed = True
            return False

    def initialise(self):
        self._pressed = False
        if self._listener is not None:
            self._listener.stop()
        self._listener = self._listener_factory(on_press=self._on_press)
        self._listener.start()

    def update(self):
        if self._pressed:
            return py_trees.common.Status.SUCCESS
        return py_trees.common.Status.RUNNING

    def terminate(self, new_status):
        if self._listener is not None:
            self._listener.stop()
            self._listener = None


def load_schedule_file(schedule_filepath: str) -> list[dict[str, datetime.time]] | None:
    """Load a YAML pause schedule and pre-compute its variance offsets.

    Each entry in the file defines a pause window as wall-clock times in
    ``HH:MM:SS`` form, plus a variance read as a duration:

    .. code-block:: yaml

        - start_pause_time: "22:30:00"
          stop_pause_time: "6:30:00"
          variance: "0:30:00"
        - start_pause_time: "12:30:00"
          stop_pause_time: "16:30:00"
          variance: "0:30:00"

    The returned dicts carry both the times as written and the variance-shifted
    times that :class:`PauseSchedule` actually matches against, under the keys
    ``start_pause_time``, ``stop_pause_time``, ``variance_time``,
    ``start_plus_variance_time`` and ``stop_plus_variance_time``.

    Variance is applied independently to the start and the stop time, and only
    ever shifts them later — see :func:`add_variance_to_datetime_time`. A
    window whose stop time precedes its start time is treated as crossing
    midnight.

    Args:
        schedule_filepath (str): Path to the YAML schedule file.

    Returns:
        A list of schedule entries ready to pass to :class:`PauseSchedule`, or
        None if the file parsed as empty (blank, or comments only), in which
        case the failure is logged rather than raised.

    Raises:
        FileNotFoundError: If ``schedule_filepath`` is not a file.

    Example:
        .. code-block:: python

            schedule = load_schedule_file("configs/schedules/example_schedule.yaml")
    """
    if not os.path.isfile(schedule_filepath):
        raise FileNotFoundError(f'schedule_filepath: {schedule_filepath} is not a valid file')
    
    with open(schedule_filepath, 'r') as schedule_file:
        schedule_raw = yaml.safe_load(schedule_file)

    if schedule_raw is None:
        logging.error(f'Failed to load schedule_file: {schedule_filepath}')
        return None

    schedule = []
    for schedule_element_raw in schedule_raw:
        start_pause_time = datetime.datetime.strptime(schedule_element_raw['start_pause_time'], '%H:%M:%S').time()
        stop_pause_time = datetime.datetime.strptime(schedule_element_raw['stop_pause_time'], '%H:%M:%S').time()
        variance_time = datetime.datetime.strptime(schedule_element_raw['variance'], '%H:%M:%S').time()
        schedule.append({'start_pause_time': start_pause_time,
                         'stop_pause_time': stop_pause_time,
                         'variance_time': variance_time,
                         'start_plus_variance_time': add_variance_to_datetime_time(start_pause_time, variance_time),
                         'stop_plus_variance_time': add_variance_to_datetime_time(stop_pause_time, variance_time)})
    return schedule

def datetime_time_to_sec(t: datetime.time):
    """Convert a time of day to seconds since midnight.

    Sub-second precision is discarded.

    Args:
        t (datetime.time): Time to convert.

    Returns:
        int: Seconds elapsed since midnight.
    """
    sec = t.hour*HOUR2SEC+t.minute*MIN2SEC+t.second
    return sec

def add_variance_to_datetime_time(t: datetime.time, variance_time: datetime.time) -> datetime.time:
    """Offset a time by a random amount drawn from ``[0, variance_time]``.

    The offset is always forward in time — it is drawn from zero to the full
    variance, never negative — and wraps past midnight if the sum exceeds
    24 hours.

    Args:
        t (datetime.time): Base time.
        variance_time (datetime.time): Upper bound of the offset, read as a
            duration, e.g. ``datetime.time(0, 30, 0)`` for up to 30 minutes.

    Returns:
        datetime.time: ``t`` plus the sampled offset.
    """
    variance_sec = datetime_time_to_sec(variance_time)
    variance_timedelta = datetime.timedelta(seconds=random.uniform(0.0, variance_sec))
    time_to_datetime = datetime.datetime.combine(datetime.date.today(), t)
    time_with_variance = (time_to_datetime + variance_timedelta).time()
    return time_with_variance

class PauseSchedule(py_trees.behaviour.Behaviour):
    """Pause until the end of the schedule window that is active right now.

    On each fresh entry this behavior looks for a window containing the current
    wall-clock time. If it finds one, it computes the seconds remaining until
    that window's (variance-adjusted) stop time and stays RUNNING for that long.
    If the current time falls outside every window, it returns SUCCESS
    immediately, so the behavior is cheap to tick continuously.

    Two pieces of state keep it from misbehaving across long runs:

    * A window that has already been handled will not pause again, even while
      the clock is still inside it. Re-arming happens once the current time has
      left every window.
    * After handling a window, fresh variance offsets are drawn for that
      window's start and stop times, so the boundaries differ from day to day.

    Windows that cross midnight are matched correctly, and the remaining-time
    calculation wraps through midnight as well.

    Args:
        name (str): Name of this behavior node.
        schedule (List[Dict[str, datetime.time]]): Preprocessed schedule, as
            returned by :func:`load_schedule_file`.

    Returns:
        Status: SUCCESS when outside all windows or once the active window's
        stop time is reached; RUNNING until then.

    Example:
        .. code-block:: python

            from py_branches.pause import PauseSchedule, load_schedule_file

            schedule = load_schedule_file("configs/schedules/example_schedule.yaml")
            if schedule is None:
                raise SystemExit("schedule file is empty")

            pause = PauseSchedule(name="ScheduledPause", schedule=schedule)

            root = py_trees.composites.Sequence(name="Root", memory=True)
            root.add_children([pause, main_behavior])
    """
    def __init__(self, name: str, schedule: List[Dict[str, datetime.time]]):
        self._schedule = schedule
        self._last_schedule_idx = None
        super(PauseSchedule, self).__init__(name=name)

    def initialise(self):
        super().initialise()
        self._t_wait = None
        self._t_start = time.time()
        now_time = datetime.datetime.now().time()
        matched_idx = None
        for idx, schedule_element in enumerate(self._schedule):
            start = schedule_element['start_plus_variance_time']
            stop = schedule_element['stop_plus_variance_time']
            if (start < stop and start < now_time < stop) or \
               (start > stop and (now_time > start or now_time < stop)):
                matched_idx = idx
                break

        # Re-arm once we've left all windows.
        if matched_idx is None:
            self._last_schedule_idx = None
            return

        # Don't re-pause for the same window we already handled.
        if matched_idx == self._last_schedule_idx:
            return

        self._last_schedule_idx = matched_idx
        schedule_element = self._schedule[matched_idx]
        stop = schedule_element['stop_plus_variance_time']
        variance = schedule_element['variance_time']
        if now_time < stop:
            self._t_wait = datetime_time_to_sec(stop) - \
                           datetime_time_to_sec(now_time)
        else:
            self._t_wait = datetime_time_to_sec(datetime.time(23, 59, 59)) + 1 - \
                           datetime_time_to_sec(now_time) + \
                           datetime_time_to_sec(stop)
        self._t_start = time.time()
        logging.info(f'Wait has been scheduled for  {self._t_wait:.3f} sec')
        schedule_element['start_plus_variance_time'] = \
            add_variance_to_datetime_time(schedule_element['start_pause_time'], variance)
        schedule_element['stop_plus_variance_time'] = \
            add_variance_to_datetime_time(schedule_element['stop_pause_time'], variance)
        logging.info(f'new start_plus_variance_time: {schedule_element["start_plus_variance_time"]}')
        logging.info(f'new stop_plus_variance_time: {schedule_element["stop_plus_variance_time"]}')

    def update(self):
        if self._t_wait is None:
            return py_trees.common.Status.SUCCESS

        t_elapse = time.time() - self._t_start
        if t_elapse < self._t_wait:
            return py_trees.common.Status.RUNNING
        else:
            return py_trees.common.Status.SUCCESS
