#!/usr/bin/env python

import math
import random

import pytest

from py_branches.delay import Delay
from py_branches.delay import DelayConstant
from py_branches.delay import DelayExponentialBackoff
from py_branches.delay import DelayLinearBackoff
from py_branches.delay import DelayNormal
from py_branches.delay import DelayUniform
from py_branches.delay import as_delay


class UntouchableRng:
    """An rng that fails the test if anything draws from it."""

    def uniform(self, a, b):
        raise AssertionError("rng was used")

    def normalvariate(self, mu, sigma):
        raise AssertionError("rng was used")


class FixedRng:
    """uniform() always returns its upper bound."""

    def uniform(self, a, b):
        return b


def test_every_delay_satisfies_the_protocol():
    for delay in [
        DelayConstant(1.0),
        DelayUniform(0.0, 1.0),
        DelayNormal(1.0, 0.1),
        DelayLinearBackoff(1.0, 0.5),
        DelayExponentialBackoff(1.0),
    ]:
        assert isinstance(delay, Delay)


def test_constant_ignores_run():
    delay = DelayConstant(1.5)
    assert [delay.sample(run) for run in range(1, 5)] == [1.5] * 4


def test_uniform_stays_within_bounds():
    delay = DelayUniform(0.2, 0.8, rng=random.Random(0))
    assert all(0.2 <= delay.sample(1) <= 0.8 for _ in range(1000))


def test_uniform_seeded_is_reproducible():
    first = DelayUniform(0.0, 1.0, rng=random.Random(42))
    second = DelayUniform(0.0, 1.0, rng=random.Random(42))
    assert [first.sample(1) for _ in range(10)] == [second.sample(1) for _ in range(10)]


def test_normal_respects_bounds():
    delay = DelayNormal(1.0, 1.0, min_t=0.5, max_t=1.5, rng=random.Random(1))
    assert all(0.5 <= delay.sample(1) <= 1.5 for _ in range(1000))


def test_normal_rejection_cap_raises():
    delay = DelayNormal(0.0, 0.01, min_t=100.0)
    with pytest.raises(ValueError, match=r"min_t\(100.0\)"):
        delay.sample(1)


def test_linear_backoff_sequence():
    delay = DelayLinearBackoff(1.0, 0.5)
    assert [delay.sample(run) for run in range(1, 6)] == [1.0, 1.5, 2.0, 2.5, 3.0]


def test_linear_backoff_capped():
    delay = DelayLinearBackoff(1.0, 1.0, max_delay=2.5)
    assert [delay.sample(run) for run in range(1, 6)] == [1.0, 2.0, 2.5, 2.5, 2.5]


def test_exponential_backoff_sequence():
    delay = DelayExponentialBackoff(0.5)
    assert [delay.sample(run) for run in range(1, 6)] == [0.5, 1.0, 2.0, 4.0, 8.0]


def test_exponential_backoff_custom_factor():
    delay = DelayExponentialBackoff(1.0, 3.0)
    assert [delay.sample(run) for run in range(1, 5)] == [1.0, 3.0, 9.0, 27.0]


def test_exponential_backoff_capped():
    delay = DelayExponentialBackoff(1.0, max_delay=5.0)
    assert [delay.sample(run) for run in range(1, 6)] == [1.0, 2.0, 4.0, 5.0, 5.0]


def test_exponential_backoff_large_run_does_not_overflow():
    assert DelayExponentialBackoff(1.0, max_delay=60.0).sample(10_000) == 60.0
    assert DelayExponentialBackoff(1.0).sample(10_000) == math.inf


@pytest.mark.parametrize(
    "delay, expected",
    [
        (DelayExponentialBackoff(0.0), 0.0),
        (DelayExponentialBackoff(2.0, 1.0), 2.0),
        (DelayExponentialBackoff(2.0, max_delay=1.0), 1.0),
        (DelayExponentialBackoff(2.0, max_delay=0.0), 0.0),
    ],
)
def test_exponential_backoff_degenerate_parameters(delay, expected):
    assert [delay.sample(run) for run in range(1, 4)] == [expected] * 3


@pytest.mark.parametrize(
    "make",
    [
        lambda rng: DelayLinearBackoff(1.0, 1.0, rng=rng),
        lambda rng: DelayExponentialBackoff(1.0, rng=rng),
    ],
)
def test_backoff_without_jitter_never_touches_rng(make):
    delay = make(UntouchableRng())
    for run in range(1, 5):
        delay.sample(run)


@pytest.mark.parametrize(
    "make",
    [
        lambda: DelayLinearBackoff(2.0, 0.0, jitter=0.25, rng=random.Random(5)),
        lambda: DelayExponentialBackoff(2.0, 1.0, jitter=0.25, rng=random.Random(5)),
    ],
)
def test_backoff_jitter_stays_within_fraction(make):
    delay = make()
    samples = [delay.sample(1) for _ in range(1000)]
    assert all(1.5 <= s <= 2.5 for s in samples)
    assert len(set(samples)) > 1


def test_jitter_is_applied_after_the_cap():
    delay = DelayExponentialBackoff(1.0, max_delay=4.0, jitter=0.5, rng=FixedRng())
    assert delay.sample(10) == 6.0


def test_shared_instance_is_stateless():
    delay = DelayExponentialBackoff(1.0)
    first = [delay.sample(run) for run in range(1, 4)]
    second = [delay.sample(run) for run in range(1, 4)]
    assert first == second == [1.0, 2.0, 4.0]


@pytest.mark.parametrize(
    "make, message",
    [
        (lambda: DelayConstant(-1.0), r"seconds\(-1.0\)"),
        (lambda: DelayUniform(-1.0, 1.0), r"low\(-1.0\)"),
        (lambda: DelayUniform(2.0, 1.0), r"low\(2.0\) must be <= high"),
        (lambda: DelayNormal(1.0, 0.0), r"sigma\(0.0\)"),
        (lambda: DelayNormal(1.0, 0.1, min_t=-1.0), r"min_t\(-1.0\)"),
        (lambda: DelayNormal(1.0, 0.1, min_t=2.0, max_t=2.0), r"max_t\(2.0\)"),
        (lambda: DelayNormal(1.0, 0.1, max_rejections=0), r"max_rejections\(0\)"),
        (lambda: DelayLinearBackoff(-1.0, 1.0), r"initial\(-1.0\)"),
        (lambda: DelayLinearBackoff(1.0, -1.0), r"step\(-1.0\)"),
        (lambda: DelayLinearBackoff(1.0, 1.0, max_delay=-1.0), r"max_delay\(-1.0\)"),
        (lambda: DelayLinearBackoff(1.0, 1.0, jitter=1.5), r"jitter\(1.5\)"),
        (lambda: DelayExponentialBackoff(-1.0), r"base\(-1.0\)"),
        (lambda: DelayExponentialBackoff(1.0, 0.5), r"factor\(0.5\)"),
        (lambda: DelayExponentialBackoff(1.0, jitter=-0.1), r"jitter\(-0.1\)"),
    ],
)
def test_validation(make, message):
    with pytest.raises(ValueError, match=message):
        make()


def test_as_delay_wraps_numbers():
    delay = as_delay(2)
    assert isinstance(delay, DelayConstant)
    assert delay.sample(1) == 2.0


def test_as_delay_passes_delays_through():
    delay = DelayUniform(0.0, 1.0)
    assert as_delay(delay) is delay


def test_as_delay_rejects_negative_numbers():
    with pytest.raises(ValueError, match=r"delay\(-0.5\) must be non-negative"):
        as_delay(-0.5)


@pytest.mark.parametrize("value", ["1.0", None, True])
def test_as_delay_rejects_other_types(value):
    with pytest.raises(TypeError, match="number of seconds or a Delay"):
        as_delay(value)


def test_reprs_are_readable():
    assert repr(DelayConstant(1.0)) == "DelayConstant(1.0)"
    assert repr(DelayExponentialBackoff(0.5)) == "DelayExponentialBackoff(0.5, 2.0)"
