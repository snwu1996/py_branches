#!/usr/bin/env python3
"""Waits to hand to behaviors: fixed, random, or growing with each run.

A behavior that waits between runs takes a ``delay``. A plain float is a fixed
wait in seconds; anything implementing :class:`Delay` decides the wait itself,
so the same behavior can wait a constant time, a random time, or a time that
backs off as runs pile up.

==================================== ==========================================
Name                                 What it is
==================================== ==========================================
:class:`Delay`                       The protocol: ``sample(run)``
:class:`DelayConstant`               Always the same number of seconds
:class:`DelayUniform`                Drawn uniformly between two bounds
:class:`DelayNormal`                 Drawn from a truncated normal distribution
:class:`DelayLinearBackoff`          Grows by a fixed step each run
:class:`DelayExponentialBackoff`     Grows by a fixed factor each run
:func:`as_delay`                     Turns a float or a :class:`Delay` into a
                                     :class:`Delay`
==================================== ==========================================

:class:`Delay` is a :class:`typing.Protocol`, so anything with a matching
``sample`` method qualifies; there is no base class to inherit.

``sample`` is given the run number rather than keeping a counter of its own,
so every implementation here is stateless apart from its random generator. One
instance can therefore be shared by several behaviors without one behavior's
runs advancing another's backoff.

Which behaviors accept one: :class:`py_branches.retry.Retry`,
:class:`py_branches.retry.RunUntilFailed`,
:class:`py_branches.retry.RunUntilXSuccesses` and
:class:`py_branches.random.RandomDelay`.

Example:
    .. testcode::

        from py_branches.delay import DelayExponentialBackoff

        backoff = DelayExponentialBackoff(base=0.5, max_delay=4.0)
        print([backoff.sample(run) for run in range(1, 6)])

    .. testoutput::

        [0.5, 1.0, 2.0, 4.0, 4.0]
"""

import math
import random
from typing import Protocol
from typing import runtime_checkable


@runtime_checkable
class Delay(Protocol):
    """A source of wait durations.

    Behaviors call :meth:`sample` once per wait and hold the result until the
    wait is over, so a random delay is drawn once per gap rather than once per
    tick.
    """

    def sample(self, run: int) -> float:
        """Return the next wait in seconds.

        Args:
            run (int): How many runs have finished before this wait, starting
                at 1 for the first wait. Backoff delays grow with it; the
                others ignore it.

        Returns:
            float: Seconds to wait, never negative.
        """
        ...


def _truncated_normal(rng, mean, sigma, min_t, max_t, max_rejections, label):
    """Draw from normal(mean, sigma), rejecting draws outside [min_t, max_t].

    Rejection rather than clamping keeps the truncated distribution's shape
    instead of piling probability mass exactly on the bounds.
    """
    for _ in range(max_rejections):
        t_wait = rng.normalvariate(mean, sigma)
        if min_t <= t_wait <= max_t:
            return t_wait
    raise ValueError(
        f"{label}: {max_rejections} consecutive draws from "
        + f"normal(mean={mean}, sigma={sigma}) all fell outside "
        + f"[min_t({min_t}), max_t({max_t})]; the distribution "
        + "and the bounds disagree."
    )


def _check_backoff_tail(max_delay: float, jitter: float) -> None:
    if max_delay < 0.0:
        raise ValueError(f"max_delay({max_delay}) must be non-negative.")
    if not 0.0 <= jitter <= 1.0:
        raise ValueError(f"jitter({jitter}) must be between 0 and 1.")


def _apply_jitter(wait: float, jitter: float, rng) -> float:
    if jitter == 0.0:
        return wait
    return wait * rng.uniform(1.0 - jitter, 1.0 + jitter)


class DelayConstant:
    """Always wait the same number of seconds.

    This is what a plain float passed as ``delay`` turns into.

    Args:
        seconds (float): The wait. Must be non-negative.

    Raises:
        ValueError: If ``seconds`` is negative.

    Example:
        .. testcode::

            delay = DelayConstant(1.5)
    """

    def __init__(self, seconds: float):
        if seconds < 0.0:
            raise ValueError(f"seconds({seconds}) must be non-negative.")
        self._seconds = seconds

    def sample(self, run: int) -> float:
        return self._seconds

    def __repr__(self) -> str:
        return f"DelayConstant({self._seconds})"


class DelayUniform:
    """Wait a duration drawn uniformly from ``[low, high]``.

    Args:
        low (float): Shortest wait in seconds. Must be non-negative.
        high (float): Longest wait in seconds. Must be at least ``low``.
        rng (Optional[random.Random]): Keyword-only. Source of randomness.
            Defaults to the :mod:`random` module's shared generator; pass a
            ``random.Random(seed)`` for reproducible waits.

    Raises:
        ValueError: If ``low`` is negative, or greater than ``high``.

    Example:
        .. testcode::

            # Somewhere between 0.2 and 0.8 seconds.
            delay = DelayUniform(0.2, 0.8)
    """

    def __init__(self, low: float, high: float, *, rng: random.Random | None = None):
        if low < 0.0:
            raise ValueError(f"low({low}) must be >= 0.")
        if low > high:
            raise ValueError(f"low({low}) must be <= high({high}).")
        self._low = low
        self._high = high
        self._rng = rng if rng is not None else random

    def sample(self, run: int) -> float:
        return self._rng.uniform(self._low, self._high)

    def __repr__(self) -> str:
        return f"DelayUniform({self._low}, {self._high})"


class DelayNormal:
    """Wait a duration drawn from a truncated normal distribution.

    Draws outside ``[min_t, max_t]`` are rejected and redrawn rather than
    clamped, with the same semantics as
    :class:`py_branches.pause.PauseNormal`. ``min_t`` defaults to 0.0, so a
    negative wait is impossible.

    Args:
        mean (float): Mean of the underlying normal distribution, in seconds.
        sigma (float): Standard deviation, in seconds. Must be positive.
        min_t (float): Keyword-only. Shortest wait, in seconds. Default 0.0.
        max_t (float): Keyword-only. Longest wait, in seconds. Default
            unbounded.
        max_rejections (int): Keyword-only. How many out-of-bounds draws to
            discard before giving up on a sample. Default 100.
        rng (Optional[random.Random]): Keyword-only. Source of randomness.
            Defaults to the :mod:`random` module's shared generator.

    Raises:
        ValueError: If ``sigma`` is not positive, ``min_t`` is negative,
            ``max_t`` is not above ``min_t``, or ``max_rejections`` is less
            than 1. Also raised when sampling if ``max_rejections``
            consecutive draws all fall outside the bounds.

    Example:
        .. testcode::

            # About a second, give or take 0.2, never under half a second.
            delay = DelayNormal(1.0, 0.2, min_t=0.5)
    """

    def __init__(
        self,
        mean: float,
        sigma: float,
        *,
        min_t: float = 0.0,
        max_t: float = math.inf,
        max_rejections: int = 100,
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
        self._mean = mean
        self._sigma = sigma
        self._min_t = min_t
        self._max_t = max_t
        self._max_rejections = max_rejections
        self._rng = rng if rng is not None else random

    def sample(self, run: int) -> float:
        return _truncated_normal(
            self._rng,
            self._mean,
            self._sigma,
            self._min_t,
            self._max_t,
            self._max_rejections,
            repr(self),
        )

    def __repr__(self) -> str:
        return f"DelayNormal({self._mean}, {self._sigma})"


class DelayLinearBackoff:
    """Wait ``initial + step * (run - 1)`` seconds, capped at ``max_delay``.

    Use it when each failed or repeated run should give the thing being called
    a little more room than the last.

    ``jitter`` spreads each wait by a random factor in ``[1 - jitter,
    1 + jitter]``, so several callers backing off together do not all retry
    at the same instant. It is applied after the cap, so with jitter on a wait
    can exceed ``max_delay`` by up to that fraction.

    Args:
        initial (float): The first wait, in seconds. Must be non-negative.
        step (float): Seconds added per run. Must be non-negative.
        max_delay (float): Keyword-only. Cap on the wait before jitter.
            Default unbounded.
        jitter (float): Keyword-only. Fractional spread, between 0 and 1.
            Default 0.0, which never touches ``rng``.
        rng (Optional[random.Random]): Keyword-only. Source of randomness for
            the jitter. Defaults to the :mod:`random` module's shared
            generator.

    Raises:
        ValueError: If ``initial``, ``step`` or ``max_delay`` is negative, or
            ``jitter`` is outside ``[0, 1]``.

    Example:
        .. testcode::

            # 1, 1.5, 2, 2.5 ... seconds, never more than 5.
            delay = DelayLinearBackoff(1.0, 0.5, max_delay=5.0)
    """

    def __init__(
        self,
        initial: float,
        step: float,
        *,
        max_delay: float = math.inf,
        jitter: float = 0.0,
        rng: random.Random | None = None,
    ):
        if initial < 0.0:
            raise ValueError(f"initial({initial}) must be non-negative.")
        if step < 0.0:
            raise ValueError(f"step({step}) must be non-negative.")
        _check_backoff_tail(max_delay, jitter)
        self._initial = initial
        self._step = step
        self._max_delay = max_delay
        self._jitter = jitter
        self._rng = rng if rng is not None else random

    def sample(self, run: int) -> float:
        wait = min(self._initial + self._step * (run - 1), self._max_delay)
        return _apply_jitter(wait, self._jitter, self._rng)

    def __repr__(self) -> str:
        return f"DelayLinearBackoff({self._initial}, {self._step})"


class DelayExponentialBackoff:
    """Wait ``base * factor ** (run - 1)`` seconds, capped at ``max_delay``.

    The usual choice for a flaky remote service: quick retries at first, then
    progressively longer gaps so a struggling service is not hammered.

    ``jitter`` spreads each wait by a random factor in ``[1 - jitter,
    1 + jitter]``, so several callers backing off together do not all retry
    at the same instant. It is applied after the cap, so with jitter on a wait
    can exceed ``max_delay`` by up to that fraction.

    Args:
        base (float): The first wait, in seconds. Must be non-negative.
        factor (float): Multiplier per run. Must be at least 1. Default 2.0.
        max_delay (float): Keyword-only. Cap on the wait before jitter.
            Default unbounded.
        jitter (float): Keyword-only. Fractional spread, between 0 and 1.
            Default 0.0, which never touches ``rng``.
        rng (Optional[random.Random]): Keyword-only. Source of randomness for
            the jitter. Defaults to the :mod:`random` module's shared
            generator.

    Raises:
        ValueError: If ``base`` or ``max_delay`` is negative, ``factor`` is
            less than 1, or ``jitter`` is outside ``[0, 1]``.

    Example:
        .. testcode::

            # 0.5, 1, 2, 4 ... seconds, never more than 30, spread by 10%.
            delay = DelayExponentialBackoff(0.5, max_delay=30.0, jitter=0.1)
    """

    def __init__(
        self,
        base: float,
        factor: float = 2.0,
        *,
        max_delay: float = math.inf,
        jitter: float = 0.0,
        rng: random.Random | None = None,
    ):
        if base < 0.0:
            raise ValueError(f"base({base}) must be non-negative.")
        if factor < 1.0:
            raise ValueError(f"factor({factor}) must be >= 1.")
        _check_backoff_tail(max_delay, jitter)
        self._base = base
        self._factor = factor
        self._max_delay = max_delay
        self._jitter = jitter
        self._rng = rng if rng is not None else random

    def sample(self, run: int) -> float:
        exponent = run - 1
        if self._base == 0.0 or self._factor == 1.0 or self._max_delay <= self._base:
            wait = min(self._base, self._max_delay)
        elif exponent * math.log(self._factor) >= math.log(
            self._max_delay / self._base
        ):
            # Past the cap; checked in log space so a large run cannot
            # overflow factor ** exponent.
            wait = self._max_delay
        else:
            try:
                wait = self._base * self._factor**exponent
            except OverflowError:
                # Only reachable with an unbounded max_delay.
                wait = math.inf
        return _apply_jitter(wait, self._jitter, self._rng)

    def __repr__(self) -> str:
        return f"DelayExponentialBackoff({self._base}, {self._factor})"


def as_delay(value: "float | Delay", *, name: str = "delay") -> Delay:
    """Return ``value`` as a :class:`Delay`.

    A number becomes a :class:`DelayConstant`; a :class:`Delay` is returned
    unchanged. Behaviors call this on their ``delay`` argument, so callers can
    pass either.

    Args:
        value (float | Delay): Seconds, or a :class:`Delay`.
        name (str): Keyword-only. Parameter name used in error messages.

    Raises:
        ValueError: If ``value`` is a negative number.
        TypeError: If ``value`` is neither a number nor a :class:`Delay`.
    """
    if isinstance(value, Delay):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value < 0.0:
            raise ValueError(f"{name}({value}) must be non-negative.")
        return DelayConstant(float(value))
    raise TypeError(
        f"{name} must be a number of seconds or a Delay, not {type(value).__name__}."
    )
