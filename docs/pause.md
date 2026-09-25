# pause

Four leaf behaviors that hold a tree still, differing only in where the wait
comes from. All of them return RUNNING while waiting and SUCCESS once done, so
the rest of the tree keeps ticking — none of them block.

## Choosing between them

| | Waits for | Use for |
|---|---|---|
| `PauseUniform` | A duration drawn between two bounds | General jitter, think time |
| `PausePDF` | A duration drawn from recorded samples | Reproducing observed timing distributions |
| `PauseUntilKey` | A key press | Operator-gated steps, debugging |
| `PauseSchedule` | A wall-clock window from a YAML file | Idling overnight, or over lunch |

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

## API

```{eval-rst}
.. automodule:: py_branches.pause
   :members:
```
