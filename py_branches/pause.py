#!/usr/bin/env python3
"""Behaviors that hold a tree still for a while.

Five leaf behaviors, differing in where the pause duration comes from:

* :class:`PauseUniform` — a duration drawn uniformly between two bounds.
* :class:`PauseNormal` — a duration drawn from a truncated normal
  distribution, for waits that cluster around a typical value.
* :class:`PausePDF` — a duration drawn from a kernel density estimate fitted
  to recorded samples, for pauses that mimic observed timing.
* :class:`PauseUntilKey` — no duration at all; waits for a key press.
* :class:`PauseSchedule` — waits out a wall-clock window loaded from a YAML
  file, for behavior that should idle overnight or over lunch.

All of them return RUNNING while the pause is active and SUCCESS once it is
over, so they tick cooperatively rather than blocking the tree.

The three timed pauses take a keyword-only ``clock`` — see
:mod:`py_branches.clock` — which is what makes their timing testable without
sleeping.

:func:`load_schedule_file` turns a YAML schedule into the form
:class:`PauseSchedule` expects; :func:`datetime_time_to_sec` and
:func:`add_variance_to_datetime_time` are the time helpers behind it.
"""

import datetime
import logging
import math
import os
import random

import numpy as np
import py_trees
import yaml
from sklearn.neighbors import KernelDensity

from .clock import Clock
from .clock import default_clock

HOUR2SEC = 3600
MIN2SEC = 60


def _time_of_day(clock: Clock) -> datetime.time:
    """Return the local time of day according to ``clock``.

    ``clock.time()`` is a Unix timestamp, so this is the clock-injected
    equivalent of ``datetime.datetime.now().time()``.

    Args:
        clock (Clock): Time source to read.

    Returns:
        datetime.time: Local time of day.
    """
    return datetime.datetime.fromtimestamp(clock.time()).time()


def _create_keyboard_listener(on_press):
    # Import lazily so headless CI can import this module without an X server.
    from pynput import keyboard

    return keyboard.Listener(on_press=on_press)


class _SampledPause(py_trees.behaviour.Behaviour):
    """Base for pauses whose duration is sampled once per fresh entry.

    Subclasses supply :meth:`_sample`; this class owns the clock, records the
    start time in ``initialise()`` and compares elapsed time against the sample
    in ``update()``. It is private: the concrete pauses are the public surface.
    """

    def __init__(self, name: str, *, clock: Clock | None = None):
        super().__init__(name=name)
        self._clock = clock if clock is not None else default_clock()

    def _sample(self) -> float:
        """Return a pause duration in seconds."""
        raise NotImplementedError

    def initialise(self):
        self._pause_t = self._sample()
        self._start_t = self._clock.time()

    def update(self):
        t_elapse = self._clock.time() - self._start_t
        if t_elapse < self._pause_t:
            return py_trees.common.Status.RUNNING
        return py_trees.common.Status.SUCCESS


class PauseUniform(_SampledPause):
    """Pause for a duration drawn uniformly from ``[low, high]``.

    A new duration is sampled on each fresh entry, using :func:`random.uniform`
    from the standard library.

    The bounds are not validated; ``low`` greater than ``high`` yields samples
    from the reversed interval, as :func:`random.uniform` permits.

    Args:
        name (str): Name of this behavior node.
        low (float): Minimum pause duration in seconds.
        high (float): Maximum pause duration in seconds.
        clock (Clock): Time source for the pause, keyword-only. Defaults to the
            real clock; pass a :class:`py_branches.clock.ManualClock` to
            control it in tests.

    Returns:
        Status: RUNNING until the sampled duration elapses, then SUCCESS.

    Example:
        .. testcode::

            # Pause for between 2 and 5 seconds.
            pause = PauseUniform(name="ShortPause", low=2.0, high=5.0)
    """

    def __init__(
        self, name: str, low: float, high: float, *, clock: Clock | None = None
    ):
        super().__init__(name=name, clock=clock)
        self._high = high
        self._low = low

    def _sample(self) -> float:
        return random.uniform(self._low, self._high)


class PauseNormal(_SampledPause):
    """Pause for a duration drawn from a truncated normal distribution.

    The middle ground between :class:`PauseUniform`, which makes every duration
    in a range equally likely, and :class:`PausePDF`, which needs a file of
    recorded samples and fits a kernel density estimate to it. "About 1.2
    seconds, give or take 0.3" is two numbers here, and needs nothing beyond
    :func:`random.normalvariate` from the standard library.

    A new duration is sampled on each fresh entry. Draws outside
    ``[min_t, max_t]`` are rejected and redrawn rather than clamped to the
    bound, which keeps the truncated distribution's shape instead of piling
    probability mass exactly on the bounds. ``min_t`` defaults to 0.0, so a
    negative pause is impossible even when ``sigma`` is large relative to
    ``mean``.

    Note:
        A normal distribution is symmetric, which makes it the right model when
        durations genuinely cluster around a typical value. Human reaction and
        dwell times are not symmetric — mostly short with an occasional long
        tail — so a log-normal distribution usually describes them better.

    Args:
        name (str): Name of this behavior node.
        mean (float): Mean of the underlying normal distribution, in seconds.
        sigma (float): Standard deviation of the underlying normal
            distribution, in seconds. Must be positive.
        min_t (float): Keyword-only. Lower bound on the sampled pause, in
            seconds. Default 0.0.
        max_t (float): Keyword-only. Upper bound on the sampled pause, in
            seconds. Default unbounded.
        max_rejections (int): Keyword-only. How many out-of-bounds draws to
            discard before giving up on a sample. Default 100 — unreachable for
            sane parameters, so exhausting it means the parameters are wrong.
        clock (Clock): Time source for the pause, keyword-only. Defaults to the
            real clock; pass a :class:`py_branches.clock.ManualClock` to
            control it in tests.
        rng (Optional[random.Random]): Keyword-only. Source of randomness.
            Defaults to the :mod:`random` module's shared generator; pass a
            ``random.Random(seed)`` for reproducible durations.

    Returns:
        Status: RUNNING until the sampled duration elapses, then SUCCESS.

    Raises:
        ValueError: If ``sigma`` is not positive, ``min_t`` is negative,
            ``max_t`` is not above ``min_t``, or ``max_rejections`` is less
            than 1. Also raised when sampling if ``max_rejections``
            consecutive draws all fall outside the bounds, which happens when
            ``mean`` sits many ``sigma`` away from the permitted range.

    Example:
        .. testcode::

            # Pause for about 1.2 seconds, give or take 0.3, never under 0.5.
            pause = PauseNormal(name="ThinkTime", mean=1.2, sigma=0.3, min_t=0.5)
    """

    def __init__(
        self,
        name: str,
        mean: float,
        sigma: float,
        *,
        min_t: float = 0.0,
        max_t: float = math.inf,
        max_rejections: int = 100,
        clock: Clock | None = None,
        rng: random.Random | None = None,
    ):
        if sigma <= 0.0:
            raise ValueError(f"sigma({sigma}) must be positive.")
        if min_t < 0.0:
            raise ValueError(f"min_t({min_t}) must be >= 0.")
        if max_t <= min_t:
            raise ValueError(f"max_t({max_t}) must be > min_t({min_t}).")
        if max_rejections < 1:
            raise ValueError(f"max_rejections({max_rejections}) must be >= 1.")

        super().__init__(name=name, clock=clock)
        self._mean = mean
        self._sigma = sigma
        self._min_t = min_t
        self._max_t = max_t
        self._max_rejections = max_rejections
        # The random module itself exposes normalvariate, so the default costs
        # no generator of its own and shares seeding with the rest of py_branches.
        self._rng = rng if rng is not None else random

    def _sample(self) -> float:
        for _ in range(self._max_rejections):
            t_wait = self._rng.normalvariate(self._mean, self._sigma)
            if self._min_t <= t_wait <= self._max_t:
                return t_wait
        raise ValueError(
            f"{self.name}: {self._max_rejections} consecutive draws from "
            + f"normal(mean={self._mean}, sigma={self._sigma}) all fell outside "
            + f"[min_t({self._min_t}), max_t({self._max_t})]; the distribution "
            + "and the bounds disagree."
        )


class PausePDF(_SampledPause):
    """Pause for a duration sampled from a KDE fit to a file of float samples.

    The file holds one float per line, in seconds; blank lines and lines
    starting with ``#`` are ignored. A Gaussian kernel density estimate is
    fitted to those samples once, at construction, and each entry draws a new
    duration from it.

    Sampling is rejected and retried until the draw falls within
    ``[min_t, max_t]``, which is what keeps a Gaussian kernel from ever
    producing a negative pause.

    The rejection loop is bounded by ``max_rejections``, so bounds that exclude
    essentially all of the fitted distribution's mass raise a ``ValueError``
    naming them rather than spinning forever inside a tick.

    Args:
        name (str): Name of this behavior node.
        filepath (str): Path to the newline-separated sample file.
        kernel_bandwidth (float): Bandwidth of the Gaussian kernel. Larger
            values smooth the fitted distribution. Default 1.0.
        min_t (float): Lower bound on the sampled pause, in seconds.
            Default 0.0.
        max_t (float): Upper bound on the sampled pause, in seconds. Default
            unbounded.
        max_rejections (int): Keyword-only. How many out-of-bounds draws to
            discard before giving up on a sample. Default 100.
        clock (Clock): Time source for the pause, keyword-only. Defaults to the
            real clock; pass a :class:`py_branches.clock.ManualClock` to
            control it in tests.

    Returns:
        Status: RUNNING until the sampled duration elapses, then SUCCESS.

    Raises:
        FileNotFoundError: If ``filepath`` is not a file.
        AssertionError: If the file contains no usable samples.
        ValueError: If ``max_rejections`` is less than 1, or — when sampling —
            if that many consecutive draws all fall outside
            ``[min_t, max_t]``.

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
        max_t: float = float("inf"),
        *,
        max_rejections: int = 100,
        clock: Clock | None = None,
    ):
        super().__init__(name=name, clock=clock)
        if max_rejections < 1:
            raise ValueError(f"max_rejections({max_rejections}) must be >= 1.")
        if not os.path.isfile(filepath):
            raise FileNotFoundError(f"filepath: {filepath} is not a valid file")

        samples = []
        with open(filepath) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                samples.append(float(line))
        assert len(samples), f"filepath: {filepath} contains no float samples"

        self._filepath = filepath
        self._min_t = min_t
        self._max_t = max_t
        self._max_rejections = max_rejections
        self._model = KernelDensity(bandwidth=kernel_bandwidth, kernel="gaussian")
        self._model.fit(np.asarray(samples).reshape(-1, 1))

    def _sample(self) -> float:
        for _ in range(self._max_rejections):
            t_wait = float(self._model.sample(1)[0][0])  # pyright: ignore
            if self._min_t <= t_wait <= self._max_t:
                self.logger.debug(f"{self.name} sampled pause {t_wait:.3f} sec")
                return t_wait
        raise ValueError(
            f"{self.name}: {self._max_rejections} consecutive draws from "
            + f"{self._filepath} all fell outside "
            + f"[min_t({self._min_t}), max_t({self._max_t})]; the bounds and "
            + "the sample data disagree."
        )


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
        .. testcode::

            # Hold the tree until the operator presses space.
            gate = PauseUntilKey(name="WaitForSpace", key="space")
    """

    def __init__(self, name: str, key: str, listener_factory=_create_keyboard_listener):
        super().__init__(name=name)
        self._key = key
        self._listener_factory = listener_factory
        self._listener = None
        self._pressed = False

    def _matches(self, key) -> bool:
        char = getattr(key, "char", None)
        if char is not None and char == self._key:
            return True
        name = getattr(key, "name", None)
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
        raise FileNotFoundError(
            f"schedule_filepath: {schedule_filepath} is not a valid file"
        )

    with open(schedule_filepath) as schedule_file:
        schedule_raw = yaml.safe_load(schedule_file)

    if schedule_raw is None:
        logging.error(f"Failed to load schedule_file: {schedule_filepath}")
        return None

    schedule = []
    for schedule_element_raw in schedule_raw:
        start_pause_time = datetime.datetime.strptime(
            schedule_element_raw["start_pause_time"], "%H:%M:%S"
        ).time()
        stop_pause_time = datetime.datetime.strptime(
            schedule_element_raw["stop_pause_time"], "%H:%M:%S"
        ).time()
        variance_time = datetime.datetime.strptime(
            schedule_element_raw["variance"], "%H:%M:%S"
        ).time()
        schedule.append(
            {
                "start_pause_time": start_pause_time,
                "stop_pause_time": stop_pause_time,
                "variance_time": variance_time,
                "start_plus_variance_time": add_variance_to_datetime_time(
                    start_pause_time, variance_time
                ),
                "stop_plus_variance_time": add_variance_to_datetime_time(
                    stop_pause_time, variance_time
                ),
            }
        )
    return schedule


def datetime_time_to_sec(t: datetime.time):
    """Convert a time of day to seconds since midnight.

    Sub-second precision is discarded.

    Args:
        t (datetime.time): Time to convert.

    Returns:
        int: Seconds elapsed since midnight.
    """
    sec = t.hour * HOUR2SEC + t.minute * MIN2SEC + t.second
    return sec


def add_variance_to_datetime_time(
    t: datetime.time, variance_time: datetime.time
) -> datetime.time:
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
    If the current time falls outside every window, it returns immediately, so
    the behavior is cheap to tick continuously: SUCCESS by default, which lets
    it gate a parent Sequence, or FAILURE with ``fail_outside_window``, which
    lets a parent Selector fall through to the next child.

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
        clock (Clock): Time source, keyword-only. Both the time of day used to
            match a window and the remaining-time countdown are read from it,
            so a :class:`py_branches.clock.ManualClock` started at a chosen
            timestamp puts a test at any hour without touching the real clock.
        fail_outside_window (bool): Return FAILURE instead of SUCCESS when no
            pause is taken (outside every window, or inside a window already
            handled), keyword-only. Use it when this behavior is a Selector
            child that should interrupt the children after it. Default False.

    Returns:
        Status: RUNNING while a pause is active and SUCCESS once the active
        window's stop time is reached. When no pause is taken, SUCCESS, or
        FAILURE if ``fail_outside_window`` is set.

    Example:
        .. code-block:: python

            from py_branches.pause import PauseSchedule, load_schedule_file

            schedule = load_schedule_file("configs/schedules/example_schedule.yaml")
            if schedule is None:
                raise SystemExit("schedule file is empty")

            pause = PauseSchedule(name="ScheduledPause", schedule=schedule)

            root = py_trees.composites.Sequence(name="Root", memory=True)
            root.add_children([pause, main_behavior])

            # Or as an interrupt: the Selector runs main_behavior except
            # while a break is in progress.
            pause = PauseSchedule(
                name="ScheduledPause", schedule=schedule, fail_outside_window=True
            )
            root = py_trees.composites.Selector(name="Root", memory=False)
            root.add_children([pause, main_behavior])
    """

    def __init__(
        self,
        name: str,
        schedule: list[dict[str, datetime.time]],
        *,
        clock: Clock | None = None,
        fail_outside_window: bool = False,
    ):
        self._schedule = schedule
        self._fail_outside_window = fail_outside_window
        self._clock = clock if clock is not None else default_clock()
        self._last_schedule_idx = None
        super().__init__(name=name)

    def initialise(self):
        super().initialise()
        self._t_wait = None
        self._t_start = self._clock.time()
        now_time = _time_of_day(self._clock)
        matched_idx = None
        for idx, schedule_element in enumerate(self._schedule):
            start = schedule_element["start_plus_variance_time"]
            stop = schedule_element["stop_plus_variance_time"]
            if (start < stop and start < now_time < stop) or (
                start > stop and (now_time > start or now_time < stop)
            ):
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
        stop = schedule_element["stop_plus_variance_time"]
        variance = schedule_element["variance_time"]
        if now_time < stop:
            self._t_wait = datetime_time_to_sec(stop) - datetime_time_to_sec(now_time)
        else:
            self._t_wait = (
                datetime_time_to_sec(datetime.time(23, 59, 59))
                + 1
                - datetime_time_to_sec(now_time)
                + datetime_time_to_sec(stop)
            )
        self._t_start = self._clock.time()
        logging.info(f"Wait has been scheduled for  {self._t_wait:.3f} sec")
        schedule_element["start_plus_variance_time"] = add_variance_to_datetime_time(
            schedule_element["start_pause_time"], variance
        )
        schedule_element["stop_plus_variance_time"] = add_variance_to_datetime_time(
            schedule_element["stop_pause_time"], variance
        )
        logging.info(
            f"new start_plus_variance_time: {schedule_element['start_plus_variance_time']}"
        )
        logging.info(
            f"new stop_plus_variance_time: {schedule_element['stop_plus_variance_time']}"
        )

    def update(self):
        if self._t_wait is None:
            if self._fail_outside_window:
                return py_trees.common.Status.FAILURE
            return py_trees.common.Status.SUCCESS

        t_elapse = self._clock.time() - self._t_start
        if t_elapse < self._t_wait:
            return py_trees.common.Status.RUNNING
        else:
            return py_trees.common.Status.SUCCESS
