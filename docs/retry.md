# retry

`Retry` re-runs its child when the child fails, up to a limit, and reports
SUCCESS if any attempt succeeds. Use it for operations that fail
transiently — network calls, hardware that occasionally needs a second ask.

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

## API

```{eval-rst}
.. automodule:: py_branches.retry
   :members:
```
