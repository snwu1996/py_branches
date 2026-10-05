# retry

`Retry` re-runs its child when the child fails, up to a limit, and reports
SUCCESS if any attempt succeeds. Use it for operations that fail
transiently — network calls, hardware that occasionally needs a second ask.

Two siblings share its machinery and differ only in what ends the loop:
`RunUntilFailed` stops at the child's first FAILURE, and `RunUntilXSuccesses`
stops once the child has succeeded a given number of times.

## Attempts cost ticks

`Retry` never loops inside a single tick. A failed attempt leaves the decorator
RUNNING, and the next attempt happens on the next tick. `max_attempts=3` against
a child that always fails therefore takes at least three ticks to report
FAILURE. This keeps a retry cycle from blocking the rest of the tree, but it
does mean the retries are paced by your tick rate.

Setting `delay` adds a wall-clock wait between attempts on top of that, during
which the decorator stays RUNNING without ticking the child. Use it when the
thing you are retrying needs recovery time rather than just another go.

## The budget resets on entry

Unlike {doc}`counter` and {doc}`latch`, `Retry` clears its attempt counter in
`initialise()`. Each fresh entry into the subtree gets a full `max_attempts`.
That is almost always what you want from a retry, but it does mean `Retry`
cannot express "three attempts total, ever" — that is `Counter`'s job.

## Repeating until the child fails

`RunUntilFailed` is `Retry` with the roles swapped: it re-runs its child each
time the child *succeeds*, and stops at the first FAILURE. Use it for work that
repeats until the child reports there is nothing left to do — draining a queue,
paging through results, stepping until a condition no longer holds.

The child's FAILURE is the loop's normal exit, so `RunUntilFailed` reports it as
SUCCESS. Reaching `max_runs` without a failure means the loop never got to its
exit condition, and that is reported as FAILURE — the cap is a safety net, not
an expected outcome, and a parent should be able to tell the two apart. If you
need the other convention, wrap it in an `Inverter` or use py_trees' own
`Repeat`.

Everything above applies to it unchanged: runs cost ticks, `delay` waits
between runs, and the budget of `max_runs` resets on each fresh entry.

## Collecting several successes

`RunUntilXSuccesses` re-runs its child until it has succeeded `num_successes`
times, giving up after `max_runs` runs. Use it when one good result is not
enough — several readings to average, several items to fetch.

Successes are counted in total, not in a row: a FAILURE uses up one of the
`max_runs` but does not reset the count, so `S F S S` reaches three successes
on the fourth run. Every finished run counts against the cap, whichever way it
ended.

There is no early exit. Once too many runs have failed for the target to be
reachable, the decorator keeps running the child until `max_runs` anyway, and
only then reports FAILURE. That costs ticks, but it means the child's side
effects happen the same number of times whatever the outcome.

With `num_successes=1` it is exactly `Retry`, with `max_runs` in place of
`max_attempts`. Runs cost ticks, `delay` waits between runs (after a FAILURE as
well as a SUCCESS), and both counters reset on each fresh entry.

## API

```{eval-rst}
.. automodule:: py_branches.retry
   :members:
```
