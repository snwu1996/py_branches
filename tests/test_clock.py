#!/usr/bin/env python

import time

from py_branches.clock import Clock
from py_branches.clock import ManualClock
from py_branches.clock import SystemClock
from py_branches.clock import default_clock


def test_system_clock_tracks_real_time():
    clock = SystemClock()
    before = time.time()
    reading = clock.time()
    after = time.time()
    assert before <= reading <= after


def test_system_clock_sleep_actually_elapses():
    clock = SystemClock()
    start = clock.time()
    clock.sleep(0.02)
    assert clock.time() - start >= 0.02


def test_manual_clock_starts_at_zero_by_default():
    assert ManualClock().time() == 0.0


def test_manual_clock_starts_where_told():
    assert ManualClock(start=1234.5).time() == 1234.5


def test_manual_clock_time_is_stable_between_advances():
    clock = ManualClock()
    assert clock.time() == clock.time() == 0.0
    clock.advance(1.0)
    assert clock.time() == clock.time() == 1.0


def test_manual_clock_advance_accumulates():
    clock = ManualClock()
    clock.advance(1.5)
    clock.advance(2.0)
    assert clock.time() == 3.5


def test_manual_clock_sleep_advances_without_blocking():
    clock = ManualClock()
    wall_start = time.time()
    clock.sleep(30.0)
    wall_elapsed = time.time() - wall_start
    assert clock.time() == 30.0
    # The whole point: 30 clock-seconds cost no real time.
    assert wall_elapsed < 1.0


def test_manual_clock_advance_and_sleep_are_interchangeable():
    advanced = ManualClock()
    slept = ManualClock()
    advanced.advance(2.0)
    slept.sleep(2.0)
    assert advanced.time() == slept.time()


def test_both_clocks_satisfy_the_protocol():
    assert isinstance(SystemClock(), Clock)
    assert isinstance(ManualClock(), Clock)


def test_arbitrary_duck_typed_clock_satisfies_the_protocol():
    """The protocol is structural, so no base class is needed downstream."""

    class OwnClock:
        def time(self) -> float:
            return 0.0

        def sleep(self, seconds: float) -> None:
            pass

    assert isinstance(OwnClock(), Clock)


def test_incomplete_clock_does_not_satisfy_the_protocol():
    class NoSleep:
        def time(self) -> float:
            return 0.0

    assert not isinstance(NoSleep(), Clock)


def test_default_clock_is_a_shared_system_clock():
    assert default_clock() is default_clock()
    assert isinstance(default_clock(), SystemClock)
