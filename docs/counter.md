# counter

`Counter` runs its child a fixed number of times and then stops running it
forever, reporting a status of your choosing instead. It is the tool for
one-time setup inside a tree that ticks indefinitely.

## Completions, not attempts

A "completion" is any tick where the child returns SUCCESS **or** FAILURE.
`Counter` limits how many times the child runs; it does not require those runs
to succeed. `Counter(child, num_runs=3)` whose child fails all three times is
done, and will not run it again.

Between runs the child is reset to INVALID so the next run starts cleanly, and
`Counter` itself reports RUNNING. A `Counter` with `num_runs=3` therefore
occupies three ticks before it reports its `completion_status` — worth knowing
if it sits under a Sequence that you expected to advance immediately.

## State outlives the tree

The run count is deliberately *not* cleared by `initialise()`. Re-entering the
subtree does not give the child a fresh budget, which is what makes this usable
for initialization that must happen once per process rather than once per
activation. Call `reset()` when you genuinely want it to run again.

## Compared to `Latch`

Both make something happen once, and the difference is what "once" means:

| | Counts | Retries a failure? |
|---|---|---|
| `Counter(num_runs=1)` | One completion, success or not | No — one attempt is all it gets |
| {doc}`latch`'s `Latch` | One SUCCESS | Yes — keeps trying until the child succeeds |

Reach for `Counter` when the action should be attempted a set number of times,
and `Latch` when it must eventually succeed.

## API

```{eval-rst}
.. automodule:: py_branches.counter
   :members:
```
