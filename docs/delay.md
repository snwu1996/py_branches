# delay

A `Delay` describes how long a behavior should wait. A plain float still works
anywhere a `delay` is accepted and means a fixed number of seconds; a `Delay`
object lets the same behavior wait a random time instead, or a time that grows
with each run.

```python
from py_branches.delay import DelayExponentialBackoff, DelayUniform
from py_branches.retry import Retry, RunUntilFailed

# 0.5, 1, 2, 4 ... seconds between attempts, never more than 30
retried = Retry(
    child,
    name="Retry",
    max_attempts=8,
    delay=DelayExponentialBackoff(0.5, max_delay=30.0),
)

# Somewhere between 0.2 and 0.8 seconds between runs
drained = RunUntilFailed(
    child,
    name="Drain",
    max_runs=100,
    delay=DelayUniform(0.2, 0.8),
)
```

The re-run decorators in {doc}`retry` and `RandomDelay` in {doc}`random` accept
one.

## Choosing one

| Class | Wait | Reach for it when |
|---|---|---|
| `DelayConstant` | always `seconds` | you want a fixed gap; a float does the same |
| `DelayUniform` | uniform in `[low, high]` | any value in a range will do |
| `DelayNormal` | truncated normal around `mean` | waits should cluster around a typical value |
| `DelayLinearBackoff` | `initial + step * (run - 1)` | each run should allow a little more room |
| `DelayExponentialBackoff` | `base * factor ** (run - 1)` | a flaky service needs progressively longer to recover |

## The run number is passed in

`sample(run)` is given the number of runs that have finished, starting at 1 for
the first wait. The delay keeps no counter of its own, which has two
consequences:

- **One instance can be shared.** Two `Retry` decorators handed the same
  `DelayExponentialBackoff` each back off from the start; neither advances the
  other.
- **Backoff resets on entry.** The decorators reset their run count in
  `initialise()`, so a fresh entry into the subtree starts again from the first
  wait.

`RandomDelay` waits once per entry, not between runs, so it always samples with
`run=1` — a backoff passed to it does not grow.

The wait is sampled once per gap and held until the gap is over, not re-drawn on
every tick.

## Jitter

The backoff delays take a `jitter` fraction between 0 and 1. Each wait is
multiplied by a random factor in `[1 - jitter, 1 + jitter]`, so several callers
that fail together do not all retry at the same instant and pile onto a service
that is trying to recover.

Jitter is applied *after* the `max_delay` cap. With `max_delay=30.0` and
`jitter=0.1`, a capped wait lands anywhere in 27–33 seconds; if the cap must be
a hard ceiling, lower it by the jitter fraction.

## Reproducible randomness

Every random delay takes a keyword-only `rng`. Left alone it uses the `random`
module's shared generator, so `random.seed()` applies; pass a
`random.Random(seed)` to make one delay reproducible on its own:

```{testcode}
import random

from py_branches.delay import DelayUniform

delay = DelayUniform(0.2, 0.8, rng=random.Random(0))
first = [delay.sample(1) for _ in range(3)]

delay = DelayUniform(0.2, 0.8, rng=random.Random(0))
assert [delay.sample(1) for _ in range(3)] == first
```

## Writing your own

`Delay` is a `typing.Protocol`: any object with a `sample(run) -> float` method
qualifies, with nothing to inherit. Return a non-negative number of seconds.

## API

```{eval-rst}
.. automodule:: py_branches.delay
   :members:
```
