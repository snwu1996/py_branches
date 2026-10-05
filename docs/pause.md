# pause

Five leaf behaviors that hold a tree still, differing only in where the wait
comes from. All of them return RUNNING while waiting and SUCCESS once done, so
the rest of the tree keeps ticking — none of them block.

## Choosing between them

| | Waits for | Use for |
|---|---|---|
| `PauseUniform` | A duration drawn between two bounds | General jitter, anything in a range |
| `PauseNormal` | A duration clustered around a typical value | Waits with a typical value and some spread |
| `PausePDF` | A duration drawn from recorded samples | Reproducing observed timing distributions |
| `PauseUntilKey` | A key press | Operator-gated steps, debugging |
| `PauseSchedule` | A wall-clock window from a YAML file | Idling overnight, or over lunch |

`PauseNormal` is the middle ground, and the cheapest of the three: two numbers
rather than a flat range or a file of recorded timings, and nothing beyond
`random.normalvariate` from the standard library. `PausePDF` is the one that
costs something — it fits a kernel density estimate, so it pulls in numpy and
scikit-learn — and it only earns that cost when you have real timings to
reproduce.

One caveat on `PauseNormal`: a normal distribution is symmetric. That fits a
wait which genuinely clusters around a typical value, but many measured
durations are not symmetric — mostly short, with an occasional long tail — and
a log-normal distribution describes them better.

## Truncation

`PauseNormal` and `PausePDF` both draw from a distribution that extends past the
duration you want, and both handle it the same way: a draw outside
`[min_t, max_t]` is **rejected and redrawn**, not clamped to the nearest bound.
Clamping would be simpler, but it piles probability mass exactly on the bounds,
so a pause would land on precisely `min_t` a few percent of the time. Rejection
keeps the truncated distribution's shape.

`PauseNormal`'s `min_t` defaults to `0.0`, so a negative pause is impossible
however large `sigma` is relative to `mean`.

The resampling loop is bounded by `max_rejections` (default 100). With sensible
parameters that is unreachable, so exhausting it means the bounds and the
distribution disagree — `mean` sitting many `sigma` outside the permitted range,
or `PausePDF` bounds that exclude the sample data. Both raise a `ValueError`
naming the parameters involved, which is a far better failure than spinning
forever inside a tick.

## Schedule files

`PauseSchedule` does not read YAML itself — pass it the output of
`load_schedule_file`, which parses the times and pre-computes the random
offsets. A schedule is a list of windows:

```yaml
- start_pause_time: "22:30:00"
  stop_pause_time: "6:30:00"
  variance: "0:30:00"
```

Two things about `variance` are easy to get wrong. It is applied to **both** the
start and the stop time, independently; and it only ever shifts a time
**later** — the offset is drawn from `[0, variance]`, never negative. So the
window above starts somewhere in 22:30–23:00 and ends somewhere in 06:30–07:00.
Fresh offsets are drawn each time a window is handled, so the boundaries move
from day to day.

Windows that cross midnight, like the one above, are matched correctly.

`load_schedule_file` returns `None` — it does not raise — when the file parses
as empty, so check for it before constructing `PauseSchedule`.

## Pausing at most once per window

`PauseSchedule` remembers the window it last handled and will not pause for it
again, even while the clock is still inside it. It re-arms once the current time
has left every window. Without this, a tree that ticks after the pause finishes
would immediately pause again for the rest of the window.

## In a Sequence or a Selector

When no pause is taken, `PauseSchedule` returns SUCCESS by default, so it works
as a gate at the front of a Sequence: the Sequence waits out a window, then
carries on. To use it as an interrupt in a Selector instead, pass
`fail_outside_window=True`: outside a window it returns FAILURE and the Selector
falls through to the next child, and inside one it stays RUNNING and pre-empts
the children after it.

```python
pause = PauseSchedule(name="Break", schedule=schedule, fail_outside_window=True)
root = py_trees.composites.Selector(name="Root", memory=False)
root.add_children([pause, main_behavior])
```

## API

```{eval-rst}
.. automodule:: py_branches.pause
   :members:
```
