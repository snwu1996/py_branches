# clock

`Clock` is the time source every timed behavior in this package reads. Left
alone they read the real clock, so nothing here changes how a tree behaves in
production. Its reason for existing is the other case: handed a `ManualClock`, a
five-second cooldown can be tested in microseconds, exactly on its boundary.

## The problem it solves

Without an injected clock, a test for anything time-based has two options, and
both are bad. It can sleep:

```python
cooldown.tick_once()  # runs
cooldown.tick_once()  # cooling
time.sleep(5.01)  # five seconds of your CI budget, every run
cooldown.tick_once()  # re-armed
```

Or it can monkeypatch `time.time` out from under the module, which couples the
test to the implementation's choice of time function and breaks the moment that
changes.

Sleeping tests are also *flaky*, not merely slow: they assert on a duration that
the scheduler is free to overshoot, so the margin has to be padded until the
assertion barely says anything. With a manual clock the assertion is exact:

```python
clock = ManualClock()
cooled = Cooldown(child, name="Cooldown", duration=5.0, clock=clock)

cooled.tick_once()  # runs
cooled.tick_once()  # cooling
clock.advance(4.999)
cooled.tick_once()  # still cooling — one hair short
clock.advance(0.001)
cooled.tick_once()  # re-armed, exactly at the boundary
```

## `sleep()` advances, it does not block

`ManualClock.sleep()` and `ManualClock.advance()` are the same operation. That
is deliberate: a component that *paces* itself by sleeping and a test that wants
time to pass both go through the clock, so one fake serves both. The behaviors
in this package tick cooperatively and never call `sleep()` — they only read
`time()` — but the runners built on top of them do.

## Which behaviors take one

`clock` is keyword-only everywhere and defaults to the real clock, so adding it
to an existing call site is never required:

| Module | Class |
|---|---|
| {doc}`cooldown` | `Cooldown` |
| {doc}`timeout` | `Timeout` |
| {doc}`retry` | `Retry` |
| {doc}`random` | `RandomDelay` |
| {doc}`pause` | `PauseUniform`, `PausePDF`, `PauseSchedule` |
| {doc}`visitors` | `TimerVisitor` |

`PauseUntilKey` is the one time-shaped behavior without a clock — it waits on a
key press, not a duration. It takes a `listener_factory` for the same reason.

## Time of day, not just elapsed time

`PauseSchedule` is the only behavior that cares *what time it is* rather than
how much time has passed. It reads the time of day from `clock.time()`, treating
it as a Unix timestamp, so a `ManualClock` aimed at a chosen moment puts a test
at any hour:

```python
import datetime

from py_branches.clock import ManualClock

# Half past eleven at night, so an overnight window is active.
late = datetime.datetime.combine(datetime.date.today(), datetime.time(23, 30, 0))
clock = ManualClock(start=late.timestamp())

pause = PauseSchedule(name="ScheduledPause", schedule=schedule, clock=clock)
```

This is what makes the midnight-wrapping cases testable at all: on the real
clock they either depend on the hour CI happens to run at, or imply a wait of up
to 24 hours.

## Supplying your own

`Clock` is a {class}`typing.Protocol`, so any object with `time()` and `sleep()`
qualifies — there is no base class to inherit and nothing to import. A
simulation clock, or one slaved to a replayed trace, plugs in the same way
`ManualClock` does.

## API

```{eval-rst}
.. automodule:: py_branches.clock
   :members:
```
