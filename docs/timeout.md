# timeout

`Timeout` converts a child that runs too long into a FAILURE, so one stuck
branch cannot stall the whole tree. A child that completes before the deadline
passes its status through untouched.

## What the clock measures

The clock starts in `initialise()` — on each fresh entry — so `duration` bounds
one uninterrupted RUNNING stretch. It is not a budget for the total time the
child has ever spent running across activations.

When the deadline passes, the child is stopped (set to INVALID) so it can clean
up in its `terminate()`, and `Timeout` reports FAILURE. There is no partial
credit: a child that was nearly done is treated the same as one that was stuck.

## Pairing it with `Retry`

`Timeout` inside {doc}`retry`'s `Retry` is a common and useful combination —
each attempt is bounded, and an attempt that hangs is converted into a failure
that `Retry` can then act on. The order matters: `Retry(Timeout(child))` bounds
each attempt, while `Timeout(Retry(child))` bounds the entire retry cycle.

## API

```{eval-rst}
.. automodule:: py_branches.timeout
   :members:
```
