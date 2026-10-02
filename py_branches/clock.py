#!/usr/bin/env python3
"""Injectable time sources, so time-based behaviors are testable.

Every behavior in this package that measures elapsed time takes a keyword-only
``clock`` argument. Left alone it reads the real clock; handed a
:class:`ManualClock` it reads whatever the test says, which turns a timing test
from "sleep and hope" into an exact assertion.

============================ ==================================================
Name                         What it is
============================ ==================================================
:class:`Clock`               The protocol: ``time()`` and ``sleep()``
:class:`SystemClock`         The default — real wall-clock time
:class:`ManualClock`         A clock that only moves when a test moves it
:func:`default_clock`        The shared :class:`SystemClock` used as the default
============================ ==================================================

:class:`Clock` is a :class:`typing.Protocol`, so anything with the right two
methods qualifies; there is no base class to inherit. That is what lets a
downstream package supply its own time source — a simulation clock, a clock
slaved to a replayed trace — without importing anything from here.

Which behaviors accept one: :class:`py_branches.cooldown.Cooldown`,
:class:`py_branches.timeout.Timeout`, :class:`py_branches.retry.Retry`,
:class:`py_branches.random.RandomDelay`,
:class:`py_branches.visitors.TimerVisitor`, and the timed pauses
:class:`py_branches.pause.PauseUniform`, :class:`py_branches.pause.PauseNormal`,
:class:`py_branches.pause.PausePDF` and
:class:`py_branches.pause.PauseSchedule`.

Example:
    .. testcode::

        from py_branches.clock import ManualClock
        from py_branches.cooldown import Cooldown

        clock = ManualClock()
        cooled = Cooldown(
            py_trees.behaviours.Success(name="Work"),
            name="Cooldown",
            duration=5.0,
            clock=clock,
        )

        cooled.tick_once()                  # runs
        cooled.tick_once()                  # cooling, child not ticked
        clock.advance(5.0)                  # no real time passes
        cooled.tick_once()                  # re-armed, runs again
"""

import time
from typing import Protocol
from typing import runtime_checkable


@runtime_checkable
class Clock(Protocol):
    """A source of elapsed time.

    Two methods, matching the subset of the :mod:`time` module that the
    behaviors in this package actually use. Implementations are expected to be
    cheap to call, since ``time()`` is read on most ticks.
    """

    def time(self) -> float:
        """Return the current time in seconds.

        Only differences between two readings are meaningful to this package,
        so the epoch is an implementation detail — except for
        :class:`py_branches.pause.PauseSchedule`, which reads the time of day
        and therefore wants a Unix timestamp.

        Returns:
            float: Seconds, monotonically non-decreasing.
        """
        ...

    def sleep(self, seconds: float) -> None:
        """Advance to ``seconds`` from now.

        A real clock blocks; a fake one just moves its own notion of now
        forward. Behaviors in this package tick cooperatively and so do not
        call this — it is here for the runners and pacing loops that do.

        Args:
            seconds (float): How long to sleep.
        """
        ...


class SystemClock:
    """The real clock: :func:`time.time` and :func:`time.sleep`.

    Stateless, so one instance can be shared by every behavior in a tree —
    which is what :func:`default_clock` does.

    Example:
        .. testcode::

            from py_branches.clock import SystemClock
            from py_branches.timeout import Timeout

            # Explicit, but identical to leaving `clock` unset.
            guarded = Timeout(
                py_trees.behaviours.Running(name="Slow"),
                name="Timeout",
                duration=5.0,
                clock=SystemClock(),
            )
    """

    def time(self) -> float:
        """Return :func:`time.time`.

        Returns:
            float: Seconds since the Unix epoch.
        """
        return time.time()

    def sleep(self, seconds: float) -> None:
        """Block for ``seconds`` via :func:`time.sleep`.

        Args:
            seconds (float): How long to block.
        """
        time.sleep(seconds)


class ManualClock:
    """A clock that moves only when told to. For tests.

    :meth:`advance` and :meth:`sleep` are the same operation under two names:
    both move the clock forward without any real time passing. The pair means a
    test can drive a behavior that sleeps and a behavior that polls with one
    object.

    Nothing stops the clock going backwards via a negative ``seconds``, and
    nothing in this package expects it to; behaviors comparing elapsed time
    against a duration will simply read as "not yet".

    Args:
        start (float): Initial value of :meth:`time`. Default 0.0. Pass a real
            Unix timestamp when the behavior under test cares about the time of
            day — see the :class:`py_branches.pause.PauseSchedule` example
            below.

    Example:
        .. testcode::

            from py_branches.clock import ManualClock

            clock = ManualClock()
            assert clock.time() == 0.0
            clock.advance(2.5)
            assert clock.time() == 2.5
            clock.sleep(0.5)            # returns immediately
            assert clock.time() == 3.0

        Pinned to a specific wall-clock time, for a behavior that reads the
        time of day:

        .. testcode::

            import datetime

            noon = datetime.datetime.combine(
                datetime.date.today(), datetime.time(12, 0, 0)
            )
            clock = ManualClock(start=noon.timestamp())
    """

    def __init__(self, start: float = 0.0) -> None:
        self._t = start

    def time(self) -> float:
        """Return the current value, unchanged since the last advance.

        Returns:
            float: The clock's current value in seconds.
        """
        return self._t

    def sleep(self, seconds: float) -> None:
        """Advance the clock by ``seconds`` without blocking.

        Args:
            seconds (float): How far to move the clock forward.
        """
        self._t += seconds

    def advance(self, seconds: float) -> None:
        """Move the clock forward by ``seconds``.

        Args:
            seconds (float): How far to move the clock forward.
        """
        self._t += seconds


_DEFAULT_CLOCK = SystemClock()


def default_clock() -> Clock:
    """Return the shared :class:`SystemClock` that behaviors default to.

    Every behavior with a ``clock`` argument falls back to this when the
    argument is omitted, so an unconfigured tree does one module-level
    allocation rather than one per node.

    Returns:
        Clock: The shared :class:`SystemClock` instance.
    """
    return _DEFAULT_CLOCK


__all__ = ["Clock", "SystemClock", "ManualClock", "default_clock"]
