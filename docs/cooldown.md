# cooldown

`Cooldown` enforces a minimum time gap between runs of its child. Use it for
work that is correct to do repeatedly but expensive to do often — a network
call, a disk write, a log line you don't want thousands of.

## The timer starts on completion

The gap is measured from when the child *finished*, not when it started. A child
that takes 2 seconds under a 5-second cooldown runs every 7 seconds, not every
5.

This also means a child that stays RUNNING is never rate-limited: the timer only
starts once the child actually returns SUCCESS or FAILURE. A cooldown around a
long-running behavior constrains how often it restarts, not how long it runs —
for the latter, see {doc}`timeout`.

The timer is wall-clock based and is not reset by re-entering the tree, so the
gap holds even if the subtree above it was invalidated in between.

## Compared to `RunEveryX`

Both space out a child's executions, but they count different things.
{doc}`alternating`'s `RunEveryX` counts *ticks*, so its spacing depends on how
fast your tree ticks. `Cooldown` counts *seconds*. If the requirement comes from
the outside world — an API rate limit, a hardware duty cycle — you want this
module. If it comes from the tree's own logic, you probably want `RunEveryX`.

## API

```{eval-rst}
.. automodule:: py_branches.cooldown
   :members:
```
